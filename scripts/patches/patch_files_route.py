import re

with open("backend/app/api/v1/routes/files.py", "r") as f:
    content = f.read()

# Replace the pypdf block with pdfplumber
old_pdf_block = """    elif filename.endswith(".pdf"):
        import pypdf
        content = await file.read()
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
            text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\\n"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e}")"""

new_pdf_block = """    elif filename.endswith(".pdf"):
        import pdfplumber
        content = await file.read()
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text = ""
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\\n"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e}")"""

content = content.replace(old_pdf_block, new_pdf_block)

with open("backend/app/api/v1/routes/files.py", "w") as f:
    f.write(content)
