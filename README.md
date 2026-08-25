# astrapi-sync

Ordner-Synchronisation über mehrere Geräte (Server-Komponente) — nach dem
Vorbild von Syncthing/Nextcloud/Ubuntu One, auf `astrapi-core` aufgebaut.

Ein Ordner wird auf dem Server angelegt (Modul „Ordner", inkl. Wahl des
Speicherorts und Dateibrowser); Geräte (CLI-Client — GTK4-/Android-App
folgen) werden per Pairing-Code gekoppelt (Modul „Geräte") und verbinden
sich dann mit einem lokalen Ordner.

Block-/Delta-Sync (Syncthing-Stil, fixe Blockgröße, SHA256 je Block),
Änderungs-Push per WebSocket statt Polling, reale Verzeichnisbäume auf
Platte statt Blob-Store. Nur Michaels eigene Geräte — Auth über
Geräte-Token statt Accounts.

Zugehöriges Client-Repo: [astrapi-sync-client](https://github.com/astrapi/astrapi-sync-client).

## Stack

| Komponente | Details |
|---|---|
| Framework | astrapi-core (FastAPI + HTMX) |
| Persistenz | SQLite |
| Auth (Sync-API) | Bearer-Geräte-Token, SHA256-gehasht gespeichert |
| Python | ≥ 3.11 |

## Setup (Entwicklung)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ../astrapi-core   # Schwesterprojekt
pip install -e .
```

## Starten

```bash
astrapi-sync --work-dir ./data --port 5004 --debug
```

| Parameter | Standard | Beschreibung |
|---|---|---|
| `--work-dir` | (Pflicht) | Datenpfad für SQLite-DB, Sync-Ordner und Laufzeitdaten |
| `--port` | `5004` | HTTP-Port |
| `--host` | `0.0.0.0` | Bind-Adresse |
| `--debug` / `--reload` | – | Auto-Reload bei Dateiänderungen |

Die Web-Oberfläche ist danach erreichbar unter: `http://localhost:5004`

## Projektstruktur

```
astrapi_sync/
├── _cli.py            # Einstiegspunkt (CLI)
├── _app.py            # ASGI-App-Factory
├── _paths.py          # Pfad-Utilities (Speicherort je Ordner)
├── api/
│   ├── auth.py         # Geräte-Token-Auth
│   ├── block_hash.py   # Block-Hashing, Datei-/Verzeichnis-Index
│   ├── sync.py          # Pairing, Index, Upload/Download/Delete, WebSocket
│   └── ws_manager.py     # Verbindungsmanager je Ordner
└── modules/
    ├── folders/        # Sync-Ordner (Admin-CRUD, Speicherort, Dateibrowser)
    └── devices/        # Gepairte Geräte, Pairing-Flow
```
