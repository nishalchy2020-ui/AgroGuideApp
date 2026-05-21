import uuid
from pathlib import Path

from flask import current_app
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

    ext = original.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / unique_name
    file.save(path)
    return unique_name, path


def humanize_class_name(class_name):
    if "___healthy" in class_name or class_name.endswith("_healthy"):
        crop = class_name.split("___")[0].split("__")[0].replace("_", " ")
        return f"Healthy {crop.strip()}"
    parts = class_name.replace("___", " - ").replace("__", " ").replace("_", " ")
    return parts.strip()
