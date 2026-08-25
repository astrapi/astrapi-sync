"""astrapi_sync._app – ASGI-App-Factory.

Start:
    uvicorn astrapi_sync._app:app
    astrapi-sync --work-dir /opt/astrapi-sync --port 5004
"""

import time

from astrapi_core.system.paths import configure as _configure_paths

_configure_paths("astrapi-sync")

from astrapi_core.modules.settings.engine import configure as configure_settings
from astrapi_core.modules.system.engine import configure_updater
from astrapi_core.system.health import register_health
from astrapi_core.system.systemd import sd_notify, start_watchdog
from astrapi_core.system.version import get_display_name
from astrapi_core.ui import create as create_ui
from astrapi_core.ui.module_registry import load_modules
from astrapi_core.ui.settings_registry import init as settings_init
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from astrapi_sync._paths import db_path, package_dir, work_dir
from astrapi_sync.api.fastapi_app import create as create_api

_START_TIME = time.time()


def _db_check() -> tuple[bool, dict]:
    from astrapi_core.system.db import _conn

    try:
        _conn().execute("SELECT 1").fetchone()
        return True, {"db": True}
    except Exception:
        return False, {"db": False}


def _migrate_folders_storage_location() -> None:
    """register_table()'s DDL ist CREATE TABLE IF NOT EXISTS -- legt bei
    bereits bestehender Tabelle keine neuen Spalten nach. storage_location
    kam nachträglich dazu (T-202-SYNC), hier per ALTER TABLE ergänzt."""
    from astrapi_core.system.db import _conn

    con = _conn()
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(folders)")]
        if "storage_location" not in cols:
            con.execute("ALTER TABLE folders ADD COLUMN storage_location TEXT NOT NULL DEFAULT ''")
            con.commit()
    except Exception:
        pass


def create_app() -> FastAPI:
    _pkg = package_dir()
    configure_settings(health_fn=_db_check, app_name=get_display_name(_pkg))
    configure_updater(_pkg)

    from astrapi_core.system.db import configure as _configure_db
    from astrapi_core.system.db import create_all_registered_tables

    _configure_db(db_path())
    create_all_registered_tables()
    _migrate_folders_storage_location()

    settings_init(work_dir())

    modules, _ = load_modules(_pkg)
    api = create_api(modules=modules)

    from pathlib import Path

    import astrapi_core.ui

    core_static = Path(astrapi_core.ui.__file__).parent / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")

    create_ui(api, app_root=_pkg, modules=modules)

    register_health(api, check_fn=_db_check, start_time=_START_TIME)
    start_watchdog(check_fn=lambda: _db_check()[0])
    sd_notify("READY=1")
    return api


app = create_app()
