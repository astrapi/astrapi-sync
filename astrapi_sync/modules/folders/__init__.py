from pathlib import Path

from astrapi_core.system.db import register_table
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

_DDL = """
    CREATE TABLE IF NOT EXISTS folders (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        description TEXT    NOT NULL DEFAULT '',
        enabled     INTEGER NOT NULL DEFAULT 1
    )"""

register_table(_KEY, _DDL)

from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402
from astrapi_core.ui.field_resolver import register_options_fetcher as _reg  # noqa: E402

from astrapi_sync.modules.folders.ui.crud import folders_for_select  # noqa: E402
from astrapi_sync.modules.folders.ui.crud import api_router as router  # noqa: E402
from astrapi_sync.modules.folders.ui.crud import router as ui_router  # noqa: E402


def _folders_options_fetcher(endpoint: str) -> list:
    return folders_for_select(enabled_only=False)


_reg("/api/folders/for-select", _folders_options_fetcher)

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header([
        Header.action_button(
            "Neu", hx_get=f"/ui/{_KEY}/create", hx_target="body", style="primary", icon="plus"
        ),
    ]),
    ui_content=ContentTable(
        columns=[
            Col.mono("id", "ID"),
        ],
    ),
)
