from pathlib import Path

from astrapi_core.system.db import register_table
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

_DDL = """
    CREATE TABLE IF NOT EXISTS folder_groups (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL DEFAULT '',
        description   TEXT    NOT NULL DEFAULT '',
        color         TEXT    NOT NULL DEFAULT '',
        enabled       INTEGER NOT NULL DEFAULT 1,
        owner_user_id INTEGER NOT NULL DEFAULT 0
    )"""

register_table(_KEY, _DDL)

from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402
from astrapi_core.ui.field_resolver import register_options_fetcher as _reg  # noqa: E402

from astrapi_sync.modules.folder_groups.ui.crud import groups_for_select  # noqa: E402
from astrapi_sync.modules.folder_groups.ui.crud import api_router as router  # noqa: E402
from astrapi_sync.modules.folder_groups.ui.crud import router as ui_router  # noqa: E402


def _groups_options_fetcher(endpoint: str) -> list:
    return groups_for_select()


# Ohne diese Registrierung bleibt folders.group_id (options_endpoint:
# /api/folder_groups/for-select) dauerhaft leer -- gleiche Begründung wie
# bei folders/__init__.py::_folders_options_fetcher.
_reg("/api/folder_groups/for-select", _groups_options_fetcher)

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header([
        Header.action_button(
            "Neue Gruppe", hx_get=f"/ui/{_KEY}/create", hx_target="body", style="primary", icon="plus"
        ),
    ]),
    ui_content=ContentTable(
        has_run_buttons=False,
        has_status=False,
        columns=[
            Col.trunc("description_text", "Beschreibung"),
        ],
    ),
)
