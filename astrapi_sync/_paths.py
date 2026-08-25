# astrapi_sync/_paths.py
from pathlib import Path

from astrapi_core.system.paths import db_path, log_dir, work_dir  # noqa: F401 – re-export


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent


def _extra_disk() -> str:
    """Gibt den ersten konfigurierten Zusatzspeicher zurück, oder ''.

    Die Einstellung "Zusätzlicher Speicher" (system.extra_disks) ist ein
    core-weites System-Setting (astrapi_core/modules/system/config/settings.yaml,
    type: list), in jeder astrapi-App automatisch unter Einstellungen ->
    System verfügbar. get_module() liefert für type:list-Settings eine
    echte Python-Liste zurück (astrapi_mirror._paths::_extra_disk() geht
    von einem Komma-String aus und würde bei einer echten Liste mit
    AttributeError abstürzen -- hier bewusst robust gegen beide Formen).
    """
    from astrapi_core.ui.settings_registry import get_module

    raw = get_module("system", "extra_disks", default=[]) or []
    if isinstance(raw, str):
        raw = raw.split(",")
    for path in raw:
        path = (path or "").strip()
        if path:
            return path
    return ""


def folders_root() -> Path:
    """Wurzelverzeichnis, unter dem jeder Sync-Ordner sein eigenes Unterverzeichnis hat."""
    disk = _extra_disk()
    if disk:
        return Path(disk).resolve() / "astrapi-sync"
    return work_dir().resolve() / "folders"


def folder_path(folder_id) -> Path:
    """Plattenpfad eines einzelnen Sync-Ordners. Legt ihn bei Bedarf an.

    Ordner werden nach ihrer numerischen ID benannt (nicht nach dem
    änderbaren Label) -- stabil auch wenn der Anzeigename später geändert
    wird.
    """
    p = folders_root() / str(folder_id)
    p.mkdir(parents=True, exist_ok=True)
    return p
