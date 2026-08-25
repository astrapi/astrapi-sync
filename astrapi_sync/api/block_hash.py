# astrapi_sync/api/block_hash.py
"""Block-Hashing für Delta-Sync.

Syncthing-Stil: feste Blockgröße, SHA256 je Block, Vergleich per Position
-- kein rsync-Rolling-Hash (der auch Byte-Verschiebungen mitten in der
Datei erkennen würde, dafür deutlich komplexer ist). Bewusste
Vereinfachung, siehe Architektur-Abschnitt im Plan.

Kein persistenter Hash-Cache in dieser Phase -- Hashes werden bei jeder
Index-Anfrage neu berechnet. Für sehr große, selten geänderte Dateien
später ggf. über (Pfad, mtime, Größe) cachen (T-220-SYNC).
"""
import hashlib
from pathlib import Path

DEFAULT_BLOCK_SIZE = 1 << 20  # 1 MiB


def hash_blocks(path: Path, block_size: int = DEFAULT_BLOCK_SIZE) -> list[str]:
    """Liest eine Datei blockweise, gibt die SHA256-Hashes je Block zurück."""
    hashes = []
    with open(path, "rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            hashes.append(hashlib.sha256(chunk).hexdigest())
    return hashes


def whole_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_file_and_blocks(path: Path, block_size: int = DEFAULT_BLOCK_SIZE) -> tuple[str, list[str]]:
    """Liest die Datei nur EINMAL, liefert Gesamt-Hash und Block-Hashes
    gemeinsam aus denselben gelesenen Chunks -- file_entry() brauchte
    vorher zwei komplett unabhängige Lesedurchläufe über denselben Inhalt
    (whole_file_hash() + hash_blocks()) (T-220-SYNC)."""
    whole = hashlib.sha256()
    blocks = []
    with open(path, "rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            whole.update(chunk)
            blocks.append(hashlib.sha256(chunk).hexdigest())
    return whole.hexdigest(), blocks


def file_entry(path: Path, rel_path: str, block_size: int = DEFAULT_BLOCK_SIZE) -> dict:
    stat = path.stat()
    sha256, blocks = hash_file_and_blocks(path, block_size)
    return {
        "path": rel_path,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "block_size": block_size,
        "sha256": sha256,
        "blocks": blocks,
    }


def build_index(root: Path, block_size: int = DEFAULT_BLOCK_SIZE) -> list[dict]:
    """Läuft den Ordnerbaum ab, gibt eine Liste von file_entry()-Dicts zurück."""
    entries = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        entries.append(file_entry(p, p.relative_to(root).as_posix(), block_size))
    return entries


def build_dir_index(root: Path) -> list[str]:
    """Relative Pfade aller (rekursiv) leeren Verzeichnisse.

    Ein Verzeichnis, das irgendwo in seinem Baum eine Datei enthält, wird
    schon implizit durch deren Pfad mitsynchronisiert (upload_file() legt
    fehlende Elternverzeichnisse an) -- nur komplett leere Verzeichnisse
    tauchen sonst nirgends im Index auf und würden nie propagiert.
    """
    dirs = []
    for p in sorted(root.rglob("*")):
        if p.is_dir() and not any(f.is_file() for f in p.rglob("*")):
            dirs.append(p.relative_to(root).as_posix())
    return dirs
