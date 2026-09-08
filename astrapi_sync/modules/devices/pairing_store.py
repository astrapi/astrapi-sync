# astrapi_sync/modules/devices/pairing_store.py
"""In-Memory-Speicher für kurzlebige Pairing-Tokens.

Bewusst nicht in der DB: Pairing-Tokens sind einmalig, laufen nach 10
Minuten ab und müssen keinen Neustart überleben (dann erzeugt man einfach
einen neuen). Passt zum Ein-Prozess-Deployment-Stil der bestehenden
astrapi-Apps (siehe astrapi_core.system.paths.run_app()).

Zwei Varianten:
- Neues Gerät (device_id=None): /api/sync/pair legt eine neue devices-
  Zeile an.
- Neu verbinden (device_id gesetzt): /api/sync/pair ersetzt nur das
  Token EINES bestehenden Geräts -- Plattform/Beschreibung/Ordner-Zugriff
  bleiben unangetastet.
"""

import secrets
import time

_TTL_SECONDS = 600

# token -> {"created_at": float, "device_id": str | None, "owner_user_id": int | None}
_pending: dict[str, dict] = {}


def create_pairing_token(device_id: str | None = None, owner_user_id: int | None = None) -> str:
    """owner_user_id: bei Neu-Pairing (device_id=None) der einladende
    Web-Nutzer -- /api/sync/pair() ordnet das neue Gerät und dessen
    Default-Ordner diesem Nutzer zu (Mandantentrennung, T-Multi-User)."""
    _cleanup()
    token = secrets.token_urlsafe(24)
    _pending[token] = {"created_at": time.time(), "device_id": device_id, "owner_user_id": owner_user_id}
    return token


def redeem_pairing_token(token: str) -> dict | None:
    """Entfernt den Token (Einmal-Nutzung) und gibt seine Metadaten zurück,
    oder None wenn er ungültig/abgelaufen ist."""
    _cleanup()
    return _pending.pop(token, None)


def _cleanup() -> None:
    now = time.time()
    expired = [t for t, meta in _pending.items() if now - meta["created_at"] > _TTL_SECONDS]
    for t in expired:
        _pending.pop(t, None)


def ttl_seconds() -> int:
    return _TTL_SECONDS
