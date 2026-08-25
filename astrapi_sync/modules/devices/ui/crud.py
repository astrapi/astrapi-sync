# astrapi_sync/modules/devices/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.store import SqliteTableStore

KEY = "devices"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


def _resolve_folder_labels(item_id: str, item: dict) -> dict:
    """Löst die rohen Ordner-IDs in folder_ids nur für die Listen-ANZEIGE
    gegen die Ordner-Beschreibung auf (z.B. "4" -> "maggie") -- vorher
    zeigte die Tabelle die rohe ID, die mobile Kartenansicht sogar die
    Python-Listen-Repräsentation im Klartext (T-225-SYNC).
    enabled_only=False, damit auch ein inzwischen deaktivierter Ordner noch
    seinen Namen zeigt statt stillschweigend zu verschwinden."""
    from astrapi_sync.modules.folders.ui.crud import folders_for_select

    labels_by_id = {opt["value"]: opt["label"] for opt in folders_for_select(enabled_only=False)}
    item["folder_ids"] = [labels_by_id.get(fid, fid) for fid in (item.get("folder_ids") or [])]
    return item


api_router = make_htmx_crud_router(
    KEY,
    _DIR / "config" / "schema.yaml",
)

router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Gerät",
    has_create=False,
    has_run_buttons=False,
    has_toggle=True,
    has_status=False,
    resolve_fields_fn=_resolve_fields,
    list_item_transform=_resolve_folder_labels,
)
