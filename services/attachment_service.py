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

    # Cache hit — skip download entirely
    existing = await repo.get_by_storage_path(storage_path)
    if existing:
        logger.info(f"Cache hit for {storage_path}")
        return existing

    # Download from Pipefy (signed URL is self-authenticating, no header needed)
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(pipefy_url)
        response.raise_for_status()
        content = response.content
        content_type = response.headers.get("content-type", "application/octet-stream")

    logger.info(f"Downloaded {filename} ({len(content)} bytes) from Pipefy")

    # Upload to Supabase Storage — supabase_client is sync, run in thread pool
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: supabase_client.storage.from_(BUCKET).upload(
            storage_path,
            content,
            file_options={"content-type": content_type, "upsert": "true"},
        ),
    )

    public_url = supabase_client.storage.from_(BUCKET).get_public_url(storage_path)
    logger.info(f"Uploaded to Supabase Storage: {public_url}")

    record = await repo.upsert({
        "pipefy_card_id": card_id,
        "storage_path": storage_path,
        "storage_url": public_url,
        "filename": filename,
        "content_type": content_type,
        "file_size": len(content),
    })
    return record
