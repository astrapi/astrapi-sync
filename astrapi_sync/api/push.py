# astrapi_sync/api/push.py
"""UnifiedPush-Weckruf für die Android-App bei Datei-/Ordneränderungen.

Ergänzt das bestehende ws_manager.py-Push (Phase 3, nur für den Linux-CLI-
Daemon mit Dauerverbindung) um einen Weg für Android, das aus Akku-Gründen
keine eigene Dauerverbindung hält (siehe astrapi-hub-Vault, projects/sync).
Bewusst NICHT über astrapi_core.modules.notify -- dessen send() sendet über
global admin-konfigurierte Kanäle/Jobs, nicht pro-Gerät-individuell an eine
bei der Registrierung erhaltene Endpoint-URL.

UnifiedPush-Protokoll: einfacher HTTP POST an die geräteindividuelle
Endpoint-URL, kein Auth-Header nötig (die URL selbst ist die Berechtigung),
Body darf leer sein -- der Push ist nur ein Weckruf, der Client holt sich
die eigentlichen Daten selbst per Sync.
"""
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


def get_push_targets(folder_id: str, exclude_device_id: str) -> list[str]:
    """Synchroner Teil (schneller lokaler DB-Zugriff) -- läuft im
    Request-Kontext, VOR dem Einreihen der eigentlichen HTTP-Calls als
    BackgroundTask. Schließt das auslösende Gerät selbst aus (das kennt
    die eigene Änderung ja bereits)."""
    from astrapi_sync.modules.devices.ui.crud import store as devices_store

    targets = []
    for device_id, device in devices_store.list().items():
        if device_id == exclude_device_id:
            continue
        if not device.get("enabled", True):
            continue
        if folder_id not in (device.get("folder_ids") or []):
            continue
        url = device.get("unifiedpush_endpoint_url") or ""
        if url:
            targets.append(url)
    return targets


def post_push(endpoint_url: str) -> None:
    """Reiner Weckruf-POST, läuft als BackgroundTask nach dem Response-
    Versand. Darf den eigentlichen Sync-Request nie stören -- Fehler
    werden nur geloggt, nie weitergeworfen (Muster wie
    sync.py::_notify_new_device())."""
    try:
        req = urllib.request.Request(url=endpoint_url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if not (200 <= resp.status < 300):
                log.warning("unifiedpush: unerwarteter Status %s für %s", resp.status, endpoint_url)
    except urllib.error.URLError as e:
        log.warning("unifiedpush: Push an %s fehlgeschlagen: %s", endpoint_url, e)
    except Exception as e:
        log.warning("unifiedpush: unerwarteter Fehler bei Push an %s: %s", endpoint_url, e)
