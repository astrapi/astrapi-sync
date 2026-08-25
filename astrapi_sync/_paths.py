# astrapi_sync/_paths.py
from pathlib import Path

from fastapi import HTTPException

from astrapi_core.system.paths import db_path, log_dir, work_dir  # noqa: F401 – re-export


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent


def extra_disk_options() -> list[str]:
    """Alle konfigurierten Zusatzspeicher-Pfade (Einstellungen -> System ->
    "Zusätzlicher Speicher", core-weites Setting system.extra_disks).

    get_module() liefert für type:list-Settings eine echte Python-Liste
    zurück (astrapi_mirror._paths::_extra_disk() geht von einem
    Komma-String aus und würde bei einer echten Liste mit AttributeError
    abstürzen -- hier bewusst robust gegen beide Formen).
    """
    from astrapi_core.ui.settings_registry import get_module

    raw = get_module("system", "extra_disks", default=[]) or []
    if isinstance(raw, str):
        raw = raw.split(",")
    return [p.strip() for p in raw if p and p.strip()]


def folder_base(storage_location: str) -> Path:
    """Wurzelverzeichnis für einen gegebenen Speicherort ("" = Standard,
    sonst einer der konfigurierten Zusatzspeicher-Pfade)."""
    if storage_location:
        return Path(storage_location).resolve() / "astrapi-sync"
    return work_dir().resolve() / "folders"


def resolve_within(root: Path, rel_path: str) -> Path:
    """Löst rel_path sicher innerhalb von root auf, wirft 400 bei Path-Traversal.

    Vergleicht die echte Path.parents-Hierarchie statt eines String-Präfix
    (der z.B. Ordner "1" und "18" verwechseln würde, da ".../18" textuell
    mit ".../1" beginnt -- siehe T-213-SYNC).
    """
    root = root.resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(400, "Ungültiger Pfad")
    return target


def folder_path(folder_id) -> Path:
    """Plattenpfad eines einzelnen Sync-Ordners -- abhängig von dessen
    eigenem storage_location-Feld (nicht global), legt ihn bei Bedarf an.

    Ordner werden nach ihrer numerischen ID benannt (nicht nach dem
    änderbaren Namen) -- stabil auch wenn der Anzeigename später geändert
    wird.
    """
    from astrapi_sync.modules.folders.ui.crud import store as folders_store

    folder = folders_store.get(str(folder_id)) or {}
    location = folder.get("storage_location") or ""
    p = folder_base(location) / str(folder_id)
    p.mkdir(parents=True, exist_ok=True)
    return p
