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
)
