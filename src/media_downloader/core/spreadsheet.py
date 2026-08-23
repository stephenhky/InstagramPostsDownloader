import os
import json
import logging
import tempfile
import boto3
from typing import List, Dict, Any, Optional
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


def _get_s3_client():
    """Create and return an S3 client using environment credentials."""
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    if not aws_access_key or not aws_secret_key:
        raise RuntimeError("AWS credentials not configured. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")
    return boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )


def get_s3_bucket() -> str:
    bucket = os.getenv("AWS_S3_BUCKET")
    if not bucket:
        raise RuntimeError("AWS_S3_BUCKET environment variable is not set.")
    return bucket


def upload_file_to_s3(local_path: str, s3_key: str) -> str:
    """Upload a local file to S3 and return the S3 URI."""
    s3 = _get_s3_client()
    bucket = get_s3_bucket()
    s3.upload_file(local_path, bucket, s3_key)
    s3_uri = f"s3://{bucket}/{s3_key}"
    logger.info(f"Uploaded {local_path} to {s3_uri}")
    return s3_uri


def upload_directory_to_s3(local_dir: str, s3_prefix: str) -> List[str]:
    """Upload all files in a local directory to S3 under the given prefix."""
    uploaded = []
    for root, dirs, files in os.walk(local_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_dir)
            s3_key = os.path.join(s3_prefix, relative_path).replace("\\", "/")
            s3_uri = upload_file_to_s3(local_path, s3_key)
            uploaded.append(s3_uri)
    return uploaded


def get_google_sheets_client():
    """Create and return an authenticated gspread client using service account.

    Supports GOOGLE_SERVICE_ACCOUNT_JSON as either:
      - A filesystem path to a service account JSON key file
      - The raw JSON string content of the service account key
    """
    import gspread
    from google.oauth2.service_account import Credentials

    service_account_value = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_value:
        raise RuntimeError(
            "Google service account JSON not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON to the path of your service account key file or the raw JSON content."
        )

    temp_file = None
    try:
        if os.path.exists(service_account_value):
            service_account_file = service_account_value
        else:
            try:
                json.loads(service_account_value)
                temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
                temp_file.write(service_account_value)
                temp_file.close()
                service_account_file = temp_file.name
            except json.JSONDecodeError:
                raise RuntimeError(
                    "GOOGLE_SERVICE_ACCOUNT_JSON is neither an existing file path nor valid JSON content."
                )

        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    finally:
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except Exception:
                pass


def get_spreadsheet():
    """Open the target Google Spreadsheet."""
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEETS_ID environment variable is not set.")
    client = get_google_sheets_client()
    return client.open_by_key(spreadsheet_id)


def read_sheet_data() -> List[Dict[str, Any]]:
    """Read all data from the first worksheet of the spreadsheet."""
    spreadsheet = get_spreadsheet()
    worksheet = spreadsheet.get_worksheet(0)
    records = worksheet.get_all_records()
    logger.info(f"Read {len(records)} rows from Google Sheet.")
    return records


def find_row_index_by_url(worksheet, url: str) -> Optional[int]:
    """Find the 1-based row index for a given URL in the sheet."""
    try:
        url_col = worksheet.find("Link")
    except Exception:
        try:
            url_col = worksheet.find("link")
        except Exception:
            return None
    if url_col is None:
        return None
    values = worksheet.col_values(url_col.col)
    for idx, val in enumerate(values, start=1):
        if val == url:
            return idx
    return None


def update_row_status(url: str, new_status: str) -> bool:
    """Update the Status cell for the row matching the given URL."""
    spreadsheet = get_spreadsheet()
    worksheet = spreadsheet.get_worksheet(0)
    row_idx = find_row_index_by_url(worksheet, url)
    if row_idx is None:
        logger.warning(f"Could not find row for URL: {url}")
        return False

    try:
        status_col = worksheet.find("Status")
    except Exception:
        try:
            status_col = worksheet.find("status")
        except Exception:
            logger.warning("Could not find 'Status' column in sheet.")
            return False
    if status_col is None:
        logger.warning("Could not find 'Status' column in sheet.")
        return False

    worksheet.update_cell(row_idx, status_col.col, new_status)
    logger.info(f"Updated status for {url} to {new_status}")
    return True


def save_spreadsheet_metadata(post_metadata: Dict[str, Any]) -> str:
    """Save post metadata to a local JSON file for the gallery view."""
    metadata_dir = os.path.join("downloads", ".spreadsheet_meta")
    os.makedirs(metadata_dir, exist_ok=True)

    identifier = post_metadata.get("shortcode") or post_metadata.get("post_id") or post_metadata.get("url", "unknown")
    safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in identifier)
    metadata_file = os.path.join(metadata_dir, f"{safe_id}.json")

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(post_metadata, f, indent=4, ensure_ascii=False)
    return metadata_file


def load_all_spreadsheet_metadata() -> List[Dict[str, Any]]:
    """Load all saved spreadsheet metadata files."""
    metadata_dir = os.path.join("downloads", ".spreadsheet_meta")
    if not os.path.exists(metadata_dir):
        return []

    items = []
    for filename in os.listdir(metadata_dir):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(metadata_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                items.append(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to read metadata file {filename}: {e}")
    return items
