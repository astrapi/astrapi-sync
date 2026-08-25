# astrapi-sync – Projektkontext für GitHub Copilot

Wird im Repo versioniert und von VS Code Copilot automatisch geladen.

---

## Was ist astrapi-sync?

Persönlicher Datei-Synchronisationsdienst nach dem Vorbild von Syncthing/Nextcloud
(Server + CLI-Client, später GTK4/Android). Nur Michaels eigene Geräte (Auth über
Geräte-Token statt Accounts), Block-/Delta-Sync (Syncthing-Stil, fixe Blockgröße,
SHA256 je Block), Änderungs-Push per WebSocket statt Polling.
Basiert auf **astrapi-core** (FastAPI + HTMX + Jinja2).
PyPI-Paketname: `astrapi-sync`, Python-Paket: `astrapi_sync`.

Zugehöriges Client-Repo: [astrapi-sync-client](https://github.com/astrapi/astrapi-sync-client)
(geteilte Sync-Engine + CLI, kein astrapi-core-Abhängigkeit).

---

## Stack

| Komponente | Details |
|---|---|
| Framework | astrapi-core (FastAPI + HTMX) |
| API | FastAPI (`/api/...`) |
| UI | FastAPI + HTMX + Jinja2 (`/ui/...`) |
| Persistenz | SQLite (über astrapi-core) |
| Auth (Sync-API) | Bearer-Geräte-Token, SHA256-gehasht gespeichert |
| Python | ≥ 3.11 |

---

## Verzeichnisstruktur

```
astrapi_sync/
├── _app.py              # ASGI-App-Factory (uvicorn-Einstiegspunkt)
├── _cli.py               # Console-Script: astrapi-sync
├── _paths.py              # package_dir(), work_dir(), folder_path(), extra_disk_options()
├── app.yaml               # name: astrapi-sync, display_name: Sync
├── navigation.yaml         # App-Navigation
├── api/
│   ├── fastapi_app.py     # FastAPI-Factory, Router-Registrierung
│   ├── auth.py             # Geräte-Token-Auth (require_device, require_device_only)
│   ├── block_hash.py       # Block-Hashing, Datei-/Verzeichnis-Index
│   ├── sync.py              # Pairing, Datei-Index, Upload/Download/Delete, WebSocket-Push
│   └── ws_manager.py        # In-Process-WebSocket-Verbindungsmanager je Ordner
└── modules/
    ├── folders/            # Sync-Ordner (Admin-CRUD, Speicherort, Dateibrowser-Modal)
    └── devices/            # Gepairte Geräte, Pairing-Flow, Reconnect
```

---

## App-Start

```
astrapi-sync --work-dir /opt/astrapi-sync --port 5004
```

- `_configure_paths("astrapi-sync")` setzt Runtime-Pfade
- `configure_updater(_pkg)` registriert `astrapi-sync` + `astrapi-core` im Updater
- Sync-Ordner liegen standardmäßig unter `<work-dir>/folders/<id>/`, oder auf einem
  konfigurierten Zusatzspeicher (`extra_disks`-Systemeinstellung) unter
  `<speicherort>/astrapi-sync/<id>/` — siehe `_paths.py::folder_path()`.

---

## Sync-Protokoll (Kurzüberblick)

- `POST /api/sync/pair` — Pairing-Token → langlebiges Geräte-Token (Bearer).
- `GET  /api/sync/folders/{id}/index` — Datei- und Verzeichnis-Index
  (`build_index()`/`build_dir_index()` in `block_hash.py`).
- `POST/GET /api/sync/folders/{id}/files/{path}` — Block-Delta-Upload/Download.
- `DELETE /api/sync/folders/{id}/files/{path}` — Löschung propagieren.
- `POST/DELETE /api/sync/folders/{id}/dirs/{path}` — leere Verzeichnisse anlegen/entfernen
  (nicht-leere entstehen implizit über Datei-Pfade).
- `WS /api/sync/folders/{id}/events` — Push bei Änderungen an alle verbundenen Geräte.

Kein rsync-Rolling-Hash, kein Blob-Store: reale Verzeichnisbäume auf Platte,
Block-Hashes nur als Übertragungstechnik.

---

## Versionsschema

CalVer: `YY.MM.patch.devN` – gesteuert via setuptools-scm + Git-Tags.
Release über `astrapi-tools/release.sh sync` (Tag `v*` triggert `publish.yml` → PyPI).
