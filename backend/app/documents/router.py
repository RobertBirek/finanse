from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    return JSONResponse(
        content={
            "message": "Upload endpoint — stub",
            "filename": file.filename,
            "content_type": file.content_type,
        },
        status_code=202,
    )


@router.get("/documents")
async def list_documents(current_user: User = Depends(get_current_user)):
    return {"documents": [], "message": "Document listing — stub"}
