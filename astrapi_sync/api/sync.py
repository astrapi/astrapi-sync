# astrapi_sync/api/sync.py
"""Client-seitige Sync-API.

Phase 1: Pairing. Phase 2: Datei-Index + Block-Delta-Upload/Download/Delete.
Phase 3: WebSocket-Push bei Änderungen.
"""
import json
import secrets
from pathlib import Path as PPath

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel

from astrapi_sync.api.auth import authenticate, hash_token, require_device, require_device_only
from astrapi_sync.api.block_hash import DEFAULT_BLOCK_SIZE, build_index, whole_file_hash
from astrapi_sync.api.ws_manager import manager

router = APIRouter(prefix="/api/sync", tags=["sync"])


# ── Pairing (Phase 1) ────────────────────────────────────────────────────────


class PairRequest(BaseModel):
    token: str
    description: str = ""
    platform: str = ""


@router.post("/pair")
def pair(payload: PairRequest):
    from astrapi_sync.modules.devices.pairing_store import redeem_pairing_token
    from astrapi_sync.modules.devices.ui.crud import store as devices_store
    from astrapi_sync.modules.folders.ui.crud import folders_for_select

    pairing_info = redeem_pairing_token(payload.token)
    if pairing_info is None:
        raise HTTPException(400, "Ungültiger oder abgelaufener Pairing-Code")

    device_token = secrets.token_urlsafe(32)
    existing_device_id = pairing_info.get("device_id")

    if existing_device_id is not None:
        # Neu verbinden: nur das Token ersetzen, Plattform/Beschreibung/
        # Ordner-Zugriff bleiben unangetastet (siehe devices/ui/pairing.py).
        existing = devices_store.get(existing_device_id)
        if existing is None:
            raise HTTPException(404, "Gerät wurde inzwischen gelöscht")
        devices_store.update(existing_device_id, {"token_hash": hash_token(device_token)})
        return {
            "device_id": existing_device_id,
            "device_token": device_token,
            "folder_ids": existing.get("folder_ids") or [],
        }

    folder_ids = [str(f["value"]) for f in folders_for_select(enabled_only=True)]

    item_id = devices_store.create(
        None,
        {
            "description": payload.description or "Neues Gerät",
            "platform": payload.platform or "",
            "folder_ids": folder_ids,
            "token_hash": hash_token(device_token),
            "last_seen": "",
            "enabled": True,
        },
    )

    return {
        "device_id": item_id,
        "device_token": device_token,
        "folder_ids": folder_ids,
    }


# ── Ordner-Liste (Phase 2) ───────────────────────────────────────────────────


@router.get("/folders")
def list_folders(device=Depends(require_device_only)):
    from astrapi_sync.modules.folders.ui.crud import store as folders_store

    _device_id, dev = device
    allowed = set(dev.get("folder_ids") or [])
    return {
        "folders": [
            {"id": fid, "description": f.get("description") or fid}
            for fid, f in folders_store.list().items()
            if fid in allowed
        ]
    }


# ── Datei-Index (Phase 2) ────────────────────────────────────────────────────


@router.get("/folders/{folder_id}/index")
def get_index(folder_id: str, device=Depends(require_device)):
    from astrapi_sync._paths import folder_path

    root = folder_path(folder_id)
    return {"files": build_index(root)}


def _resolve_file_path(folder_id: str, rel_path: str) -> PPath:
    """Löst einen relativen Client-Pfad sicher innerhalb des Sync-Ordners auf.

    Verhindert Path-Traversal (z.B. "../../etc/passwd") -- der aufgelöste
    Pfad muss innerhalb von folder_path(folder_id) liegen.
    """
    from astrapi_sync._paths import folder_path

    root = folder_path(folder_id).resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(400, "Ungültiger Pfad")
    return target


# ── Download (Phase 2) ───────────────────────────────────────────────────────


@router.get("/folders/{folder_id}/files/{rel_path:path}")
def download_file(folder_id: str, rel_path: str, device=Depends(require_device)):
    target = _resolve_file_path(folder_id, rel_path)
    if not target.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(str(target))


# ── Upload (Phase 2) ─────────────────────────────────────────────────────────


@router.post("/folders/{folder_id}/files/{rel_path:path}")
async def upload_file(
    folder_id: str,
    rel_path: str,
    meta: str = Form(...),
    data: UploadFile | None = File(default=None),
    device=Depends(require_device),
):
    """Multipart-Upload: `meta` (JSON-Formularfeld) beschreibt die Ziel-
    Blockliste, `data` enthält die rohen Bytes NUR der geänderten Blöcke,
    hintereinander in Reihenfolge der `changed`-Indizes. Unveränderte
    Blöcke bleiben in der bestehenden Datei einfach stehen.

    meta = {
        "size": int, "mtime": float, "block_size": int,
        "blocks": [sha256, ...],   # Ziel-Zustand, komplette Liste
        "changed": [int, ...],     # Indizes, für die `data` Bytes enthält
        "expected_server_sha256": str | null,  # Konflikt-Check, siehe unten
    }
    """
    try:
        info = json.loads(meta)
    except json.JSONDecodeError:
        raise HTTPException(400, "meta ist kein gültiges JSON")

    target = _resolve_file_path(folder_id, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    block_size = int(info.get("block_size") or DEFAULT_BLOCK_SIZE)
    blocks: list[str] = info.get("blocks") or []
    changed: list[int] = info.get("changed") or []
    size = int(info.get("size") or 0)

    # Konflikt-Erkennung: Client kennt den Server-Hash, den er zuletzt
    # gesehen hat (leer bei neuer Datei). Weicht der TATSÄCHLICHE
    # aktuelle Server-Stand davon ab, hat sich die Datei serverseitig seit
    # dem letzten bekannten Sync-Stand des Clients geändert -- echter
    # Konflikt, kein einfaches "neuer gewinnt". Client muss die Kopie
    # selbst als *.syncconflict sichern und erneut versuchen.
    expected = info.get("expected_server_sha256")
    if target.is_file():
        current_hash = whole_file_hash(target)
        if expected is not None and current_hash != expected:
            raise HTTPException(
                409,
                "Konflikt: Datei wurde serverseitig seit dem letzten bekannten Stand geändert",
            )

    changed_bytes = await data.read() if data is not None else b""
    offsets = {idx: pos for pos, idx in enumerate(sorted(changed))}

    # Bestehenden Inhalt (falls vorhanden) als Basis nehmen, unveränderte
    # Bereiche bleiben unangetastet -- nur die geänderten Blockpositionen
    # werden überschrieben.
    existing = target.read_bytes() if target.is_file() else b""
    buf = bytearray(existing)
    if len(buf) < size:
        buf.extend(b"\x00" * (size - len(buf)))

    for idx in sorted(changed):
        start = idx * block_size
        end = min(start + block_size, size)
        chunk_start = offsets[idx] * block_size
        chunk = changed_bytes[chunk_start : chunk_start + (end - start)]
        buf[start:end] = chunk

    del buf[size:]
    target.write_bytes(bytes(buf))

    mtime = info.get("mtime")
    if mtime is not None:
        import os

        os.utime(target, (mtime, mtime))

    new_hash = whole_file_hash(target)
    await manager.broadcast(folder_id, {"event": "changed", "path": rel_path})
    return {"status": "ok", "sha256": new_hash}


# ── Löschen (Phase 2) ────────────────────────────────────────────────────────


@router.delete("/folders/{folder_id}/files/{rel_path:path}")
async def delete_file(folder_id: str, rel_path: str, device=Depends(require_device)):
    target = _resolve_file_path(folder_id, rel_path)
    if target.is_file():
        target.unlink()
    await manager.broadcast(folder_id, {"event": "deleted", "path": rel_path})
    return {"status": "ok"}


# ── WebSocket-Push (Phase 3) ─────────────────────────────────────────────────


@router.websocket("/folders/{folder_id}/events")
async def folder_events(websocket: WebSocket, folder_id: str):
    token = websocket.query_params.get("token", "")
    try:
        device_id, device = authenticate(token)
    except HTTPException:
        await websocket.close(code=4401)
        return
    if folder_id not in (device.get("folder_ids") or []):
        await websocket.close(code=4403)
        return

    await manager.connect(folder_id, websocket)
    try:
        while True:
            # Der Client sendet nichts Sinnvolles -- wir warten nur auf
            # Disconnect. receive_text() blockiert, bis die Verbindung
            # endet oder der Client etwas (z.B. einen Ping) schickt.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(folder_id, websocket)
