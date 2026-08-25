"""astrapi_sync.modules.folders.ui.files – Dateibrowser für einen Sync-Ordner.

Angelehnt an astrapi-backup's Borg-Archiv-Browser
(astrapi_backup/modules/borg/ui/archives.py, dialogs/archives/*.html) --
gleiches In-App-Modal mit HTMX-Navigation statt eigenständiger Seite.
Hier deutlich einfacher, da immer genau ein Wurzelverzeichnis pro Ordner
existiert (kein Borg-Repo/SSH, direkter Dateisystemzugriff über
folder_path())."""
from datetime import datetime
from pathlib import Path, PurePosixPath

from astrapi_core.system.format import fmt_bytes as _fmt_size
from astrapi_core.ui.render import render
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .crud import api_router as router
from .crud import store


def _fmt_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _dir_listing(root: Path, cur: str) -> tuple[list, list]:
    from astrapi_sync._paths import resolve_within

    target = resolve_within(root, cur) if cur else root
    if not target.is_dir():
        raise HTTPException(404, "Verzeichnis nicht gefunden")
    try:
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        raise HTTPException(403, "Zugriff verweigert")
    dirs, files = [], []
    for e in entries:
        rel = (cur + "/" + e.name).lstrip("/") if cur else e.name
        if e.is_dir():
            dirs.append({"name": e.name, "path": rel})
        else:
            st = e.stat()
            files.append(
                {
                    "name": e.name,
                    "path": rel,
                    "size_fmt": _fmt_size(st.st_size),
                    "mtime": _fmt_mtime(st.st_mtime),
                }
            )
    return dirs, files


def _browse_ctx(item_id: str, folder: dict, path: str) -> dict:
    from astrapi_sync._paths import folder_path

    root = folder_path(item_id)
    cur = path.strip("/")
    error = None
    dirs, files = [], []
    try:
        dirs, files = _dir_listing(root, cur)
    except HTTPException as exc:
        error = exc.detail

    crumbs = [{"label": "Wurzel", "path": ""}]
    acc = ""
    for part in PurePosixPath(cur).parts if cur else []:
        acc = (acc + "/" + part).lstrip("/")
        crumbs.append({"label": part, "path": acc})
    parent_path = None
    if cur:
        p = str(PurePosixPath(cur).parent)
        parent_path = "" if p == "." else p

    return {
        "item_id": item_id,
        "description": folder.get("description") or item_id,
        "path": cur,
        "breadcrumbs": crumbs,
        "dirs": dirs,
        "files": files,
        "parent_path": parent_path,
        "error": error,
    }


@router.get("/{item_id}/files", response_class=HTMLResponse)
def files_modal(item_id: str, request: Request):
    folder = store.get(item_id)
    if folder is None:
        raise HTTPException(404, "Ordner nicht gefunden")
    return render(request, "folders/dialogs/files/modal.html", _browse_ctx(item_id, folder, ""))


@router.get("/{item_id}/files/browse", response_class=HTMLResponse)
def files_browse(item_id: str, request: Request, path: str = ""):
    folder = store.get(item_id)
    if folder is None:
        raise HTTPException(404, "Ordner nicht gefunden")
    return render(request, "folders/dialogs/files/browse.html", _browse_ctx(item_id, folder, path))


@router.get("/{item_id}/files/download")
def files_download(item_id: str, path: str):
    from astrapi_sync._paths import folder_path, resolve_within

    folder = store.get(item_id)
    if folder is None:
        raise HTTPException(404, "Ordner nicht gefunden")
    clean = path.strip("/")
    if not clean or any(part == ".." for part in PurePosixPath(clean).parts):
        raise HTTPException(400, "Ungültiger Pfad")
    target = resolve_within(folder_path(item_id), clean)
    if not target.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(str(target), filename=target.name)
