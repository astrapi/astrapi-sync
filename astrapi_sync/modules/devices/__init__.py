from pathlib import Path

from astrapi_core.system.db import register_table
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

_DDL = """
    CREATE TABLE IF NOT EXISTS devices (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        label      TEXT    NOT NULL DEFAULT '',
        platform   TEXT    NOT NULL DEFAULT '',
        folder_ids TEXT    NOT NULL DEFAULT '',
        token_hash TEXT    NOT NULL DEFAULT '',
        last_seen  TEXT    NOT NULL DEFAULT '',
        enabled    INTEGER NOT NULL DEFAULT 1
    )"""

register_table(_KEY, _DDL, list_fields=["folder_ids"])

from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402

from astrapi_sync.modules.devices.ui.crud import api_router as router  # noqa: E402
from astrapi_sync.modules.devices.ui.crud import router as ui_router  # noqa: E402
from astrapi_sync.modules.devices.ui import pairing as _pairing  # noqa: E402,F401 – registriert Routen auf ui_router

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header([
        Header.action_button(
            "Gerät koppeln",
            hx_get=f"/ui/{_KEY}/pair",
            hx_target="body",
            style="primary",
            icon="plus",
        ),
    ]),
    ui_content=ContentTable(
        columns=[
            Col.text("platform", "Plattform"),
            Col.join("folder_ids", "Ordner"),
            Col.text("last_seen", "Zuletzt gesehen"),
        ],
    ),
)
