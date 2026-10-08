from fastapi import APIRouter, File, UploadFile, HTTPException, status
import io

router = APIRouter(prefix="/files", tags=["files"])

@router.post("/extract-text")
async def extract_text(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    filename = file.filename.lower()
    
    if filename.endswith(".md"):
        content = await file.read()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Invalid Markdown file encoding (must be UTF-8).")
            
    elif filename.endswith(".pdf"):
        import pypdf
        content = await file.read()
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
            text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e}")
            
    elif filename.endswith(".docx"):
        import docx
        content = await file.read()
        try:
            doc = docx.Document(io.BytesIO(content))
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse DOCX: {e}")
            
    else:
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file type. Only .pdf, .docx, and .md are supported."
        )
        
    return {"text": text}

import os
import shutil
import uuid
from fastapi.responses import FileResponse

UPLOAD_DIR = "/tmp/veritas_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload-media")
async def upload_media(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{uuid.uuid4()}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    
    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Using localhost for simplicity as the backend fetches it. 
    # The frontend can also use this URL if it runs on localhost.
    return {"url": f"http://localhost:8000/api/v1/files/media/{filename}"}

@router.get("/media/{filename}")
async def get_media(filename: str):
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
