# astrapi_sync/modules/folder_groups/ui/crud.py
"""Gruppen zur Organisation von Ordnern (T-31x-SYNC) -- owner-scoped wie
folders/devices (siehe _owner_store.py), Verwaltung (Anlegen/Umbenennen/
Löschen) nur über die Weboberfläche. Android/GTK4 zeigen Gruppen nur an."""
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.store import SqliteTableStore
from astrapi_sync.modules._owner_store import OwnerScopedStore, make_owner_crud_api_router

KEY = "folder_groups"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)
ui_store = OwnerScopedStore(store)


def groups_for_select() -> list[dict]:
    return [
        {"value": gid, "label": g.get("name") or gid}
        for gid, g in ui_store.list().items()
    ]


def _resolve_labels(item_id: str, item: dict) -> dict:
    """list_wrapper_inner.html rendert die NAME-Spalte immer fest aus
    item_data.description -- folder_groups hat wie host_groups ein eigenes
    'name'-Feld (Pflicht) UND ein separates, optionales 'description'-Feld,
    die sonst auf demselben Dict-Key kollidieren (siehe
    astrapi-admin/host_groups/ui/crud.py::_resolve_labels, dieselbe
    Fehlerklasse). 'description_text' ist der kollisionsfreie Schlüssel für
    die echte Beschreibung-Spalte, 'description' trägt jetzt den Namen
    fürs NAME-Feld."""
    return {
        **item,
        "description": item.get("name") or item_id,
        "description_text": item.get("description") or "—",
    }


def _delete_guard(item_id: str) -> str | None:
    """Verhindert das Löschen einer Gruppe, der noch mindestens ein Ordner
    zugeordnet ist -- sonst zeigt der Ordner danach auf eine nicht mehr
    existierende Gruppe (group_id liefe ins Leere), analog
    folders/ui/crud.py::_delete_guard gegen devices."""
    from astrapi_sync.modules.folders.ui.crud import store as folders_store

    referencing = [
        f.get("description") or fid
        for fid, f in folders_store.list().items()
        if str(f.get("group_id") or "") == str(item_id)
    ]
    if not referencing:
        return None
    return (
        f"Gruppe wird noch von {len(referencing)} Ordner(n) verwendet "
        f"({', '.join(referencing)}) -- zuerst dort entfernen."
    )


api_router = make_owner_crud_api_router(
    KEY,
    _DIR / "config" / "schema.yaml",
    ui_store,
    can_delete_fn=_delete_guard,
)


@api_router.get("/for-select")
def for_select():
    return {"options": groups_for_select()}


router = make_crud_router(
    ui_store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Gruppe",
    description_field="name",
    has_toggle=False,
    has_run_buttons=False,
    has_status=False,
    list_item_transform=_resolve_labels,
)
