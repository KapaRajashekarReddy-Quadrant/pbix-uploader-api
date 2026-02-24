"""
Standalone script: Download empty .pbix from Azure Blob Storage
and upload it as a new report to a Power BI workspace.

Usage:
    python upload_report.py --workspace-id <WORKSPACE_ID> --report-name <REPORT_NAME>

Auth uses client credentials (service principal) flow — no browser/session needed.
"""

import argparse
import time
import sys
import requests
import msal
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
import os

load_dotenv()

# ── Config (loaded from .env or environment variables) ───────────────────────
TENANT_ID      = os.getenv("TENANT_ID")
CLIENT_ID      = os.getenv("CLIENT_ID")
CLIENT_SECRET  = os.getenv("CLIENT_SECRET")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
BLOB_CONTAINER  = os.getenv("BLOB_CONTAINER")
EMPTY_PBIX_NAME = os.getenv("EMPTY_PBIX_NAME")

POWERBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
POWERBI_API   = "https://api.powerbi.com/v1.0/myorg"
# ─────────────────────────────────────────────────────────────────────────────


def get_access_token() -> str:
    """Obtain a Power BI access token via service principal (client credentials)."""
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=POWERBI_SCOPE)
    if "access_token" not in result:
        print("ERROR: Failed to acquire token:", result.get("error_description"))
        sys.exit(1)
    print("✓ Access token acquired.")
    return result["access_token"]


def download_empty_pbix() -> bytes:
    """Download the empty .pbix template from Azure Blob Storage."""
    blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container    = blob_service.get_container_client(BLOB_CONTAINER)
    blob         = container.get_blob_client(EMPTY_PBIX_NAME)
    data         = blob.download_blob().readall()
    print(f"✓ Downloaded '{EMPTY_PBIX_NAME}' from blob ({len(data):,} bytes).")
    return data


def upload_to_workspace(access_token: str, workspace_id: str, report_name: str, pbix_bytes: bytes) -> dict:
    """Upload the .pbix to the specified Power BI workspace."""
    headers = {"Authorization": f"Bearer {access_token}"}

    upload_url = (
        f"{POWERBI_API}/groups/{workspace_id}/imports"
        f"?datasetDisplayName={report_name}"
        "&nameConflict=CreateOrOverwrite"
    )

    files = {
        "file": (f"{report_name}.pbix", pbix_bytes, "application/vnd.ms-powerbi.pbix")
    }

    print(f"↑ Uploading report '{report_name}' to workspace {workspace_id} ...")
    resp = requests.post(upload_url, headers=headers, files=files)

    if resp.status_code not in (200, 201, 202):
        print(f"ERROR: Upload failed ({resp.status_code}): {resp.text}")
        sys.exit(1)

    print(f"✓ Upload accepted (HTTP {resp.status_code}). Waiting for Power BI to process...")
    return headers


def fetch_report_id(headers: dict, workspace_id: str, report_name: str) -> str | None:
    """Poll the workspace reports list to find the newly uploaded report's ID."""
    reports_url = f"{POWERBI_API}/groups/{workspace_id}/reports"

    for attempt in range(8):
        time.sleep(3)
        resp = requests.get(reports_url, headers=headers)
        if resp.ok:
            for report in resp.json().get("value", []):
                if report["name"].lower() == report_name.lower():
                    return report["id"]
        print(f"  Attempt {attempt + 1}: report not found yet, retrying...")

    return None


def main():
    parser = argparse.ArgumentParser(description="Upload empty .pbix from blob to Power BI workspace.")
    parser.add_argument("--workspace-id",  required=True, help="Power BI workspace (group) ID")
    parser.add_argument("--report-name",   required=True, help="Name to give the uploaded report")
    args = parser.parse_args()

    # Validate required env vars
    missing = [v for v in ["TENANT_ID", "CLIENT_ID", "CLIENT_SECRET",
                            "AZURE_STORAGE_CONNECTION_STRING", "BLOB_CONTAINER", "EMPTY_PBIX_NAME"]
               if not os.getenv(v)]
    if missing:
        print("ERROR: Missing environment variables:", ", ".join(missing))
        sys.exit(1)

    token      = get_access_token()
    pbix_bytes = download_empty_pbix()
    headers    = upload_to_workspace(token, args.workspace_id, args.report_name, pbix_bytes)
    report_id  = fetch_report_id(headers, args.workspace_id, args.report_name)

    if report_id:
        print(f"\n✅ Success!")
        print(f"   Report Name : {args.report_name}")
        print(f"   Report ID   : {report_id}")
        print(f"   Workspace ID: {args.workspace_id}")
    else:
        print("\n⚠️  Upload succeeded but report ID could not be confirmed (may still be processing).")
        print(f"   Check workspace {args.workspace_id} in Power BI portal.")


if __name__ == "__main__":
    main()
