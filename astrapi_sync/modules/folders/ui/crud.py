# astrapi_sync/modules/folders/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.store import SqliteTableStore
from fastapi import Query

KEY = "folders"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)


def folders_for_select(enabled_only: bool = True) -> list[dict]:
    return [
        {"value": fid, "label": f.get("description") or fid}
        for fid, f in store.list().items()
        if not enabled_only or f.get("enabled")
    ]


api_router = make_htmx_crud_router(
    KEY,
    _DIR / "config" / "schema.yaml",
)


@api_router.get("/for-select")
def for_select(enabled: str = Query(default="1")):
    return {"options": folders_for_select(enabled_only=enabled != "0")}


router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Ordner",
    has_run_buttons=False,
    has_toggle=False,
    has_status=False,
)
