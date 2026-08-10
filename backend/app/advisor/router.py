from fastapi import APIRouter, Depends

from app.identity.models import User
from app.identity.router import get_current_user
from app.advisor.schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat")
async def chat(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    return {
        "message": "Advisor chat endpoint — stub. OpenAI integration coming soon.",
        "user_message": data.message,
        "conversation_id": str(data.conversation_id) if data.conversation_id else None,
    }
