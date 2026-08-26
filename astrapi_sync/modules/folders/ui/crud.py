# astrapi_sync/modules/folders/ui/crud.py
"""Jeder Sync-Ordner liegt zwingend unter dem einen konfigurierten
Zusatzspeicher (_paths.py::folder_base(), require_extra_disk()) -- kein
Wahlfeld mehr pro Ordner (frueher storage_location, siehe T-201-SYNC bis
T-219-SYNC), daher auch kein Verschieben zwischen Speicherorten mehr
noetig. Anlegen ist trotzdem eigens überschrieben: crud_blueprint.py's
generischer create_apply() macht nur einen DB-Insert, ruehrt nie ans
Dateisystem -- create_with_check() unten prueft den Zusatzspeicher
sofort auf Schreibbarkeit, statt das erst beim ersten echten Sync eines
Clients auffallen zu lassen (T-240-SYNC). Bearbeiten hat dagegen keine
Dateisystem-Seiteneffekte mehr und laeuft komplett generisch.

Eigene Route zuerst auf einem eigenen APIRouter registriert, generischer
Router erst danach per include_router() eingehängt -- FastAPI matcht die
zuerst registrierte Route zuerst, das eigene create_with_check()
überschattet damit crud_blueprint.py's create_apply() für denselben Pfad
(gleiches Muster wie proxmox_lxc/create-modal, devices/pairing)."""
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
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


def _resolve_last_run(item_id: str, item: dict) -> dict:
    """Speist "Letzter Lauf" aus dem Activity Log statt aus dem (bei
    folders nie gepflegten) Job-Runner-Feld -- die Sync-Log-Einträge aus
    T-212-SYNC (module="folders", item_id=<folder_id>) sind bereits die
    passende Datenquelle, nur bisher nirgends an die Anzeige angebunden
    (T-226-SYNC)."""
    from astrapi_core.system.activity_log import list_runs_for_item

    runs = list_runs_for_item(KEY, str(item_id), limit=1)
    if runs:
        item["last_run"] = runs[0].get("started_at")
    return item


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


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def create_with_check(request: Request):
    """Wie crud_blueprint.py's create_apply(), aber: der (verpflichtende)
    Zusatzspeicher wird sofort nach dem Anlegen auf Schreibbarkeit geprüft
    (T-240-SYNC), statt sich erst beim ersten echten Sync eines Clients zu
    zeigen -- das rein generische create_apply() macht nur einen
    DB-Insert, ohne das Dateisystem je zu berühren. Ein Ordner blieb
    dadurch bisher unbemerkt angelegt, obwohl kein Zusatzspeicher
    konfiguriert oder dieser nicht beschreibbar war (siehe
    _paths.py::folder_path(), einzige Stelle mit dem eigentlichen
    .mkdir())."""
    from astrapi_sync._paths import folder_path

    form = await request.form()
    data = {
        "description": form.get("description", ""),
        "enabled": "1" in form.getlist("enabled"),
    }
    item_id = store.create(None, data)
    try:
        folder_path(item_id)  # legt das Verzeichnis an -- deckt fehlenden/nicht beschreibbaren Zusatzspeicher sofort auf
    except (OSError, RuntimeError) as exc:
        # DB-Eintrag wieder entfernen, statt einen Ordner ohne
        # nutzbaren Speicherort zurückzulassen.
        store.delete(item_id)
        raise HTTPException(500, f"Ordner NICHT angelegt: {exc}") from exc
    return RedirectResponse(f"/ui/{KEY}/content", status_code=303)


# Generische CRUD-Routen danach (create wird durch die obige Route überschattet;
# update/edit läuft jetzt komplett generisch, siehe Docstring oben)
_crud = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Ordner",
    has_toggle=False,
    list_item_transform=_resolve_last_run,
)
router.include_router(_crud)
