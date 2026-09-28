"""Secure item image handling.

Validation rules:
* extension whitelist (jpg / jpeg / png / webp)
* MIME type whitelist
* magic-byte verification through Pillow (never trust the client)
* size limits
* generated random filenames (original filenames are never used)
* stored below the dedicated upload folder only (no path traversal)
* images are resized/compressed before saving
"""

import io
import os
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps

from app import constants as C


class ImageValidationError(Exception):
    """User facing image validation error."""


def _allowed_config():
    allowed_ext = current_app.config.get("ALLOWED_IMAGE_EXTENSIONS", C.ALLOWED_IMAGE_EXTENSIONS)
    allowed_mime = current_app.config.get("ALLOWED_IMAGE_MIME_TYPES", C.ALLOWED_IMAGE_MIME_TYPES)
    allowed_formats = current_app.config.get("ALLOWED_IMAGE_FORMATS", C.ALLOWED_IMAGE_FORMATS)
    max_bytes = current_app.config.get("MAX_IMAGE_BYTES", C.MAX_IMAGE_BYTES)
    return allowed_ext, allowed_mime, allowed_formats, max_bytes


def _extension_of(filename: str) -> str:
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if not ext.isalnum() or not ext:
        raise ImageValidationError("Invalid file name.")
    return ext


def process_image(file_storage, subfolder: str = "items") -> str:
    """Validate, resize and store an uploaded image.

    Returns the stored path relative to the upload folder, e.g.
    ``items/202609/a1b2c3d4e5.jpg``.
    """
    allowed_ext, allowed_mime, allowed_formats, max_bytes = _allowed_config()

    filename = getattr(file_storage, "filename", "") or ""
    if not filename:
        raise ImageValidationError("No image file selected.")

    ext = _extension_of(filename)
    if ext not in allowed_ext:
        raise ImageValidationError(
            "Unsupported file type. Allowed: " + ", ".join(sorted(allowed_ext)) + "."
        )

    mime = (getattr(file_storage, "mimetype", "") or "").lower()
    if mime not in allowed_mime:
        raise ImageValidationError("Unsupported image content type.")

    data = file_storage.read()
    if not data:
        raise ImageValidationError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise ImageValidationError(f"Image is too large (max {max_bytes // (1024 * 1024)} MB).")

    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:  # Pillow raises many exception types
        raise ImageValidationError("The file is not a valid image.") from exc

    if image.format not in allowed_formats:
        raise ImageValidationError(
            "Unsupported image format. Allowed: " + ", ".join(sorted(allowed_formats)) + "."
        )

    image = ImageOps.exif_transpose(image)

    max_dimension = int(
        current_app.config.get("IMAGE_MAX_DIMENSION", C.IMAGE_MAX_DIMENSION)
    )
    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )

    if has_alpha:
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        output_format = "PNG"
        new_ext = "png"
        quality_args = {"optimize": True}
    else:
        if image.mode != "RGB":
            image = image.convert("RGB")
        output_format = "JPEG"
        new_ext = "jpg"
        quality_args = {
            "quality": int(current_app.config.get("IMAGE_JPEG_QUALITY", C.IMAGE_JPEG_QUALITY)),
            "optimize": True,
        }

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target_dir = upload_root / subfolder / date_folder()
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}.{new_ext}"
    destination = (target_dir / safe_name).resolve()

    # Path traversal guard: the final path must stay inside the upload folder.
    if upload_root != destination and upload_root not in destination.parents:
        raise ImageValidationError("Invalid upload path.")

    buffer = io.BytesIO()
    image.save(buffer, format=output_format, **quality_args)
    buffer.seek(0)
    with open(destination, "wb") as handle:
        handle.write(buffer.read())

    relative = destination.relative_to(upload_root).as_posix()
    return relative


def date_folder() -> str:
    from datetime import datetime

    return datetime.utcnow().strftime("%Y%m")


def delete_stored_image(relative_path: str) -> None:
    """Remove a previously stored image file (ignores missing files)."""
    if not relative_path:
        return
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    destination = (upload_root / relative_path).resolve()
    if upload_root != destination and upload_root not in destination.parents:
        return
    try:
        if destination.is_file():
            os.remove(destination)
    except OSError:
        pass
