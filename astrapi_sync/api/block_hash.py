# astrapi_sync/api/block_hash.py
"""Block-Hashing für Delta-Sync.

Syncthing-Stil: feste Blockgröße, SHA256 je Block, Vergleich per Position
-- kein rsync-Rolling-Hash (der auch Byte-Verschiebungen mitten in der
Datei erkennen würde, dafür deutlich komplexer ist). Bewusste
Vereinfachung, siehe Architektur-Abschnitt im Plan.

Kein persistenter Hash-Cache in dieser Phase -- Hashes werden bei jeder
Index-Anfrage neu berechnet. Für sehr große, selten geänderte Dateien
später ggf. über (Pfad, mtime, Größe) cachen.
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


def file_entry(path: Path, rel_path: str, block_size: int = DEFAULT_BLOCK_SIZE) -> dict:
    stat = path.stat()
    return {
        "path": rel_path,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "block_size": block_size,
        "sha256": whole_file_hash(path),
        "blocks": hash_blocks(path, block_size),
    }


def build_index(root: Path, block_size: int = DEFAULT_BLOCK_SIZE) -> list[dict]:
    """Läuft den Ordnerbaum ab, gibt eine Liste von file_entry()-Dicts zurück."""
    entries = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        entries.append(file_entry(p, p.relative_to(root).as_posix(), block_size))
    return entries
