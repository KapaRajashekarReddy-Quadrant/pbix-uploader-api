"""
FastAPI app — Upload empty .pbix from Azure Blob Storage to a Power BI workspace.
Run:  uvicorn main:app --reload
Docs: http://localhost:8000/docs
"""

import time
import os
import requests
import msal
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
TENANT_ID      = os.getenv("TENANT_ID")
CLIENT_ID      = os.getenv("CLIENT_ID")
CLIENT_SECRET  = os.getenv("CLIENT_SECRET")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
BLOB_CONTAINER  = os.getenv("BLOB_CONTAINER")
EMPTY_PBIX_NAME = os.getenv("EMPTY_PBIX_NAME")

POWERBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
POWERBI_API   = "https://api.powerbi.com/v1.0/myorg"
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Power BI Report Uploader",
    description="Downloads an empty .pbix from Azure Blob Storage and uploads it to a Power BI workspace.",
    version="1.0.0",
)


# ── Request / Response models ─────────────────────────────────────────────────
class UploadRequest(BaseModel):
    workspace_id: str = Field(..., example="90062faa-3344-4bf4-8dc9-f5f54f38d8bf", description="Power BI Workspace (Group) ID")
    report_name:  str = Field(..., example="My New Report", description="Name to give the uploaded report")


class UploadResponse(BaseModel):
    message:      str
    workspace_id: str
    report_name:  str
    report_id:    str | None = None
# ─────────────────────────────────────────────────────────────────────────────


def get_access_token() -> str:
    app_client = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app_client.acquire_token_for_client(scopes=POWERBI_SCOPE)
    if "access_token" not in result:
        raise HTTPException(status_code=500, detail=f"Token error: {result.get('error_description')}")
    return result["access_token"]


def download_empty_pbix() -> bytes:
    try:
        blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        container    = blob_service.get_container_client(BLOB_CONTAINER)
        blob         = container.get_blob_client(EMPTY_PBIX_NAME)
        return blob.download_blob().readall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Blob download failed: {str(e)}")


def fetch_report_id(headers: dict, workspace_id: str, report_name: str) -> str | None:
    reports_url = f"{POWERBI_API}/groups/{workspace_id}/reports"
    for _ in range(8):
        time.sleep(3)
        resp = requests.get(reports_url, headers=headers)
        if resp.ok:
            for report in resp.json().get("value", []):
                if report["name"].lower() == report_name.lower():
                    return report["id"]
    return None


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "Power BI Report Uploader is running. Visit /docs to use the API."}


@app.post("/upload-report", response_model=UploadResponse, tags=["Power BI"])
def upload_report(body: UploadRequest):
    """
    Downloads the empty .pbix template from Azure Blob Storage and uploads it
    to the specified Power BI workspace as a new report.
    """
    # 1. Auth
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    # 2. Download template from blob
    pbix_bytes = download_empty_pbix()

    # 3. Upload to Power BI
    upload_url = (
        f"{POWERBI_API}/groups/{body.workspace_id}/imports"
        f"?datasetDisplayName={body.report_name}"
        "&nameConflict=CreateOrOverwrite"
    )
    files = {
        "file": (f"{body.report_name}.pbix", pbix_bytes, "application/vnd.ms-powerbi.pbix")
    }

    resp = requests.post(upload_url, headers=headers, files=files)

    if resp.status_code not in (200, 201, 202):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    # 4. Poll for report ID
    report_id = fetch_report_id(headers, body.workspace_id, body.report_name)

    return UploadResponse(
        message="Report uploaded successfully" if report_id else "Upload accepted but report ID not yet confirmed",
        workspace_id=body.workspace_id,
        report_name=body.report_name,
        report_id=report_id,
    )
