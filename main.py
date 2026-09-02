
# """
# FastAPI app — Upload empty .pbix from Azure Blob Storage to a Power BI workspace.
# Run:  uvicorn main:app --reload
# Docs: http://localhost:8000/docs
# """

# import time
# import os
# import requests
# import msal
# from azure.storage.blob import BlobServiceClient
# from dotenv import load_dotenv
# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel, Field

# load_dotenv()

# # ── Config ────────────────────────────────────────────────────────────────────
# TENANT_ID      = os.getenv("TENANT_ID")
# CLIENT_ID      = os.getenv("CLIENT_ID")
# CLIENT_SECRET  = os.getenv("CLIENT_SECRET")

# AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
# BLOB_CONTAINER  = os.getenv("BLOB_CONTAINER")
# EMPTY_PBIX_NAME = os.getenv("EMPTY_PBIX_NAME")

# POWERBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
# POWERBI_API   = "https://api.powerbi.com/v1.0/myorg"
# # ─────────────────────────────────────────────────────────────────────────────

# app = FastAPI(
#     title="Power BI Report Uploader",
#     description="Downloads an empty .pbix from Azure Blob Storage and uploads it to a Power BI workspace.",
#     version="1.0.0",
# )

# # ── ✅ CORS FIX ───────────────────────────────────────────────────────────────
# origins = [
#     "https://id-preview--1115fb10-6ea8-4052-8d1b-31238016c02e.lovable.app",
#     "https://reportmigration-frontend-g9ceape5ddgxa5gq.eastus-01.azurewebsites.net",
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# # ─────────────────────────────────────────────────────────────────────────────


# # ── Request / Response models ─────────────────────────────────────────────────
# class UploadRequest(BaseModel):
#     workspace_id: str = Field(..., example="90062faa-3344-4bf4-8dc9-f5f54f38d8bf",
#                               description="Power BI Workspace (Group) ID")
#     report_name:  str = Field(..., example="My New Report",
#                               description="Name to give the uploaded report")


# class UploadResponse(BaseModel):
#     message:      str
#     workspace_id: str
#     report_name:  str
#     report_id:    str | None = None
#     dataset_id:   str | None = None
# # ─────────────────────────────────────────────────────────────────────────────


# def get_access_token() -> str:
#     app_client = msal.ConfidentialClientApplication(
#         CLIENT_ID,
#         authority=f"https://login.microsoftonline.com/{TENANT_ID}",
#         client_credential=CLIENT_SECRET,
#     )

#     result = app_client.acquire_token_for_client(scopes=POWERBI_SCOPE)

#     if "access_token" not in result:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Token error: {result.get('error_description')}"
#         )

#     return result["access_token"]


# def download_empty_pbix() -> bytes:
#     try:
#         blob_service = BlobServiceClient.from_connection_string(
#             AZURE_STORAGE_CONNECTION_STRING
#         )
#         container = blob_service.get_container_client(BLOB_CONTAINER)
#         blob = container.get_blob_client(EMPTY_PBIX_NAME)

#         return blob.download_blob().readall()

#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Blob download failed: {str(e)}"
#         )


# def fetch_report_id(headers: dict, workspace_id: str, report_name: str) -> str | None:
#     reports_url = f"{POWERBI_API}/groups/{workspace_id}/reports"

#     for _ in range(8):
#         time.sleep(3)
#         resp = requests.get(reports_url, headers=headers)

#         if resp.ok:
#             for report in resp.json().get("value", []):
#                 if report["name"].lower() == report_name.lower():
#                     return report["id"]

#     return None


# @app.get("/", tags=["Health"])
# def root():
#     return {
#         "status": "ok",
#         "message": "Power BI Report Uploader is running. Visit /docs to use the API."
#     }


# @app.post("/upload-report", response_model=UploadResponse, tags=["Power BI"])
# def upload_report(body: UploadRequest):

#     # 1️⃣ Authenticate
#     access_token = get_access_token()
#     headers = {"Authorization": f"Bearer {access_token}"}

#     # 2️⃣ Download template from Blob Storage
#     pbix_bytes = download_empty_pbix()

#     # 3️⃣ Upload to Power BI (Import API)
#     upload_url = (
#         f"{POWERBI_API}/groups/{body.workspace_id}/imports"
#         f"?datasetDisplayName={body.report_name}"
#         "&nameConflict=CreateOrOverwrite"
#     )

#     files = {
#         "file": (
#             f"{body.report_name}.pbix",
#             pbix_bytes,
#             "application/vnd.ms-powerbi.pbix"
#         )
#     }

#     resp = requests.post(upload_url, headers=headers, files=files)

#     if resp.status_code not in (200, 201, 202):
#         raise HTTPException(status_code=resp.status_code, detail=resp.text)

#     import_data = resp.json()
#     import_id = import_data.get("id")

#     if not import_id:
#         raise HTTPException(
#             status_code=500,
#             detail="Import ID not returned from Power BI."
#         )

#     dataset_id = None
#     report_id = None

#     import_status_url = (
#         f"{POWERBI_API}/groups/{body.workspace_id}/imports/{import_id}"
#     )

#     for _ in range(15):
#         time.sleep(3)

#         status_resp = requests.get(import_status_url, headers=headers)

#         if not status_resp.ok:
#             continue

#         status_json = status_resp.json()
#         state = status_json.get("importState")

#         if state == "Succeeded":
#             datasets = status_json.get("datasets", [])
#             reports = status_json.get("reports", [])

#             if datasets:
#                 dataset_id = datasets[0].get("id")

#             if reports:
#                 report_id = reports[0].get("id")

#             break

#         elif state == "Failed":
#             raise HTTPException(
#                 status_code=500,
#                 detail="Power BI import failed."
#             )

#     # 🔥 NEW LOGIC ADDED: Disable SSO for DirectQuery (Service Principal Mapping)
#     if dataset_id:
#         datasources_url = f"{POWERBI_API}/groups/{body.workspace_id}/datasets/{dataset_id}/datasources"
#         ds_resp = requests.get(datasources_url, headers=headers)

#         if ds_resp.ok:
#             datasources = ds_resp.json().get("value", [])
#             if datasources:
#                 gateway_id = datasources[0]["gatewayId"]
#                 datasource_id = datasources[0]["datasourceId"]

#                 patch_url = f"{POWERBI_API}/gateways/{gateway_id}/datasources/{datasource_id}"

#                 patch_body = {
#                     "credentialDetails": {
#                         "credentialType": "OAuth2",
#                         "credentials": "{\"credentialData\":[]}",
#                         "encryptedConnection": "Encrypted",
#                         "encryptionAlgorithm": "None",
#                         "privacyLevel": "Organizational",
#                         "useEndUserOAuth2Credentials": False
#                     }
#                 }

#                 requests.patch(patch_url, headers=headers, json=patch_body)

#     return UploadResponse(
#         message="Report uploaded successfully"
#                 if dataset_id
#                 else "Upload processing still in progress",
#         workspace_id=body.workspace_id,
#         report_name=body.report_name,
#         report_id=report_id,
#         dataset_id=dataset_id,
#     )

"""
FastAPI app — Upload empty .pbix from Azure Blob Storage to a Power BI workspace.
UPDATED: Reuse path creates a NEW report via the normal import, then rebinds it
onto the existing (reused) dataset — the throwaway dataset created during import
is deleted afterward. This avoids ever returning a fake/non-existent report_id.

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
from fastapi.middleware.cors import CORSMiddleware
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
    description="Downloads an empty .pbix from Azure Blob Storage and uploads it to a Power BI workspace. Supports reuse of existing datasets via rebind.",
    version="2.1.0",
)

# ── ✅ CORS FIX ───────────────────────────────────────────────────────────────
origins = [
    "https://id-preview--1115fb10-6ea8-4052-8d1b-31238016c02e.lovable.app",
    "https://reportmigration-frontend-g9ceape5ddgxa5gq.eastus-01.azurewebsites.net",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ─────────────────────────────────────────────────────────────────────────────


# ── Request / Response models ─────────────────────────────────────────────────
class UploadRequest(BaseModel):
    workspace_id: str = Field(..., example="90062faa-3344-4bf4-8dc9-f5f54f38d8bf",
                              description="Power BI Workspace (Group) ID")
    report_name:  str = Field(..., example="My New Report",
                              description="Name to give the uploaded report")
    dataset_id:   str | None = Field(None, example="12345678-1234-1234-1234-123456789012",
                                     description="[REUSE PATH] Existing dataset ID to bind the new report to")


class UploadResponse(BaseModel):
    message:      str
    workspace_id: str
    report_name:  str
    report_id:    str | None = None
    dataset_id:   str | None = None
# ─────────────────────────────────────────────────────────────────────────────


def get_access_token() -> str:
    """Acquire Power BI API access token."""
    app_client = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )

    result = app_client.acquire_token_for_client(scopes=POWERBI_SCOPE)

    if "access_token" not in result:
        raise HTTPException(
            status_code=500,
            detail=f"Token error: {result.get('error_description')}"
        )

    return result["access_token"]


def download_empty_pbix() -> bytes:
    """Download empty PBIX template from Azure Blob Storage."""
    try:
        blob_service = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING
        )
        container = blob_service.get_container_client(BLOB_CONTAINER)
        blob = container.get_blob_client(EMPTY_PBIX_NAME)

        return blob.download_blob().readall()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Blob download failed: {str(e)}"
        )


def fetch_report_id(headers: dict, workspace_id: str, report_name: str) -> str | None:
    """Poll Power BI to find a report by name (waits up to ~24 seconds)."""
    reports_url = f"{POWERBI_API}/groups/{workspace_id}/reports"

    for _ in range(8):
        time.sleep(3)
        resp = requests.get(reports_url, headers=headers)

        if resp.ok:
            for report in resp.json().get("value", []):
                if report["name"].lower() == report_name.lower():
                    return report["id"]

    return None


def import_empty_pbix(headers: dict, workspace_id: str, report_name: str) -> tuple[str | None, str | None]:
    """
    Runs the standard empty-PBIX import flow. Returns (dataset_id, report_id)
    for whatever got created — used both for the NEW-dataset path and as the
    first step of the REUSE path (which then rebinds and deletes the dataset).
    """
    pbix_bytes = download_empty_pbix()

    upload_url = (
        f"{POWERBI_API}/groups/{workspace_id}/imports"
        f"?datasetDisplayName={report_name}"
        "&nameConflict=CreateOrOverwrite"
    )

    files = {
        "file": (
            f"{report_name}.pbix",
            pbix_bytes,
            "application/vnd.ms-powerbi.pbix"
        )
    }

    resp = requests.post(upload_url, headers=headers, files=files)

    if resp.status_code not in (200, 201, 202):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    import_data = resp.json()
    import_id = import_data.get("id")

    if not import_id:
        raise HTTPException(
            status_code=500,
            detail="Import ID not returned from Power BI."
        )

    dataset_id = None
    report_id = None

    import_status_url = f"{POWERBI_API}/groups/{workspace_id}/imports/{import_id}"

    for _ in range(15):
        time.sleep(3)

        status_resp = requests.get(import_status_url, headers=headers)

        if not status_resp.ok:
            continue

        status_json = status_resp.json()
        state = status_json.get("importState")

        if state == "Succeeded":
            datasets = status_json.get("datasets", [])
            reports = status_json.get("reports", [])

            if datasets:
                dataset_id = datasets[0].get("id")

            if reports:
                report_id = reports[0].get("id")

            break

        elif state == "Failed":
            raise HTTPException(
                status_code=500,
                detail="Power BI import failed."
            )

    return dataset_id, report_id


def disable_sso_for_dataset(headers: dict, workspace_id: str, dataset_id: str) -> None:
    """Disable SSO for DirectQuery (Service Principal Mapping) on a freshly
    imported dataset. Only relevant for a NEWLY created dataset — a reused
    dataset already had this configured the first time it completed."""
    datasources_url = f"{POWERBI_API}/groups/{workspace_id}/datasets/{dataset_id}/datasources"
    ds_resp = requests.get(datasources_url, headers=headers)

    if not ds_resp.ok:
        return

    datasources = ds_resp.json().get("value", [])
    if not datasources:
        return

    gateway_id = datasources[0]["gatewayId"]
    datasource_id = datasources[0]["datasourceId"]

    patch_url = f"{POWERBI_API}/gateways/{gateway_id}/datasources/{datasource_id}"

    patch_body = {
        "credentialDetails": {
            "credentialType": "OAuth2",
            "credentials": "{\"credentialData\":[]}",
            "encryptedConnection": "Encrypted",
            "encryptionAlgorithm": "None",
            "privacyLevel": "Organizational",
            "useEndUserOAuth2Credentials": False
        }
    }

    requests.patch(patch_url, headers=headers, json=patch_body)


def rebind_report(headers: dict, workspace_id: str, report_id: str, target_dataset_id: str) -> None:
    """Rebinds an existing report onto a different dataset."""
    rebind_url = f"{POWERBI_API}/groups/{workspace_id}/reports/{report_id}/Rebind"
    resp = requests.post(rebind_url, headers=headers, json={"datasetId": target_dataset_id})

    if not resp.ok:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Rebind failed: {resp.text}"
        )


def delete_dataset(headers: dict, workspace_id: str, dataset_id: str) -> None:
    """Best-effort cleanup of the throwaway dataset created during a reuse
    import. Failure here is logged but never fails the request — an orphan
    dataset is a minor cost, not a broken migration."""
    try:
        delete_url = f"{POWERBI_API}/groups/{workspace_id}/datasets/{dataset_id}"
        requests.delete(delete_url, headers=headers)
    except Exception as e:
        print(f"[REUSE MODE] Cleanup warning — failed to delete throwaway dataset {dataset_id}: {e}")


@app.get("/", tags=["Health"])
def root():
    return {
        "status": "ok",
        "message": "Power BI Report Uploader is running. Visit /docs to use the API."
    }


@app.post("/upload-report", response_model=UploadResponse, tags=["Power BI"])
def upload_report(body: UploadRequest):
    """
    Upload a report to Power BI.

    Two modes:

    1. **NEW dataset** (dataset_id not provided):
       - Download empty PBIX from blob storage
       - Upload to Power BI (creates new dataset + report)
       - Poll for completion, disable SSO on the new dataset, return new IDs

    2. **REUSE dataset** (dataset_id provided):
       - Still creates a NEW report (same import as above) — a report must
         exist to bind visuals onto; only the *dataset* is being reused.
       - Rebinds that new report onto the existing dataset_id.
       - Deletes the throwaway dataset the import created.
       - Returns the NEW report_id + the REUSED dataset_id.
    """

    # 1️⃣ Authenticate
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # REUSE PATH: create a new report via the normal import, then rebind it
    # onto the existing dataset and discard the throwaway dataset.
    # ═══════════════════════════════════════════════════════════════════════════
    if body.dataset_id:
        print(f"[REUSE MODE] Creating new report, will rebind onto dataset {body.dataset_id}")

        throwaway_dataset_id, new_report_id = import_empty_pbix(headers, body.workspace_id, body.report_name)

        if not new_report_id:
            raise HTTPException(
                status_code=500,
                detail="Reuse mode: import succeeded but no report_id was returned — cannot rebind."
            )

        rebind_report(headers, body.workspace_id, new_report_id, body.dataset_id)

        if throwaway_dataset_id:
            delete_dataset(headers, body.workspace_id, throwaway_dataset_id)

        return UploadResponse(
            message="Report created and bound to existing semantic model",
            workspace_id=body.workspace_id,
            report_name=body.report_name,
            report_id=new_report_id,
            dataset_id=body.dataset_id,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW DATASET PATH: standard import flow
    # ═══════════════════════════════════════════════════════════════════════════
    dataset_id, report_id = import_empty_pbix(headers, body.workspace_id, body.report_name)

    # 5️⃣ Disable SSO for DirectQuery (Service Principal Mapping)
    if dataset_id:
        disable_sso_for_dataset(headers, body.workspace_id, dataset_id)

    return UploadResponse(
        message="Report uploaded successfully"
                if dataset_id
                else "Upload processing still in progress",
        workspace_id=body.workspace_id,
        report_name=body.report_name,
        report_id=report_id,
        dataset_id=dataset_id,
    )

