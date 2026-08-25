# astrapi-sync

Ordner-Synchronisation über mehrere Geräte (Server-Komponente) — nach dem
Vorbild von Syncthing/Nextcloud/Ubuntu One, auf `astrapi-core` aufgebaut.

Ein Ordner wird auf dem Server angelegt (Modul „Ordner"); Geräte (GTK4-App,
CLI, Android-App — jeweils eigene Repos) werden per Pairing-Code gekoppelt
(Modul „Geräte") und verbinden ihn dann mit einem lokalen Ordner.

Aktueller Stand: Server-Grundgerüst + Pairing-Flow (Phase 1). Das
eigentliche Sync-Protokoll (Datei-Index, Block-Delta-Übertragung,
WebSocket-Push) folgt in Phase 2 — siehe Plan-Dokumentation im
astrapi-hub-Vault, `projects/sync/`.

## Start (lokal)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

astrapi-sync --work-dir ./data --port 5004 --debug
```
