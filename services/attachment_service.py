import asyncio
import httpx
import logging
from services.supabase_client import supabase_client
from repositories.attachment_repository import AttachmentRepository

logger = logging.getLogger(__name__)

BUCKET = "pipefy-attachments"


async def fetch_and_store_attachment(
    card_id: str,
    pipefy_url: str,
    filename: str,
) -> dict:
    """
    Downloads a file from Pipefy and uploads it permanently to Supabase Storage.
    Idempotent: returns the existing record if the file was already stored.
    """
    storage_path = f"{card_id}/{filename}"
    repo = AttachmentRepository()
    
    
    print(f"Fetching attachment for card_id={card_id}, pipefy_url={pipefy_url}, filename={filename}")

    # Cache hit — skip download entirely
    existing = await repo.get_by_storage_path(storage_path)
    if existing:
        logger.info(f"Cache hit for {storage_path}")
        return existing
    print(f"No cache hit for {storage_path}, {pipefy_url} proceeding to download and upload")

    # Download from Pipefy (signed URL is self-authenticating, no header needed)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(pipefy_url)
            print(f"Downloaded {filename} from Pipefy with status code {response.status_code}, content-type {response.headers.get('content-type')}, size {len(response.content)} bytes")
            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("content-type", "application/octet-stream")
            logger.info(f"Downloaded {filename} ({len(content)} bytes) from Pipefy")
    except httpx.HTTPError as e:
        logger.error(f"Failed to download {pipefy_url}: {str(e)}")
        raise Exception(f"Failed to download attachment from Pipefy: {str(e)}")

    # Upload to Supabase Storage — supabase_client is sync, run in thread pool
    try:
        print(f"Uploading {filename} to Supabase Storage at path: {storage_path}")
        loop = asyncio.get_event_loop()

        # Try uploading - if file exists, remove and re-upload (upsert)
        def upload_file():
            # Check if file already exists and remove if so (for upsert behavior)
            try:
                existing_files = supabase_client.storage.from_(BUCKET).list(path=f"{card_id}/")
                if any(f.get("name") == filename for f in existing_files):
                    print(f"File {filename} already exists, removing for upsert")
                    supabase_client.storage.from_(BUCKET).remove([storage_path])
            except Exception as list_err:
                print(f"Could not check/remove existing file: {list_err}")

            # Upload the file with raw bytes
            return supabase_client.storage.from_(BUCKET).upload(
                path=storage_path,
                file=content,
                file_options={"content-type": content_type},
            )

        upload_result = await loop.run_in_executor(None, upload_file)
        print(f"Upload result: {upload_result}")
        logger.info(f"Upload completed for {storage_path}")
    except Exception as e:
        logger.error(f"Failed to upload {filename} to Supabase Storage: {str(e)}")
        print(f"Upload error details: {str(e)}")
        raise Exception(f"Failed to upload to Supabase Storage: {str(e)}")

    public_url = supabase_client.storage.from_(BUCKET).get_public_url(storage_path)
    logger.info(f"Uploaded to Supabase Storage: {public_url}")
    print(f"Generated public URL: {public_url}")

    record = await repo.upsert({
        "pipefy_card_id": card_id,
        "storage_path": storage_path,
        "storage_url": public_url,
        "filename": filename,
        "content_type": content_type,
        "file_size": len(content),
    })
    return record
