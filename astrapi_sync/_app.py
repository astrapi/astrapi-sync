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


def _migrate_folders_color() -> None:
    """Gleiches Problem/Muster wie _migrate_folders_storage_location() --
    color kam nachträglich zur folders-DDL dazu (ersetzt group_id/das
    entfernte folder_groups-Modul durch eine freie Farbkategorie pro
    Ordner). Die alte group_id-Spalte bleibt als harmlose Karteileiche
    bestehen -- kein SQLite-DROP COLUMN, da der bisherige Stand ohnehin
    nur auf sync-dev existiert und nie released wurde."""
    from astrapi_core.system.db import _conn

    con = _conn()
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(folders)")]
        if "color" not in cols:
            con.execute("ALTER TABLE folders ADD COLUMN color TEXT NOT NULL DEFAULT ''")
            con.commit()
    except Exception:
        pass


def _migrate_devices_unifiedpush_endpoint() -> None:
    """Gleiches Problem/Muster wie _migrate_folders_storage_location() --
    unifiedpush_endpoint_url kam nachträglich zur devices-DDL dazu."""
    from astrapi_core.system.db import _conn

    con = _conn()
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(devices)")]
        if "unifiedpush_endpoint_url" not in cols:
            con.execute("ALTER TABLE devices ADD COLUMN unifiedpush_endpoint_url TEXT NOT NULL DEFAULT ''")
            con.commit()
    except Exception:
        pass


def _migrate_folders_owner_user_id() -> None:
    """Gleiches Problem/Muster wie _migrate_folders_storage_location() --
    owner_user_id kam nachträglich zur folders-DDL dazu (Mandantentrennung).
    Bestehende Zeilen (owner_user_id=0) werden dem impliziten Default-User
    zugeordnet, damit niemandem seine Alt-Ordner verschwinden."""
    from astrapi_core.system.db import _conn

    con = _conn()
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(folders)")]
        if "owner_user_id" not in cols:
            con.execute("ALTER TABLE folders ADD COLUMN owner_user_id INTEGER NOT NULL DEFAULT 0")
            con.commit()
        n = con.execute("SELECT COUNT(*) AS n FROM folders WHERE owner_user_id=0").fetchone()["n"]
        if n:
            from astrapi_core.system.auth import _default_user_id

            con.execute("UPDATE folders SET owner_user_id=? WHERE owner_user_id=0", (_default_user_id(),))
            con.commit()
    except Exception:
        pass


def _migrate_devices_owner_user_id() -> None:
    """Gleiches Muster wie _migrate_folders_owner_user_id(), Tabelle devices."""
    from astrapi_core.system.db import _conn

    con = _conn()
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(devices)")]
        if "owner_user_id" not in cols:
            con.execute("ALTER TABLE devices ADD COLUMN owner_user_id INTEGER NOT NULL DEFAULT 0")
            con.commit()
        n = con.execute("SELECT COUNT(*) AS n FROM devices WHERE owner_user_id=0").fetchone()["n"]
        if n:
            from astrapi_core.system.auth import _default_user_id

            con.execute("UPDATE devices SET owner_user_id=? WHERE owner_user_id=0", (_default_user_id(),))
            con.commit()
    except Exception:
        pass


class _SetCurrentUserMiddleware:
    """Setzt den eingeloggten Web-Nutzer (aus der Session-Cookie) pro Request
    in api.user_context, damit devices/folders-UI-Routen ihn owner-scopen
    können. Getrennt von der Geräte-Bearer-Token-Auth (api/auth.py)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from astrapi_core.system import auth as authmod
        from starlette.requests import Request

        from astrapi_sync.api.user_context import set_current_user

        request = Request(scope, receive=receive)
        token = request.cookies.get(authmod.SESSION_COOKIE_NAME)
        set_current_user(authmod.get_current_user(token))
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    _pkg = package_dir()

    # Sync-Ordner liegen direkt auf der Wurzel ("/{folder_id}/..."), das
    # Dashboard wird per Caddy unter /admin reverse-proxied. Siehe
    # astrapi_core.system.paths.set_admin_prefix()-Docstring. Muss vor
    # load_modules() gesetzt sein.
    from astrapi_core.system.paths import set_admin_prefix

    set_admin_prefix("/admin")

    configure_settings(health_fn=_db_check, app_name=get_display_name(_pkg))
    configure_updater(_pkg)

    from astrapi_core.system.db import configure as _configure_db
    from astrapi_core.system.db import create_all_registered_tables

    _configure_db(db_path())
    create_all_registered_tables()
    _migrate_folders_storage_location()
    _migrate_folders_color()
    _migrate_devices_unifiedpush_endpoint()
    _migrate_folders_owner_user_id()
    _migrate_devices_owner_user_id()

    settings_init(work_dir())

    modules, _ = load_modules(_pkg)
    api = create_api(modules=modules)
    api.add_middleware(_SetCurrentUserMiddleware)

    from pathlib import Path

    import astrapi_core.ui

    core_static = Path(astrapi_core.ui.__file__).parent / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")

    create_ui(api, app_root=_pkg, modules=modules)

    register_health(api, check_fn=_db_check, start_time=_START_TIME)

    # public_files.router bewusst ganz zuletzt eingehaengt -- registriert
    # u.a. den Catch-all "/{item_id}/{path:path}" auf der Wurzel, der
    # sonst vor spezifischeren Routen (/health, /admin/..., /static/...)
    # gewinnen wuerde (Starlette matcht in Registrierungsreihenfolge,
    # nicht nach Spezifitaet -- siehe astrapi-mirror/-packages fuer den
    # identischen Fall).
    from astrapi_sync.api.public_files import router as public_files_router

    api.include_router(public_files_router)

    start_watchdog(check_fn=lambda: _db_check()[0])
    sd_notify("READY=1")
    return api


app = create_app()
