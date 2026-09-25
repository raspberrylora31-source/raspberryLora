"""Message history and send-to-mesh."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import SendMessageRequest
from app.services.meshtastic_service import radio_service
from app.services.packet_service import list_messages, message_to_dict

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("")
def api_list_messages(limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db)) -> dict:
    rows = [message_to_dict(m) for m in list_messages(db, limit)]
    return {"messages": rows, "count": len(rows)}


@router.post("/send")
def api_send_message(body: SendMessageRequest) -> dict:
    try:
        payload = radio_service.send_text(
            body.text,
            destination=body.destination,
            channel_index=body.channel_index,
            want_ack=body.want_ack,
        )
        return {"ok": True, "message": payload}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Send failed: {exc}") from exc
