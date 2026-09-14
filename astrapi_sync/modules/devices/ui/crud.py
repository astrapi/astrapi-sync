# astrapi_sync/modules/devices/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.store import SqliteTableStore
from astrapi_sync.modules._owner_store import (
    OwnerScopedStore,
    make_owner_crud_api_router,
    make_reassign_owner_router,
)

KEY = "devices"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)
# admin_sees_all=True (T-331-SYNC, analog zu folders/T-330-SYNC): Admins
# sehen alle Geräte in der Liste, um sie einem anderen Nutzer zuordnen zu
# können (z.B. den ersten, noch auf "_default" laufenden Geräten). Anders
# als bei Ordnern gibt es hier keine zusätzliche Zugriffsbeschränkung --
# ein Gerät hat keinen schützenswerten "Inhalt", nur Metadaten, die Admins
# schon vorher über has_edit/has_delete=True (Default) bearbeiten konnten,
# sobald sie den Eintrag sehen.
ui_store = OwnerScopedStore(store, admin_sees_all=True)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


def _resolve_folder_labels(item_id: str, item: dict) -> dict:
    """Löst die rohen Ordner-IDs in folder_ids nur für die Listen-ANZEIGE
    gegen die Ordner-Beschreibung auf (z.B. "4" -> "maggie") -- vorher
    zeigte die Tabelle die rohe ID, die mobile Kartenansicht sogar die
    Python-Listen-Repräsentation im Klartext (T-225-SYNC).
    enabled_only=False, damit auch ein inzwischen deaktivierter Ordner noch
    seinen Namen zeigt statt stillschweigend zu verschwinden. owner_user_id
    explizit auf den GERÄTE-Besitzer gesetzt statt des Default (aktueller
    Web-Nutzer) -- sonst würde ein Admin, der dank admin_sees_all=True ein
    fremdes Gerät sieht, dessen Ordner-Zuordnung anhand der EIGENEN
    Ordnerliste aufzulösen versuchen und nur rohe IDs statt Namen sehen."""
    from astrapi_sync.modules.folders.ui.crud import folders_for_select

    labels_by_id = {
        opt["value"]: opt["label"]
        for opt in folders_for_select(enabled_only=False, owner_user_id=item.get("owner_user_id"))
    }
    item["folder_ids"] = [labels_by_id.get(fid, fid) for fid in (item.get("folder_ids") or [])]
    return item


def _resolve_owner(item_id: str, item: dict) -> dict:
    """Zeigt in der Liste, wem ein Gerät gehört -- v.a. für Admins relevant,
    die dank admin_sees_all=True auch fremde Geräte sehen (T-331-SYNC)."""
    from astrapi_core.system import auth as authmod

    user = authmod.get_user(item.get("owner_user_id"))
    item["owner_display"] = (user.get("display_name") or user.get("username")) if user else "—"
    return item


def _resolve_list_display(item_id: str, item: dict) -> dict:
    item = _resolve_folder_labels(item_id, item)
    item = _resolve_owner(item_id, item)
    return item


api_router = make_owner_crud_api_router(
    KEY,
    _DIR / "config" / "schema.yaml",
    ui_store,
)

router = make_crud_router(
    ui_store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Gerät",
    has_create=False,
    has_run_buttons=False,
    has_toggle=True,
    has_status=False,
    extra_actions_template=f"{KEY}/partials/row_actions.html",
    resolve_fields_fn=_resolve_fields,
    list_item_transform=_resolve_list_display,
)

# Besitzerwechsel (T-331-SYNC) -- gemeinsame, admin-only Routen/Logik für
# folders/devices, siehe _owner_store.py::make_reassign_owner_router().
router.include_router(
    make_reassign_owner_router(KEY, store, f"{KEY}/dialogs/reassign/modal.html")
)
