import asyncio
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile

from repositories.order_files import OrderFileRepository
from schemas.order_file import OrderFileOut, OrderFileUpdate
from services.supabase_client import supabase_client

logger = logging.getLogger(__name__)

# Private bucket: files are organized as `<order_id>/<uuid>-<filename>`.
BUCKET = "order-files"
SIGNED_URL_EXPIRY_SECONDS = 3600  # 1 hour
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB — mirrors the bucket's file_size_limit
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/gif",
    "application/pdf",
}

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: Optional[str]) -> str:
    """Sanitize a client-supplied filename for use in a storage path."""
    cleaned = (name or "file").strip().replace(" ", "_")
    cleaned = _UNSAFE_CHARS.sub("", cleaned)
    return cleaned or "file"


def _sign(path: str) -> Optional[str]:
    """Create a short-lived signed URL for a private object (blocking)."""
    try:
        result = supabase_client.storage.from_(BUCKET).create_signed_url(
            path, SIGNED_URL_EXPIRY_SECONDS
        )
        return result.get("signedURL") or result.get("signedUrl")
    except Exception as exc:  # signing failure shouldn't break the read path
        logger.warning("Could not sign URL for %s: %s", path, exc)
        return None


async def _to_out(row: Dict[str, Any]) -> OrderFileOut:
    """Map a DB row to OrderFileOut, attaching a fresh signed URL."""
    out = OrderFileOut.model_validate(row)
    if out.file_url:
        out.signed_url = await asyncio.to_thread(_sign, out.file_url)
    return out


async def _sign_all(rows: List[Dict[str, Any]]) -> List[OrderFileOut]:
    return list(await asyncio.gather(*[_to_out(row) for row in rows]))


async def sign_paths(paths: List[str]) -> Dict[str, Optional[str]]:
    """Sign many object paths concurrently, returning {path: signed_url}.

    Used by callers that embed order files (e.g. the full order details
    listing) and need a usable URL per file without N sequential calls.
    Duplicate paths are signed once.
    """
    unique = list({p for p in paths if p})
    if not unique:
        return {}
    signed = await asyncio.gather(*[asyncio.to_thread(_sign, p) for p in unique])
    return dict(zip(unique, signed))


async def _upload_bytes(path: str, content: bytes, content_type: str) -> None:
    """Upload raw bytes to the private bucket (supabase client is sync)."""
    def _do_upload() -> Any:
        return supabase_client.storage.from_(BUCKET).upload(
            path=path,
            file=content,
            file_options={"content-type": content_type},
        )

    await asyncio.to_thread(_do_upload)


async def remove_paths(paths: List[str]) -> None:
    """Public best-effort removal of objects from Storage.

    Used by callers outside this module (e.g. deleting an order, whose
    file rows are cascade-deleted in the DB but whose Storage objects are
    not) to clean the bucket.
    """
    await _remove_paths(paths)


async def _remove_paths(paths: List[str]) -> None:
    """Best-effort removal of objects from Storage (used for cleanup)."""
    if not paths:
        return

    def _do_remove() -> Any:
        return supabase_client.storage.from_(BUCKET).remove(paths)

    try:
        await asyncio.to_thread(_do_remove)
    except Exception as exc:
        logger.warning("Failed to remove storage objects %s: %s", paths, exc)


async def upload_files_for_order(
    order_id: str,
    files: List[UploadFile],
    uploaded_by: Optional[str] = None,
    label: Optional[str] = None,
) -> List[OrderFileOut]:
    """Upload one or more files into the order's folder and record them.

    The bytes are validated (type/size), uploaded to `order-files/<order_id>/`,
    and a metadata row is inserted per file. If the DB insert fails, the
    just-uploaded objects are cleaned up so Storage doesn't drift from the DB.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    uploaded_paths: List[str] = []
    records: List[Dict[str, Any]] = []

    for file in files:
        content = await file.read()
        size = len(content)

        if size == 0:
            await _remove_paths(uploaded_paths)
            raise HTTPException(
                status_code=400, detail=f"File '{file.filename}' is empty"
            )
        if size > MAX_FILE_SIZE:
            await _remove_paths(uploaded_paths)
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' exceeds the 10MB limit",
            )

        content_type = file.content_type or "application/octet-stream"
        if content_type not in ALLOWED_CONTENT_TYPES:
            await _remove_paths(uploaded_paths)
            raise HTTPException(
                status_code=415,
                detail=(
                    f"Unsupported file type '{content_type}' for "
                    f"'{file.filename}'. Allowed: images and PDF."
                ),
            )

        path = f"{order_id}/{uuid.uuid4().hex}-{_safe_filename(file.filename)}"
        try:
            await _upload_bytes(path, content, content_type)
        except Exception as exc:
            await _remove_paths(uploaded_paths)
            logger.error("Storage upload failed for %s: %s", path, exc)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to upload '{file.filename}' to storage: {exc}",
            )
        uploaded_paths.append(path)

        record: Dict[str, Any] = {
            "order_id": str(order_id),
            "file_url": path,
            "file_type": content_type,
        }
        if uploaded_by:
            record["uploaded_by"] = str(uploaded_by)
        if label:
            record["label"] = label
        records.append(record)

    repo = OrderFileRepository()
    try:
        created = await repo.create_many(records)
    except HTTPException:
        # DB insert failed (e.g. unknown order_id) — undo the storage uploads.
        await _remove_paths(uploaded_paths)
        raise

    logger.info("Uploaded %d file(s) for order %s", len(created), order_id)
    return await _sign_all(created)


async def list_files_for_order(order_id: str) -> List[OrderFileOut]:
    """Return every file attached to an order, each with a fresh signed URL."""
    repo = OrderFileRepository()
    rows = await repo.list_by_order(str(order_id))
    return await _sign_all(rows)


async def get_file(file_id: str) -> OrderFileOut:
    """Return a single order file (404 if it doesn't exist)."""
    repo = OrderFileRepository()
    row = await repo.get_by_id(str(file_id))
    if not row:
        raise HTTPException(status_code=404, detail="Order file not found")
    return await _to_out(row)


async def update_file(file_id: str, data: OrderFileUpdate) -> OrderFileOut:
    """Patch editable metadata (label / file_type) on an order file."""
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    repo = OrderFileRepository()
    row = await repo.update(str(file_id), payload)
    if not row:
        raise HTTPException(status_code=404, detail="Order file not found")
    return await _to_out(row)


async def delete_file(file_id: str) -> None:
    """Delete an order file from both the DB and Storage (404 if missing)."""
    repo = OrderFileRepository()
    row = await repo.delete(str(file_id))
    if not row:
        raise HTTPException(status_code=404, detail="Order file not found")

    path = row.get("file_url")
    if path:
        await _remove_paths([path])
    logger.info("Deleted order file %s", file_id)
