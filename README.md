# PBIX Blob → Power BI Uploader

A minimal standalone script that:
1. Downloads an empty `.pbix` template from **Azure Blob Storage**
2. Uploads it as a new report to a given **Power BI workspace**

---

## Setup

```bash
pip install -r requirements.txt
```

Fill in `.env` with your credentials:

```
TENANT_ID=...
CLIENT_ID=...
CLIENT_SECRET=...
AZURE_STORAGE_CONNECTION_STRING=...
BLOB_CONTAINER=powerbi-template
EMPTY_PBIX_NAME=Generatedpbi.pbix
```

> **Auth note:** This script uses **Service Principal (client credentials)** flow — no browser login needed.  
> Make sure your service principal has the **Power BI Workspace Admin/Member** role and the Power BI tenant setting *"Allow service principals to use Power BI APIs"* is enabled.

---

## Usage

```bash
python upload_report.py --workspace-id <WORKSPACE_ID> --report-name <REPORT_NAME>
```

### Example

```bash
python upload_report.py \
  --workspace-id 90062faa-3344-4bf4-8dc9-f5f54f38d8bf \
  --report-name "My New Report"
```

### Output

```
✓ Access token acquired.
✓ Downloaded 'Generatedpbi.pbix' from blob (12,345 bytes).
↑ Uploading report 'My New Report' to workspace 90062faa-... 
✓ Upload accepted (HTTP 202). Waiting for Power BI to process...
  Attempt 1: report not found yet, retrying...

✅ Success!
   Report Name : My New Report
   Report ID   : 3cf615ca-6afb-4259-bda1-b91a8848892e
   Workspace ID: 90062faa-3344-4bf4-8dc9-f5f54f38d8bf
```
