# astrapi_sync/api/sync.py
"""Client-seitige Sync-API (Phase 1: nur Pairing; Index/Blocks/WebSocket folgen in Phase 2)."""
import hashlib
import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/sync", tags=["sync"])


class PairRequest(BaseModel):
    token: str
    label: str = ""
    platform: str = ""


@router.post("/pair")
def pair(payload: PairRequest):
    from astrapi_sync.modules.devices.pairing_store import redeem_pairing_token
    from astrapi_sync.modules.devices.ui.crud import store as devices_store
    from astrapi_sync.modules.folders.ui.crud import folders_for_select

    if not redeem_pairing_token(payload.token):
        raise HTTPException(400, "Ungültiger oder abgelaufener Pairing-Code")

    device_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(device_token.encode()).hexdigest()
    folder_ids = [str(f["value"]) for f in folders_for_select(enabled_only=True)]

    item_id = devices_store.create(
        None,
        {
            "label": payload.label or "Neues Gerät",
            "platform": payload.platform or "",
            "folder_ids": folder_ids,
            "token_hash": token_hash,
            "last_seen": "",
            "enabled": True,
        },
    )

    return {
        "device_id": item_id,
        "device_token": device_token,
        "folder_ids": folder_ids,
    }
