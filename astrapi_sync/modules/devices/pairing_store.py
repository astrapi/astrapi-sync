# astrapi_sync/modules/devices/pairing_store.py
"""In-Memory-Speicher für kurzlebige Pairing-Tokens.

Bewusst nicht in der DB: Pairing-Tokens sind einmalig, laufen nach 10
Minuten ab und müssen keinen Neustart überleben (dann erzeugt man einfach
einen neuen). Passt zum Ein-Prozess-Deployment-Stil der bestehenden
astrapi-Apps (siehe astrapi_core.system.paths.run_app()).
"""

import secrets
import time

_TTL_SECONDS = 600

# token -> {"created_at": float}
_pending: dict[str, dict] = {}


def create_pairing_token() -> str:
    _cleanup()
    token = secrets.token_urlsafe(24)
    _pending[token] = {"created_at": time.time()}
    return token


def redeem_pairing_token(token: str) -> bool:
    """Gibt True zurück und entfernt den Token, wenn er gültig war (Einmal-Nutzung)."""
    _cleanup()
    return _pending.pop(token, None) is not None


def _cleanup() -> None:
    now = time.time()
    expired = [t for t, meta in _pending.items() if now - meta["created_at"] > _TTL_SECONDS]
    for t in expired:
        _pending.pop(t, None)


def ttl_seconds() -> int:
    return _TTL_SECONDS
