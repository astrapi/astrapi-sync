"""astrapi_sync._cli – Console-Script-Einstiegspunkt.

Start:
    astrapi-sync --work-dir /opt/astrapi-sync --port 5004
    astrapi-sync --work-dir /opt/astrapi-sync --port 5004 --debug
"""
from astrapi_core.system.paths import run_app


def main() -> None:
    run_app("astrapi_sync._app:app", "astrapi-sync", default_port=5004)


if __name__ == "__main__":
    main()
