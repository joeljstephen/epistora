from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.auth import require_api_key
from app.dependencies import get_database
from app.models.chat import (
    BroadChatRequest,
    ChatSettingsRequest,
    ChatSettingsResponse,
    ConversationCreateRequest,
    ConversationResponse,
    MessageResponse,
    SidebarChatRequest,
)
from app.services.chat_service import (
    broad_chat,
    create_conversation,
    delete_conversation,
    get_chat_settings,
    get_conversation,
    list_conversations,
    list_messages,
    save_chat_settings,
    sidebar_chat,
)
from app.storage.sqlite import Database

router = APIRouter(
    prefix="/studio/chat",
    tags=["studio-chat"],
    dependencies=[Depends(require_api_key)],
)

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "x-vercel-ai-ui-message-stream": "v1",
}


@router.post("/sidebar")
async def sidebar_chat_endpoint(req: SidebarChatRequest, db: Database = Depends(get_database)):
    return StreamingResponse(
        sidebar_chat(db, req),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.post("/broad")
async def broad_chat_endpoint(req: BroadChatRequest, db: Database = Depends(get_database)):
    return StreamingResponse(
        broad_chat(db, req),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def conversations(db: Database = Depends(get_database)):
    return list_conversations(db)


@router.post("/conversations", response_model=ConversationResponse)
async def new_conversation(
    req: ConversationCreateRequest,
    db: Database = Depends(get_database),
):
    return create_conversation(db, req.title)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def conversation_messages(conversation_id: str, db: Database = Depends(get_database)):
    if get_conversation(db, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return list_messages(db, conversation_id)


@router.delete("/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str, db: Database = Depends(get_database)):
    if get_conversation(db, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    delete_conversation(db, conversation_id)
    return {"deleted": True}


@router.get("/settings", response_model=ChatSettingsResponse)
async def chat_settings(db: Database = Depends(get_database)):
    return get_chat_settings(db)


@router.put("/settings", response_model=ChatSettingsResponse)
async def update_chat_settings(
    req: ChatSettingsRequest,
    db: Database = Depends(get_database),
):
    return save_chat_settings(db, req)
