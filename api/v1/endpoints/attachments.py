"""
Attachment endpoint
Returns a fresh signed URL for a Pipefy attachment so the browser can download directly.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
import httpx
import logging
from urllib.parse import urlparse
from typing import Optional
from api.deps import get_current_user
from core.config import settings
from repositories.pipefy_data import PipeFyDataRepository

router = APIRouter()
logger = logging.getLogger(__name__)


def _extract_upload_path(url: str) -> Optional[str]:
    """Extract the uploads/UUID/filename portion from a Pipefy storage URL."""
    try:
        path = urlparse(url).path  # e.g. /storage/v1/signed/uploads/UUID/file.jpg
        parts = path.split("/uploads/", 1)
        return parts[1] if len(parts) == 2 else None
    except Exception:
        return None


def _find_fresh_url(original_url: str, card_details: dict) -> Optional[str]:
    """
    Search card_details for a fresh signed URL matching the same upload path.
    Checks both card-level attachments and attachment-type field values.
    """
    upload_path = _extract_upload_path(original_url)
    if not upload_path:
        return None

    # Card-level attachments
    for att in card_details.get("attachments", []):
        for key in ("file_url", "url"):
            candidate = att.get(key) or ""
            if upload_path in candidate:
                return candidate

    # Attachment-type field values
    for field in card_details.get("fields", []):
        if field.get("field", {}).get("type") != "attachment":
            continue
        value = field.get("value") or ""
        if upload_path in value:
            return value
        for av in field.get("array_value") or []:
            if upload_path in (av or ""):
                return av

    return None


@router.get("/fresh-url")
async def get_fresh_attachment_url(
    url: str,
    card_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Returns a fresh Pipefy signed URL for an attachment.
    The frontend uses this URL to trigger a direct browser download from Pipefy
    (no file streaming through our server).

    Query params:
        url:     Original (possibly expired) Pipefy signed URL — used to identify the file
        card_id: Pipefy card ID — used to fetch fresh attachment URLs
    """
    if not url.startswith("https://app.pipefy.com/storage/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Only Pipefy storage URLs are allowed.",
        )

    try:
        pipefy_repo = PipeFyDataRepository(settings.PIPEFY_API_TOKEN)
        card_details = await pipefy_repo.get_card_details(card_id)
        fresh_url = _find_fresh_url(url, card_details)

        if not fresh_url:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find a matching attachment for card {card_id}. "
                       "The file may have been deleted or the URL format is unrecognized.",
            )

        logger.info(f"Returning fresh URL for card {card_id}")
        return {"url": fresh_url}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching fresh URL for card {card_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch fresh URL from Pipefy: {str(e)}",
        )


@router.get("/download")
async def download_attachment(
    url: str,
    card_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Proxy download — kept for fallback.
    Prefer /fresh-url + direct browser download when possible.
    """
    if not url.startswith("https://app.pipefy.com/storage/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Only Pipefy storage URLs are allowed.",
        )

    download_url = url

    if card_id:
        try:
            pipefy_repo = PipeFyDataRepository(settings.PIPEFY_API_TOKEN)
            card_details = await pipefy_repo.get_card_details(card_id)
            fresh = _find_fresh_url(url, card_details)
            if fresh:
                download_url = fresh
                logger.info(f"Using fresh Pipefy URL for card {card_id}")
            else:
                logger.warning(f"No matching fresh URL found for card {card_id}, trying original")
        except Exception as e:
            logger.warning(f"Failed to fetch fresh URL for card {card_id}: {e}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(download_url)
            response.raise_for_status()

            filename = download_url.split("/")[-1].split("?")[0]
            content_type = response.headers.get("content-type", "application/octet-stream")

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(len(response.content)),
                },
            )

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to download file from Pipefy: {str(e)}",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to download file from Pipefy: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error downloading file: {str(e)}",
        )
