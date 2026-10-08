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
