"""astrapi_sync.api.public_files – Sync-Ordner direkt auf der Wurzel.

Neue Fähigkeit (kein Umzug einer bestehenden Route): der bisherige
Datei-Browser (modules/folders/ui/files.py) ist ein reines In-App-Modal
unter /api/folders/{id}/files/... -- hier kommt eine eigenständige,
"echte" URL dazu (/{folder_id}/{pfad}), fürs direkte Verlinken/Abrufen
einzelner Dateien ohne den Dashboard-Umweg.

Login-pflichtig: RequireLoginMiddleware (auth_middleware.py) schützt
per Default alles außer einer expliziten Ausnahmeliste, diese Routen
stehen bewusst NICHT drauf. Zusätzlich pro Ordner Besitzer-geprüft über
OwnerScopedStore.get() (liefert None für fremde/fremd-eingeloggte
Ordner-IDs) -- ohne das könnte ein eingeloggter Nutzer A die Ordner
von Nutzer B allein durch Erraten der ID sehen.

Wiederverwendet astrapi_core.ui.file_listing fürs Rendering (gleiches
Muster wie astrapi-mirror/astrapi-packages), aber NICHT dessen
safe_child() für die Pfadauflösung -- das prüft nur einen String-Präfix
und hätte denselben Verwechslungsfehler wie vor T-213-SYNC (Ordner "1"
vs "18"). Stattdessen astrapi_sync._paths.resolve_within(), das genau
dafür schon gehärtet ist.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from astrapi_core.ui.file_listing import (
    list_dir_entries,
    render_link_row,
    render_page as _page,
    render_row,
)

router = APIRouter()


def _get_owned_folder(item_id: str) -> dict:
    from astrapi_sync.modules.folders.ui.crud import ui_store as folders_store

    folder = folders_store.get(item_id)
    if folder is None:
        raise HTTPException(404, "Ordner nicht gefunden")
    return folder


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def folders_index():
    from astrapi_sync.modules.folders.ui.crud import ui_store as folders_store

    folders = folders_store.list()
    rows = [
        render_link_row((f.get("description") or str(fid)) + "/", f"/{fid}/")
        for fid, f in sorted(folders.items(), key=lambda kv: (kv[1].get("description") or "").lower())
    ]
    return HTMLResponse(
        _page(
            "Sync",
            "",
            rows,
            col_headers=("Name",),
            empty_message="Keine Ordner.",
        )
    )


@router.get("/{item_id}", include_in_schema=False)
def folder_redirect(item_id: str):
    _get_owned_folder(item_id)
    return RedirectResponse(f"/{item_id}/", status_code=301)


@router.get("/{item_id}/{path:path}", include_in_schema=False)
def folder_serve(item_id: str, path: str, request: Request):
    from astrapi_sync._paths import folder_path, resolve_within

    folder = _get_owned_folder(item_id)
    root = folder_path(item_id)
    label = folder.get("description") or item_id

    path_clean = path.strip("/")
    target = resolve_within(root, path_clean) if path_clean else root

    if target.is_file():
        return FileResponse(str(target))

    if not target.is_dir():
        raise HTTPException(404, "Nicht gefunden")

    prefix = f"/{item_id}"

    def _href(name: str, is_dir: bool) -> str:
        suffix = "/" if is_dir else ""
        return f"{prefix}/{path_clean}/{name}{suffix}" if path_clean else f"{prefix}/{name}{suffix}"

    try:
        entries = list_dir_entries(target, _href)
    except PermissionError:
        raise HTTPException(403, "Zugriff verweigert")

    if path_clean:
        parts = path_clean.split("/")
        back = f"{prefix}/" + "/".join(parts[:-1]) + "/" if len(parts) > 1 else f"{prefix}/"
    else:
        back = "/"

    title = label + (f"/{path_clean}" if path_clean else "")
    rows = [render_row(e) for e in entries]
    return HTMLResponse(
        _page(
            title,
            "",
            rows,
            back=back,
            col_headers=("Name", "Geändert", "Größe"),
            empty_message="Leer.",
        )
    )
