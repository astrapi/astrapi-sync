# astrapi_sync/api/auth.py
"""Geräte-Authentifizierung für die Sync-API.

astrapi-core kennt keinerlei Auth-Konzept (kein Login, keine Sessions,
keine API-Keys) -- komplett neu für dieses Projekt gebaut. Ein Gerät
weist sich mit einem Bearer-Token aus (`Authorization: Bearer <token>`),
das beim Pairing einmalig im Klartext ausgegeben und seither nur noch als
SHA256-Hash gespeichert wird (wie ein Passwort).
"""
import hashlib
import time

from fastapi import Header, HTTPException, Path


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_device_by_token(token: str) -> tuple[str, dict] | None:
    from astrapi_sync.modules.devices.ui.crud import store as devices_store

    token_hash = hash_token(token)
    for device_id, device in devices_store.list().items():
        if device.get("token_hash") == token_hash:
            return device_id, device
    return None


def authenticate(token: str) -> tuple[str, dict]:
    """Prüft ein rohes Token (ohne "Bearer "-Präfix), aktualisiert last_seen.

    Gibt (device_id, device_dict) zurück oder wirft HTTPException.
    """
    from astrapi_sync.modules.devices.ui.crud import store as devices_store

    found = get_device_by_token(token)
    if found is None:
        raise HTTPException(401, "Ungültiges Geräte-Token")
    device_id, device = found
    if not device.get("enabled", True):
        raise HTTPException(403, "Gerät ist deaktiviert")

    devices_store.update(device_id, {"last_seen": time.strftime("%Y-%m-%d %H:%M:%S")})
    return device_id, device


def require_device_only(authorization: str = Header(default="")) -> tuple[str, dict]:
    """Dependency für Endpunkte ohne folder_id (z.B. GET /api/sync/folders)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Kein Geräte-Token angegeben")
    return authenticate(authorization.removeprefix("Bearer ").strip())


def require_device(
    folder_id: str = Path(...),
    authorization: str = Header(default=""),
) -> tuple[str, dict]:
    """Dependency für Sync-Endpunkte unter /api/sync/folders/{folder_id}/...

    Gibt (device_id, device_dict) zurück, wenn das Token gültig ist, das
    Gerät aktiviert ist und Zugriff auf diesen Ordner hat.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Kein Geräte-Token angegeben")
    token = authorization.removeprefix("Bearer ").strip()

    device_id, device = authenticate(token)
    if folder_id not in (device.get("folder_ids") or []):
        raise HTTPException(403, "Gerät hat keinen Zugriff auf diesen Ordner")
    return device_id, device
