# astrapi_sync/modules/folders/ui/move.py
"""Ordner-Speicherort verschieben: physisch den kompletten Inhalt an einen
anderen konfigurierten Zusatzspeicher (oder zurück zum Standard) umziehen,
nicht nur die Einstellung ändern -- neue/geänderte Dateien würden sonst
am neuen Ort landen, während der bisherige Inhalt am alten Ort
zurückbliebe und für Clients unsichtbar wäre."""
import shutil

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from astrapi_core.ui.render import render

from astrapi_sync._paths import folder_base, folder_path
from astrapi_sync.modules.folders.ui.crud import KEY, router, store

# FastAPI/Starlette behandelt bei Form(...) einen leeren String faktisch
# wie ein fehlendes Feld (reproduzierbar auch ganz ohne HTTP direkt via
# TestClient -- 422 "Field required") -- daher hier ein nicht-leerer
# Platzhalter für "Standard" statt "", erst serverseitig zurückübersetzt.
_DEFAULT_SENTINEL = "__default__"


def _location_options(current: str) -> list[dict]:
    from astrapi_sync._paths import extra_disk_options

    options = []
    if current != "":
        options.append({"value": _DEFAULT_SENTINEL, "label": "Standard (Arbeitsverzeichnis)"})
    for disk in extra_disk_options():
        if disk != current:
            options.append({"value": disk, "label": disk})
    return options


@router.get(f"/ui/{KEY}/{{item_id}}/move", response_class=HTMLResponse)
def move_dialog(item_id: str, request: Request):
    folder = store.get(item_id)
    if folder is None:
        return HTMLResponse("Ordner nicht gefunden", status_code=404)
    current = folder.get("storage_location") or ""
    return render(
        request,
        f"{KEY}/dialogs/move/modal.html",
        {
            "folder_id": item_id,
            "current_label": current or "Standard (Arbeitsverzeichnis)",
            "options": _location_options(current),
            "loading_id": request.query_params.get("loading_id", f"{KEY}-loading"),
        },
    )


@router.post(f"/ui/{KEY}/{{item_id}}/move")
def move_apply(item_id: str, target: str = Form(...)):
    if target == _DEFAULT_SENTINEL:
        target = ""

    folder = store.get(item_id)
    if folder is None:
        return HTMLResponse("Ordner nicht gefunden", status_code=404)

    current = folder.get("storage_location") or ""
    if target == current:
        return RedirectResponse(f"/ui/{KEY}/content", status_code=303)

    old_path = folder_path(item_id)  # aktueller Ort, wird bei Bedarf angelegt
    new_path = folder_base(target) / item_id
    if new_path.exists() and any(new_path.iterdir()):
        return HTMLResponse("Zielverzeichnis existiert bereits und ist nicht leer", status_code=400)

    new_path.parent.mkdir(parents=True, exist_ok=True)
    if old_path.exists():
        if new_path.exists():
            new_path.rmdir()  # oben als leer geprüft, shutil.move braucht ein nicht existierendes Ziel
        shutil.move(str(old_path), str(new_path))
    else:
        new_path.mkdir(parents=True, exist_ok=True)

    store.update(item_id, {"storage_location": target})
    return RedirectResponse(f"/ui/{KEY}/content", status_code=303)
