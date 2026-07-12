import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename


def allowed_file(filename):
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def save_upload(file):
    original = secure_filename(file.filename or "upload.jpg")
    if not allowed_file(original):
        raise ValueError("Invalid file type. Use PNG, JPG, JPEG, or WEBP.")

    unique_name = f"{uuid.uuid4().hex}.jpg"
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / unique_name
    source_path = upload_dir / f".{uuid.uuid4().hex}.upload"
    try:
        file.save(source_path)
        _normalize_and_compress_image(source_path, path)
    finally:
        source_path.unlink(missing_ok=True)
    return unique_name, path


def _normalize_and_compress_image(source_path, output_path):
    """Validate an upload and save a small, model-friendly JPEG copy."""
    allowed_formats = {"PNG", "JPEG", "WEBP", "GIF"}
    try:
        with Image.open(source_path) as image:
            image.verify()
            image_format = image.format
        with Image.open(source_path) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        output_path.unlink(missing_ok=True)
        raise ValueError("Uploaded file is not a valid image.") from exc

    if image_format not in allowed_formats:
        output_path.unlink(missing_ok=True)
        raise ValueError("Unsupported image format. Use PNG, JPG, JPEG, GIF, or WEBP.")
    if width < 32 or height < 32:
        output_path.unlink(missing_ok=True)
        raise ValueError("Image is too small for reliable disease detection.")
    if width > 8000 or height > 8000:
        output_path.unlink(missing_ok=True)
        raise ValueError("Image dimensions are too large.")

    try:
        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            image.seek(0)
            image = image.convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            image.save(output_path, "JPEG", quality=78, optimize=True, progressive=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        output_path.unlink(missing_ok=True)
        raise ValueError("The image could not be prepared for detection.") from exc


def humanize_class_name(class_name):
    if "___healthy" in class_name or class_name.endswith("_healthy"):
        crop = class_name.split("___")[0].split("__")[0].replace("_", " ")
        return f"Healthy {crop.strip()}"
    parts = class_name.replace("___", " - ").replace("__", " ").replace("_", " ")
    return parts.strip()
