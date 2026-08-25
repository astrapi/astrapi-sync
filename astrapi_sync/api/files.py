"""astrapi_sync.api.files – Nur-Lese-Dateibrowser für Sync-Ordner unter /files/.

Sync-Ordner sind laut Konzept ein echter, durchsuchbarer Verzeichnisbaum
auf Platte, kein Blob-Store -- diese Route macht den Inhalt direkt im
Browser einsehbar, angelehnt an astrapi-mirror's /files/-Browser
(astrapi_mirror/api/repo.py::generic_serve()), aber ohne dessen
OS-Registry/virtuelle-Dateien-Komplexität, da hier immer genau ein
Wurzelverzeichnis pro Ordner existiert.
"""
import html as _html
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

router = APIRouter()

_UNITS = [("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)]

_CSS = """
    @font-face { font-family:'JetBrains Mono'; src:url('/static/fonts/mono.woff2') format('woff2'); }
    :root { --mono:'JetBrains Mono',ui-monospace,monospace; }
    body { font-family:var(--mono); font-size:.85rem; padding:2rem; background:#0d1117; color:#c9d1d9; }
    h1 { color:#58a6ff; margin-bottom:1rem; font-size:1.1rem; }
    p.back { margin-bottom:1rem; font-size:.85rem; }
    table { border-collapse:collapse; width:100%; }
    thead th { text-align:left; padding:.4rem 1rem; border-bottom:2px solid #30363d; color:#8b949e; font-size:.8rem; font-weight:600; letter-spacing:.04em; }
    thead th:last-child { text-align:right; padding-right:2.5rem; }
    td { padding:.35rem 1rem; border-bottom:1px solid #21262d; }
    td.size { text-align:right; color:#8b949e; white-space:nowrap; padding-right:2.5rem; }
    a { text-decoration:none; color:#58a6ff; }
    a:hover { text-decoration:underline; }
"""


def _fmt_size(n: int) -> str:
    for unit, div in _UNITS:
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


def _safe_child(base: Path, *parts: str) -> Path:
    """Gibt aufgelösten Pfad zurück; wirft 400 bei Path-Traversal."""
    resolved = (base / Path(*parts)).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise HTTPException(400, "Ungültiger Pfad")
    return resolved


def _page(title: str, rows_html: str, back: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>{_html.escape(title)}</title><style>{_CSS}</style></head>
<body>
  <p class="back"><a href="{back}">← Zurück</a></p>
  <h1>{_html.escape(title)}</h1>
  <table>
    <thead><tr><th>Name</th><th>Größe</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</body>
</html>"""


@router.get("/files/{folder_id}", include_in_schema=False)
def folder_redirect(folder_id: str):
    return RedirectResponse(f"/files/{folder_id}/", status_code=301)


@router.get("/files/{folder_id}/{path:path}", include_in_schema=False)
def generic_serve(folder_id: str, path: str):
    from astrapi_sync._paths import folder_path
    from astrapi_sync.modules.folders.ui.crud import store as folders_store

    folder = folders_store.get(folder_id)
    if folder is None:
        raise HTTPException(404, f"Ordner nicht konfiguriert: {folder_id}")

    root = folder_path(folder_id)
    path_clean = path.strip("/")
    target = _safe_child(root, path_clean) if path_clean else root

    if target.is_file():
        return FileResponse(str(target), filename=target.name)

    if not target.is_dir():
        raise HTTPException(404, "Nicht gefunden")

    path_clean = path.rstrip("/")
    path_parts = path_clean.split("/") if path_clean else []
    if len(path_parts) > 1:
        back = f"/files/{folder_id}/" + "/".join(path_parts[:-1]) + "/"
    elif path_parts:
        back = f"/files/{folder_id}/"
    else:
        back = "/ui/folders/content"

    title = (folder.get("description") or folder_id) + (f"/{path_clean}" if path_clean else "")

    try:
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        raise HTTPException(403, "Zugriff verweigert")

    prefix = f"/files/{folder_id}"
    rows = []
    for e in entries:
        display = e.name + ("/" if e.is_dir() else "")
        suffix = "/" if e.is_dir() else ""
        href = f"{prefix}/{path_clean}/{e.name}{suffix}" if path_clean else f"{prefix}/{e.name}{suffix}"
        size = "—" if e.is_dir() else _fmt_size(e.stat().st_size)
        rows.append(
            f'<tr><td><a href="{href}">{_html.escape(display)}</a></td>'
            f'<td class="size">{size}</td></tr>'
        )
    return HTMLResponse(_page(title, "\n".join(rows) or "<tr><td colspan='2'>Leer.</td></tr>", back=back))
