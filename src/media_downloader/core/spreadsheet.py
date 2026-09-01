import os
import json
import logging
import tempfile
import boto3
from typing import List, Dict, Any, Optional
from botocore.exceptions import BotoCoreError, ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
import gspread
from gspread.exceptions import IncorrectCellLabel

logger = logging.getLogger(__name__)


def _is_retryable_gspread_error(exc: BaseException) -> bool:
    """Return True for transient gspread API errors worth retrying."""
    if isinstance(exc, gspread.exceptions.APIError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status in (500, 502, 503, 504, 429)
    return False


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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(_is_retryable_gspread_error))
def get_spreadsheet():
    """Open the target Google Spreadsheet."""
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEETS_ID environment variable is not set.")
    client = get_google_sheets_client()
    return client.open_by_key(spreadsheet_id)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(_is_retryable_gspread_error))
def read_sheet_data() -> List[Dict[str, Any]]:
    """Read all data from the first worksheet of the spreadsheet."""
    spreadsheet = get_spreadsheet()
    worksheet = spreadsheet.get_worksheet(0)
    records = worksheet.get_all_records()
    logger.info(f"Read {len(records)} rows from Google Sheet.")
    return records


def _get_column_indices(worksheet) -> Dict[str, int]:
    """Get mapping of canonical lowercase column name to 1-based column index."""
    headers = worksheet.row_values(1)
    col_map = {}
    for idx, h in enumerate(headers, start=1):
        clean_h = h.strip().lower().replace(" ", "_")
        col_map[clean_h] = idx
    return col_map


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(_is_retryable_gspread_error))
def find_row_index_by_url(worksheet, url: str) -> Optional[int]:
    """Find the 1-based row index for a given URL in the sheet."""
    col_map = _get_column_indices(worksheet)
    link_col = col_map.get("link")
    if not link_col:
        return None

    clean_target = url.strip().rstrip("/")
    values = worksheet.col_values(link_col)
    for idx, val in enumerate(values, start=1):
        if idx == 1:
            continue
        if val.strip().rstrip("/") == clean_target:
            return idx

    # Also check rectified_link column if available
    rect_col = col_map.get("rectified_link")
    if rect_col:
        rect_values = worksheet.col_values(rect_col)
        for idx, val in enumerate(rect_values, start=1):
            if idx == 1:
                continue
            if val.strip().rstrip("/") == clean_target:
                return idx

    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(_is_retryable_gspread_error))
def update_row_fields(url: str, status: Optional[str] = None, username: Optional[str] = None, rectified_link: Optional[str] = None) -> bool:
    """Update row cells (status, username, rectified_link) for the row matching URL."""
    spreadsheet = get_spreadsheet()
    worksheet = spreadsheet.get_worksheet(0)
    row_idx = find_row_index_by_url(worksheet, url)
    if row_idx is None:
        logger.warning(f"Could not find row for URL: {url}")
        return False

    col_map = _get_column_indices(worksheet)
    if status and "status" in col_map:
        worksheet.update_cell(row_idx, col_map["status"], status)
        logger.info(f"Updated status for {url} to {status}")
    if username and "username" in col_map:
        current_user = worksheet.cell(row_idx, col_map["username"]).value
        if not current_user:
            worksheet.update_cell(row_idx, col_map["username"], username)
            logger.info(f"Updated username for {url} to {username}")
    if rectified_link and "rectified_link" in col_map:
        current_rect = worksheet.cell(row_idx, col_map["rectified_link"]).value
        if not current_rect:
            worksheet.update_cell(row_idx, col_map["rectified_link"], rectified_link)
            logger.info(f"Updated rectified_link for {url} to {rectified_link}")
    return True


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(_is_retryable_gspread_error))
def update_row_status(url: str, new_status: str) -> bool:
    """Update the Status cell for the row matching the given URL."""
    return update_row_fields(url, status=new_status)


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


# ── Column name normalization ──────────────────────────────────────────────────

# Canonical column names mapped to lowercase keys for case-insensitive lookup
_COLUMN_MAP = {
    "datetime": "datetime",
    "link": "link",
    "rectified_link": "rectified_link",
    "rectified link": "rectified_link",
    "username": "username",
    "platform": "platform",
    "status": "status",
    "comment": "comment",
}


def normalize_row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a spreadsheet row's keys to canonical lowercase names."""
    normalized = {}
    for key, value in row.items():
        canonical = _COLUMN_MAP.get(key.strip().lower(), key.strip().lower())
        normalized[canonical] = value
    return normalized


# ── S3 helpers ────────────────────────────────────────────────────────────────

def list_s3_post_files(s3_prefix: str) -> List[str]:
    """List all object keys under a given S3 prefix."""
    s3 = _get_s3_client()
    bucket = get_s3_bucket()
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def rename_s3_media_files(s3_prefix: str, suffix: str) -> List[str]:
    """Rename media files in S3 by applying a suffix before the file extension.

    Returns the list of new S3 keys after renaming.
    """
    import re as _re

    s3 = _get_s3_client()
    bucket = get_s3_bucket()
    existing_keys = list_s3_post_files(s3_prefix)

    new_keys = []
    clean_suffix = _re.sub(r'[\\/*?:"<>|]', "", suffix)

    for old_key in existing_keys:
        filename = os.path.basename(old_key)
        base, ext = os.path.splitext(filename)

        # Skip metadata.json from renaming
        if filename == "metadata.json":
            new_keys.append(old_key)
            continue

        # Only add suffix if not already present
        if clean_suffix and not base.endswith(clean_suffix):
            new_base = f"{base}{clean_suffix}"
        else:
            new_base = base

        new_filename = f"{new_base}{ext}"
        new_key = old_key.rsplit("/", 1)[0] + "/" + new_filename

        if new_key != old_key:
            # Copy to new key, then delete old key
            s3.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": old_key},
                Key=new_key,
            )
            s3.delete_object(Bucket=bucket, Key=old_key)
            logger.info(f"Renamed S3 object: {old_key} -> {new_key}")

        new_keys.append(new_key)

    # Update metadata.json in S3 with new filenames
    meta_key = f"{s3_prefix}/metadata.json" if not s3_prefix.endswith("/") else f"{s3_prefix}metadata.json"
    try:
        response = s3.get_object(Bucket=bucket, Key=meta_key)
        meta = json.loads(response["Body"].read().decode("utf-8"))
        new_media_files = []
        for f in meta.get("media_files", []):
            base, ext = os.path.splitext(f)
            if clean_suffix and not base.endswith(clean_suffix):
                new_media_files.append(f"{base}{clean_suffix}{ext}")
            else:
                new_media_files.append(f)
        meta["media_files"] = new_media_files
        s3.put_object(
            Bucket=bucket,
            Key=meta_key,
            Body=json.dumps(meta, indent=4, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info(f"Updated metadata.json in S3 at {meta_key}")

        # Also update local metadata cache
        save_spreadsheet_metadata(meta)
    except Exception as e:
        logger.warning(f"Could not update metadata.json in S3: {e}")

    return new_keys


def download_post_from_s3(s3_prefix: str, local_target_dir: str) -> List[str]:
    """Download all files from an S3 prefix to a local directory.

    Returns the list of downloaded local file paths.
    """
    s3 = _get_s3_client()
    bucket = get_s3_bucket()
    os.makedirs(local_target_dir, exist_ok=True)

    keys = list_s3_post_files(s3_prefix)
    downloaded = []

    s3_filenames = {os.path.basename(k) for k in keys}

    # Clean up stale local media files that no longer exist in S3 (e.g. after rename)
    for local_file in os.listdir(local_target_dir):
        if local_file not in s3_filenames and local_file != "metadata.json":
            try:
                os.remove(os.path.join(local_target_dir, local_file))
                logger.info(f"Removed stale local file: {local_file}")
            except Exception as e:
                logger.warning(f"Failed to remove stale file {local_file}: {e}")

    for key in keys:
        filename = os.path.basename(key)
        local_path = os.path.join(local_target_dir, filename)
        s3.download_file(bucket, key, local_path)
        logger.info(f"Downloaded S3 object {key} to {local_path}")
        downloaded.append(local_path)

    return downloaded


def get_s3_media_url(s3_key: str) -> str:
    """Generate a pre-signed URL for an S3 object (valid for 1 hour)."""
    s3 = _get_s3_client()
    bucket = get_s3_bucket()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=3600,
    )
    return url
