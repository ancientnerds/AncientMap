"""
Simple image upload server for Ancient Nerds Map.
Uploads go to 'uploads/' folder for manual review before approval.

Run: python upload_server.py
Then uploads are accepted at http://localhost:8001/upload

To approve images: manually move from uploads/{site_id}/ to
ancient-nerds-map/public/images/sites/{site_id}/
"""

import os
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Ancient Nerds Image Upload Server")

# CORS configuration (via API_CORS_ORIGINS env var, defaults to localhost for dev)
cors_origins_str = os.getenv("API_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
UPLOAD_DIR = Path("uploads")
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
ALLOWED_MIMETYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def get_image_type(file_content: bytes) -> str | None:
    """Detect image type from magic bytes (replacement for imghdr removed in Python 3.13)."""
    if len(file_content) < 12:
        return None
    # JPEG: starts with FF D8 FF
    if file_content[:3] == b'\xff\xd8\xff':
        return 'jpeg'
    # PNG: starts with 89 50 4E 47 0D 0A 1A 0A
    if file_content[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    # GIF: starts with GIF87a or GIF89a
    if file_content[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    # WebP: starts with RIFF....WEBP
    if file_content[:4] == b'RIFF' and file_content[8:12] == b'WEBP':
        return 'webp'
    return None


def validate_image(file_content: bytes, filename: str) -> bool:
    """Validate that file is actually an image."""
    # Check extension
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False

    # Check magic bytes (actual file type)
    img_type = get_image_type(file_content)
    if img_type not in ('jpeg', 'png', 'gif', 'webp'):
        return False

    return True


@app.post("/upload")
async def upload_image(
    file: UploadFile,
    site_id: str = Form(...),
    site_name: str = Form(default=""),
    uploader: str = Form(default="anonymous"),
):
    """
    Upload an image for a site.

    - file: The image file (jpg, png, gif, webp only)
    - site_id: The site ID this image belongs to
    - site_name: Optional site name for reference
    - uploader: Optional uploader name/email
    """
    # Validate site_id
    if not site_id or len(site_id) > 100:
        raise HTTPException(400, "Invalid site_id")

    # Sanitize site_id (prevent path traversal)
    safe_site_id = "".join(c for c in site_id if c.isalnum() or c in ('_', '-'))
    if not safe_site_id:
        raise HTTPException(400, "Invalid site_id")

    # Check file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large. Max {MAX_FILE_SIZE // 1024 // 1024}MB")

    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    # Validate it's actually an image
    if not validate_image(content, file.filename or "unknown.jpg"):
        raise HTTPException(400, "Invalid image format. Allowed: jpg, png, gif, webp")

    # Check content type
    if file.content_type and file.content_type not in ALLOWED_MIMETYPES:
        raise HTTPException(400, f"Invalid content type: {file.content_type}")

    # Create upload directory
    site_upload_dir = UPLOAD_DIR / safe_site_id
    site_upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    ext = Path(file.filename or "image.jpg").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = '.jpg'

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    new_filename = f"{timestamp}_{unique_id}{ext}"

    # Save file
    file_path = site_upload_dir / new_filename
    with open(file_path, 'wb') as f:
        f.write(content)

    # Save metadata
    meta_path = site_upload_dir / f"{new_filename}.meta.txt"
    with open(meta_path, 'w') as f:
        f.write(f"site_id: {site_id}\n")
        f.write(f"site_name: {site_name}\n")
        f.write(f"original_filename: {file.filename}\n")
        f.write(f"uploader: {uploader}\n")
        f.write(f"uploaded_at: {datetime.now().isoformat()}\n")
        f.write(f"file_size: {len(content)}\n")

    print(f"[UPLOAD] {safe_site_id}/{new_filename} ({len(content)} bytes) from {uploader}")

    return JSONResponse({
        "success": True,
        "message": "Image uploaded successfully. Pending review.",
        "site_id": safe_site_id,
        "filename": new_filename,
        "size": len(content),
    })


@app.get("/uploads/{site_id}")
async def list_uploads(site_id: str):
    """List pending uploads for a site."""
    safe_site_id = "".join(c for c in site_id if c.isalnum() or c in ('_', '-'))
    site_dir = UPLOAD_DIR / safe_site_id

    if not site_dir.exists():
        return {"site_id": site_id, "uploads": []}

    uploads = []
    for f in site_dir.glob("*"):
        if f.suffix.lower() in ALLOWED_EXTENSIONS:
            uploads.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "uploaded": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })

    return {"site_id": site_id, "uploads": uploads}


@app.get("/health")
async def health():
    return {"status": "ok", "upload_dir": str(UPLOAD_DIR.absolute())}


if __name__ == "__main__":
    print("=" * 60)
    print("ANCIENT NERDS - Image Upload Server")
    print("=" * 60)
    print(f"\nUpload directory: {UPLOAD_DIR.absolute()}")
    print(f"Max file size: {MAX_FILE_SIZE // 1024 // 1024}MB")
    print(f"Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}")
    print("\nEndpoints:")
    print("  POST /upload - Upload an image")
    print("  GET /uploads/{site_id} - List pending uploads")
    print("  GET /health - Health check")
    print("\n" + "=" * 60)

    UPLOAD_DIR.mkdir(exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8001)
