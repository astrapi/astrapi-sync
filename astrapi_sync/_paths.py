# astrapi_sync/_paths.py
import threading
from pathlib import Path

from fastapi import HTTPException

from astrapi_core.system.paths import db_path, log_dir, work_dir  # noqa: F401 – re-export

_folder_locks: dict[str, threading.Lock] = {}
_folder_locks_guard = threading.Lock()


def folder_lock(folder_id) -> threading.Lock:
    """Ein Lock pro Sync-Ordner -- serialisiert Dateisystem-Operationen auf
    demselben Ordner (Sync-API-Endpunkte, Speicherort-Verschieben).

    threading.Lock statt asyncio.Lock, da sowohl synchrone (im Threadpool
    laufende) als auch async-def-Endpunkte denselben Lock nutzen müssen --
    ein asyncio.Lock wäre aus einem synchronen def-Endpunkt heraus nicht
    sauber nutzbar. Ein-Prozess-Deployment (siehe ws_manager.py), kein
    Multi-Worker -- ein simpler In-Memory-Dict reicht (T-219-SYNC).
    """
    folder_id = str(folder_id)
    with _folder_locks_guard:
        return _folder_locks.setdefault(folder_id, threading.Lock())


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent


def folder_base() -> Path:
    """Wurzelverzeichnis aller Sync-Ordner. Zusatzspeicher ist Pflicht
    (kein stiller Rückfall aufs Arbeitsverzeichnis, T-24X-SYNC) -- eigenes
    Unterverzeichnis, da "Zusätzlicher Speicher" ein core-weites Setting
    ist, das eine andere astrapi-App auf demselben Datenträger ebenfalls
    nutzen könnte."""
    from astrapi_core.system.paths import require_extra_disk

    return Path(require_extra_disk()).resolve() / "astrapi-sync"


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
    """Plattenpfad eines einzelnen Sync-Ordners, legt ihn bei Bedarf an.

    Ordner werden nach ihrer numerischen ID benannt (nicht nach dem
    änderbaren Namen) -- stabil auch wenn der Anzeigename später geändert
    wird.
    """
    p = folder_base() / str(folder_id)
    p.mkdir(parents=True, exist_ok=True)
    return p
