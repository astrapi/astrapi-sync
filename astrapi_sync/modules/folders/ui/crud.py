# astrapi_sync/modules/folders/ui/crud.py
"""Speicherort (storage_location) ist ein normales Auswahlfeld in
Anlegen- UND Bearbeiten-Dialog (schema.yaml). Anlegen läuft komplett
generisch über crud_blueprint.py -- ein neuer Ordner ist leer, der Wert
kann direkt gesetzt werden. Bearbeiten wird unten überschrieben: ändert
sich der Speicherort, muss der komplette Ordnerinhalt physisch
mitverschoben werden (sonst "verliert" der Client scheinbar seine
Dateien, siehe T-203-SYNC) -- das kann crud_blueprint.py's generischer
edit_apply() nicht.

Eigene Route zuerst auf einem eigenen APIRouter registriert, generischer
Router erst danach per include_router() eingehängt -- FastAPI matcht die
zuerst registrierte Route zuerst, das eigene update_with_move()
überschattet damit crud_blueprint.py's edit_apply() für denselben Pfad
(gleiches Muster wie proxmox_lxc/create-modal, devices/pairing)."""
import shutil
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import register_options_fetcher, resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.store import SqliteTableStore
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

KEY = "folders"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)


def folders_for_select(enabled_only: bool = True) -> list[dict]:
    return [
        {"value": fid, "label": f.get("description") or fid}
        for fid, f in store.list().items()
        if not enabled_only or f.get("enabled")
    ]


def storage_location_options() -> list[dict]:
    from astrapi_sync._paths import extra_disk_options

    options = [{"value": "", "label": "Standard (Arbeitsverzeichnis)"}]
    options += [{"value": disk, "label": disk} for disk in extra_disk_options()]
    return options


register_options_fetcher("/api/folders/storage-locations", lambda _endpoint: storage_location_options())


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


api_router = make_htmx_crud_router(
    KEY,
    _DIR / "config" / "schema.yaml",
)


@api_router.get("/for-select")
def for_select(enabled: str = Query(default="1")):
    return {"options": folders_for_select(enabled_only=enabled != "0")}


# Eigene Routen zuerst registrieren -- FastAPI nutzt first-match, siehe
# Docstring oben.
router = APIRouter()


@router.post(f"/ui/{KEY}/{{item_id}}/update", response_class=HTMLResponse)
async def update_with_move(item_id: str, request: Request):
    """Wie crud_blueprint.py's edit_apply(), aber: ändert sich
    storage_location, wird der komplette Ordnerinhalt zuerst physisch
    verschoben, bevor die DB aktualisiert wird."""
    from astrapi_sync._paths import folder_base, folder_path

    folder = store.get(item_id)
    if folder is None:
        return HTMLResponse("Ordner nicht gefunden", status_code=404)

    form = await request.form()
    data = {
        "description": form.get("description", ""),
        "storage_location": form.get("storage_location", ""),
        "enabled": "1" in form.getlist("enabled"),
    }

    current_location = folder.get("storage_location") or ""
    target_location = data["storage_location"]
    if target_location != current_location:
        old_path = folder_path(item_id)  # aktueller Ort, wird bei Bedarf angelegt
        new_path = folder_base(target_location) / item_id
        if new_path.exists() and any(new_path.iterdir()):
            raise HTTPException(400, "Zielverzeichnis existiert bereits und ist nicht leer")
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if old_path.exists():
            if new_path.exists():
                new_path.rmdir()  # oben als leer geprüft, shutil.move braucht ein nicht existierendes Ziel
            shutil.move(str(old_path), str(new_path))
        else:
            new_path.mkdir(parents=True, exist_ok=True)

    store.update(item_id, data)
    return RedirectResponse(f"/ui/{KEY}/content", status_code=303)


# Generische CRUD-Routen danach (update wird durch die obige Route überschattet)
_crud = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Ordner",
    has_run_buttons=False,
    has_toggle=False,
    has_status=False,
    resolve_fields_fn=_resolve_fields,
)
router.include_router(_crud)
