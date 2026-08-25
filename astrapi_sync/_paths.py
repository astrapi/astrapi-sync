# astrapi_sync/_paths.py
from pathlib import Path

from astrapi_core.system.paths import db_path, log_dir, work_dir  # noqa: F401 – re-export


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent


def folders_root() -> Path:
    """Wurzelverzeichnis, unter dem jeder Sync-Ordner sein eigenes Unterverzeichnis hat."""
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
