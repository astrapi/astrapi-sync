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
from astrapi_core.ui.store import SqliteTableStore
from astrapi_sync.modules._owner_store import OwnerScopedStore, make_owner_crud_api_router
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

KEY = "folders"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)
ui_store = OwnerScopedStore(store)


def folders_for_select(enabled_only: bool = True, owner_user_id: int | None = None) -> list[dict]:
    """owner_user_id=None: aktueller Web-Nutzer (UI-Fall, current_user_id()).
    Explizit gesetzt: Pairing-Flow (api/sync.py::pair()), kein Web-Login
    vorhanden -- dort ist der einladende Nutzer bereits aus dem
    Pairing-Token bekannt."""
    if owner_user_id is None:
        from astrapi_sync.api.user_context import current_user_id

        owner_user_id = current_user_id()
    return [
        {"value": fid, "label": f.get("description") or fid}
        for fid, f in store.list().items()
        if f.get("owner_user_id") == owner_user_id and (not enabled_only or f.get("enabled"))
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


def _group_meta() -> dict:
    """{group_id: {"label", "color"}} für die Gruppen-Trennzeilen in
    list_wrapper_inner.html (group_by_field="group_id" unten) -- owner-
    gescoped wie folders selbst, aus demselben Grund wie
    OwnerScopedStore.get() (Verteidigung gegen fremde group_ids, auch wenn
    diese normalerweise nie auftreten können, da /api/folder_groups/
    for-select nur eigene Gruppen zur Auswahl anbietet)."""
    from astrapi_sync.modules.folder_groups.ui.crud import ui_store as groups_store

    return {
        gid: {"label": g.get("name") or gid, "color": g.get("color") or None}
        for gid, g in groups_store.list().items()
    }


def _resolve_display(item_id: str, item: dict) -> dict:
    item = _resolve_last_run(item_id, item)
    gid = item.get("group_id")
    if gid:
        meta = _group_meta().get(gid)
        item["group_description"] = (meta or {}).get("label") or gid
    else:
        item["group_description"] = ""
    return item


def _delete_guard(item_id: str) -> str | None:
    """Verhindert das Löschen eines Ordners, der noch mindestens einem
    Gerät zugeordnet ist -- sonst zeigt das Gerät danach auf einen nicht
    mehr existierenden Ordner (folder_ids liefe ins Leere)."""
    from astrapi_sync.modules.devices.ui.crud import store as devices_store

    referencing = [
        d.get("description") or did
        for did, d in devices_store.list().items()
        if str(item_id) in [str(fid) for fid in (d.get("folder_ids") or [])]
    ]
    if not referencing:
        return None
    return (
        f"Ordner wird noch von {len(referencing)} Gerät(en) verwendet "
        f"({', '.join(referencing)}) -- zuerst dort entfernen."
    )


api_router = make_owner_crud_api_router(
    KEY,
    _DIR / "config" / "schema.yaml",
    ui_store,
    can_delete_fn=_delete_guard,
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
        "group_id": form.get("group_id", ""),
        "enabled": "1" in form.getlist("enabled"),
    }
    item_id = ui_store.create(None, data)
    try:
        folder_path(item_id)  # legt das Verzeichnis an -- deckt fehlenden/nicht beschreibbaren Zusatzspeicher sofort auf
    except (OSError, RuntimeError) as exc:
        # DB-Eintrag wieder entfernen, statt einen Ordner ohne
        # nutzbaren Speicherort zurückzulassen.
        ui_store.delete(item_id)
        raise HTTPException(500, f"Ordner NICHT angelegt: {exc}") from exc
    return RedirectResponse(f"/ui/{KEY}/content", status_code=303)


# Generische CRUD-Routen danach (create wird durch die obige Route überschattet;
# update/edit läuft jetzt komplett generisch, siehe Docstring oben)
_crud = make_crud_router(
    ui_store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Ordner",
    has_toggle=False,
    list_item_transform=_resolve_display,
    group_by_field="group_id",
    group_meta_fn=_group_meta,
)
router.include_router(_crud)
