# astrapi_sync/api/sync.py
"""Client-seitige Sync-API.

Phase 1: Pairing. Phase 2: Datei-Index + Block-Delta-Upload/Download/Delete.
Phase 3: WebSocket-Push bei Änderungen.
"""
import json
import logging
import os
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
from astrapi_sync.api.block_hash import DEFAULT_BLOCK_SIZE, build_dir_index, build_index, whole_file_hash
from astrapi_sync.api.ws_manager import manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


# ── Pairing (Phase 1) ────────────────────────────────────────────────────────


class PairRequest(BaseModel):
    token: str
    description: str = ""
    platform: str = ""


def _notify_new_device(description: str, platform: str) -> None:
    """Benachrichtigt (falls konfiguriert) ueber ein frisch gepairtes Gerät --
    nur fuer echte Neuzugaenge, nicht fuer "Neu verbinden" (Token-Ersatz
    eines bereits bekannten Geraets, siehe pair()). Wie in den anderen
    astrapi-Apps ueblich (z.B. astrapi_mirror/modules/debian/jobs.py) ohne
    register_source() -- ein reiner String-Schluessel reicht fuer die
    Job-Filterung in notify.send(), eine Fehlermeldung darf den Pairing-
    Vorgang selbst nicht verhindern."""
    try:
        from astrapi_core.modules.notify import engine as notify_engine

        notify_engine.send(
            title="Neues Gerät verbunden",
            message=f"„{description}“ ({platform or 'unbekannte Plattform'}) hat sich mit astrapi-sync gekoppelt.",
            event=notify_engine.INFO,
            source="devices",
            tags=["gerät", "pairing"],
        )
    except Exception as e:
        log.warning("notify: Benachrichtigung für neues Gerät fehlgeschlagen: %s", e)


@router.post("/pair")
def pair(payload: PairRequest):
    from astrapi_core.system.activity_log import log_activity

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
        log_activity(
            log_type="job",
            module="devices",
            item_id=str(existing_device_id),
            description=f"Gerät „{existing.get('description') or existing_device_id}“ neu verbunden",
            status="ok",
        )
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
    log_activity(
        log_type="job",
        module="devices",
        item_id=str(item_id),
        description=f"Neues Gerät „{payload.description or 'Neues Gerät'}“ gepairt",
        status="ok",
    )
    _notify_new_device(payload.description or "Neues Gerät", payload.platform)

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
    return {"files": build_index(root), "dirs": build_dir_index(root)}


def _resolve_file_path(folder_id: str, rel_path: str) -> PPath:
    """Löst einen relativen Client-Pfad sicher innerhalb des Sync-Ordners auf."""
    from astrapi_sync._paths import folder_path, resolve_within

    return resolve_within(folder_path(folder_id), rel_path)


# ── Download (Phase 2) ───────────────────────────────────────────────────────


@router.get("/folders/{folder_id}/files/{rel_path:path}")
def download_file(folder_id: str, rel_path: str, device=Depends(require_device)):
    from astrapi_sync._paths import folder_lock

    # Lock nur um Pfadauflösung + Existenz-Check -- das eigentliche
    # Streamen der Antwort passiert danach außerhalb, siehe T-219-SYNC
    # (dort auch die Einschränkung dazu dokumentiert).
    with folder_lock(folder_id):
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

    block_size = int(info.get("block_size") or DEFAULT_BLOCK_SIZE)
    blocks: list[str] = info.get("blocks") or []
    changed: list[int] = info.get("changed") or []
    size = int(info.get("size") or 0)
    expected = info.get("expected_server_sha256")

    # Upload-Payload VOR dem Lock einlesen -- das Warten auf Netzwerk-Bytes
    # soll den Ordner nicht fuer andere Requests blockieren.
    changed_bytes = await data.read() if data is not None else b""

    from astrapi_sync._paths import folder_lock

    with folder_lock(folder_id):
        target = _resolve_file_path(folder_id, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Konflikt-Erkennung: Client kennt den Server-Hash, den er zuletzt
        # gesehen hat (leer bei neuer Datei). Weicht der TATSÄCHLICHE
        # aktuelle Server-Stand davon ab, hat sich die Datei serverseitig
        # seit dem letzten bekannten Sync-Stand des Clients geändert --
        # echter Konflikt, kein einfaches "neuer gewinnt". Client muss die
        # Kopie selbst als *.syncconflict sichern und erneut versuchen.
        if target.is_file():
            current_hash = whole_file_hash(target)
            if expected is not None and current_hash != expected:
                raise HTTPException(
                    409,
                    "Konflikt: Datei wurde serverseitig seit dem letzten bekannten Stand geändert",
                )

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
        # Temp-Datei + os.replace() statt direktem write_bytes() -- ein
        # Absturz mitten im Schreiben hinterlaesst sonst eine halb
        # geschriebene Datei ohne Wiederherstellung (T-224-SYNC, analog
        # zum bereits atomaren Client-Download-Pfad in api_client.py).
        tmp_target = target.with_name(f".{target.name}.tmp-{os.getpid()}")
        tmp_target.write_bytes(bytes(buf))

        mtime = info.get("mtime")
        if mtime is not None:
            os.utime(tmp_target, (mtime, mtime))

        os.replace(tmp_target, target)
        new_hash = whole_file_hash(target)

    await manager.broadcast(folder_id, {"event": "changed", "path": rel_path})
    return {"status": "ok", "sha256": new_hash}


# ── Löschen (Phase 2) ────────────────────────────────────────────────────────


@router.delete("/folders/{folder_id}/files/{rel_path:path}")
async def delete_file(folder_id: str, rel_path: str, device=Depends(require_device)):
    from astrapi_sync._paths import folder_lock

    with folder_lock(folder_id):
        target = _resolve_file_path(folder_id, rel_path)
        if target.is_file():
            target.unlink()
    await manager.broadcast(folder_id, {"event": "deleted", "path": rel_path})
    return {"status": "ok"}


# ── Leere Verzeichnisse (Phase 2) ────────────────────────────────────────────
# Nicht-leere Verzeichnisse werden implizit über Datei-Pfade angelegt
# (upload_file() macht target.parent.mkdir(parents=True)) -- diese beiden
# Routen decken nur den Fall ab, dass ein Verzeichnis GAR KEINE Datei
# enthält und sonst nie im Index auftauchen würde.


@router.post("/folders/{folder_id}/dirs/{rel_path:path}")
async def create_dir(folder_id: str, rel_path: str, device=Depends(require_device)):
    from astrapi_sync._paths import folder_lock

    with folder_lock(folder_id):
        target = _resolve_file_path(folder_id, rel_path)
        target.mkdir(parents=True, exist_ok=True)
    await manager.broadcast(folder_id, {"event": "dir_created", "path": rel_path})
    return {"status": "ok"}


@router.delete("/folders/{folder_id}/dirs/{rel_path:path}")
async def delete_dir(folder_id: str, rel_path: str, device=Depends(require_device)):
    from astrapi_sync._paths import folder_lock

    deleted = False
    with folder_lock(folder_id):
        target = _resolve_file_path(folder_id, rel_path)
        if target.is_dir():
            try:
                target.rmdir()
                deleted = True
            except OSError:
                # nicht (mehr) leer -- z.B. zwischenzeitlich im selben Lauf
                # eine Datei hineingelegt; niemals rekursiv löschen. Client
                # bekommt deleted=False zurück und weiß so, dass hier
                # tatsächlich nichts entfernt wurde (kein Fantom-Löschen im
                # Ergebnis-Report).
                pass
    if deleted:
        await manager.broadcast(folder_id, {"event": "dir_deleted", "path": rel_path})
    return {"status": "ok", "deleted": deleted}


# ── Sync-Zusammenfassung fürs Activity Log ──────────────────────────────────
# Der Server sieht nur einzelne Datei-/Verzeichnis-Requests, kein Konzept
# von "ein Sync-Lauf" -- das kennt nur der Client (sync_folder_once()).
# Der Client meldet daher explizit einmal pro Lauf eine Zusammenfassung,
# statt dass der Server versucht, Lauf-Grenzen aus Request-Timing zu raten.


class SyncSummary(BaseModel):
    uploaded: int = 0
    downloaded: int = 0
    deleted_local: int = 0
    deleted_remote: int = 0
    conflicts: int = 0


@router.post("/folders/{folder_id}/sync-log")
def log_sync_summary(folder_id: str, summary: SyncSummary, device=Depends(require_device)):
    from astrapi_core.system.activity_log import log_activity

    device_id, dev = device
    total = summary.uploaded + summary.downloaded + summary.deleted_local + summary.deleted_remote
    if total == 0:
        return {"status": "ok", "logged": False}

    parts = []
    if summary.uploaded:
        parts.append(f"{summary.uploaded} hochgeladen")
    if summary.downloaded:
        parts.append(f"{summary.downloaded} heruntergeladen")
    deleted = summary.deleted_local + summary.deleted_remote
    if deleted:
        parts.append(f"{deleted} gelöscht")
    if summary.conflicts:
        parts.append(f"{summary.conflicts} Konflikt(e)")

    device_label = dev.get("description") or device_id
    log_activity(
        log_type="job",
        module="folders",
        item_id=folder_id,
        description=f"Sync von „{device_label}“: " + ", ".join(parts),
        status="warning" if summary.conflicts else "ok",
        items_count=total,
        metadata={"device_id": device_id, "device": device_label, **summary.model_dump()},
    )
    return {"status": "ok", "logged": True}


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
