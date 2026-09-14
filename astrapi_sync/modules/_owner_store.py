# astrapi_sync/modules/_owner_store.py
"""Owner-scopender Wrapper um SqliteTableStore für devices/folders --
filtert list()/get() auf den aktuell eingeloggten Web-Nutzer
(api/user_context.py) und stempelt neue Einträge mit dessen owner_user_id.

update()/delete() prüfen den Owner VOR der eigentlichen Operation (nicht
nur die Anzeige) -- verhindert, dass jemand über eine erratene/bekannte
fremde ID an fremden Daten schreibt, selbst wenn die UI sie nie zeigt.

admin_sees_all (T-330-SYNC): opt-in, nur folders setzt es -- Admins duerfen
dort ALLE Ordner in der Liste sehen (um sie ueberhaupt einem anderen Nutzer
zuordnen zu koennen), aber get()/update()/delete()/toggle() bleiben
UNVERAENDERT strikt owner-gescoped, auch fuer Admins. Der Besitzerwechsel
selbst laeuft deshalb bewusst NICHT ueber diese Klasse, sondern direkt
gegen den inneren Store (siehe folders/ui/crud.py::reassign_apply()) --
Admins bekommen dadurch keinen generellen Lese-/Schreibzugriff auf fremde
Ordnerinhalte (Dateibrowser bleibt ueber store.get() gesperrt), nur die
Sichtbarkeit in der Liste und die eine, eng gefasste Besitzerwechsel-Aktion."""
from astrapi_core.ui.store import SqliteTableStore
from astrapi_sync.api.user_context import current_user_id, get_current_user


def _current_user_is_admin() -> bool:
    user = get_current_user()
    return bool(user and user.get("is_admin"))


class OwnerScopedStore:
    def __init__(self, inner: SqliteTableStore, admin_sees_all: bool = False) -> None:
        self._inner = inner
        self._admin_sees_all = admin_sees_all

    def list(self) -> dict[str, dict]:
        if self._admin_sees_all and _current_user_is_admin():
            return dict(self._inner.list())
        uid = current_user_id()
        return {k: v for k, v in self._inner.list().items() if v.get("owner_user_id") == uid}

    def get(self, item_id: str) -> dict | None:
        item = self._inner.get(item_id)
        if item is None or item.get("owner_user_id") != current_user_id():
            return None
        return item

    def create(self, item_id: str | None, data: dict) -> str:
        return self._inner.create(item_id, {**data, "owner_user_id": current_user_id()})

    def update(self, item_id: str, data: dict) -> None:
        if self.get(item_id) is None:
            raise KeyError(item_id)
        self._inner.update(item_id, data)

    def delete(self, item_id: str) -> bool:
        if self.get(item_id) is None:
            return False
        return self._inner.delete(item_id)

    def toggle(self, item_id: str, field: str = "enabled", default: bool = True) -> bool:
        if self.get(item_id) is None:
            raise KeyError(item_id)
        return self._inner.toggle(item_id, field=field, default=default)


def make_owner_crud_api_router(key, schema_path, ui_store, *, can_delete_fn=None):
    """Ersatz für astrapi_core.ui.htmx_crud_router.make_htmx_crud_router()
    speziell für devices/folders: das Original arbeitet direkt gegen
    astrapi_core.system.db und nimmt kein Store-Objekt entgegen, würde
    OwnerScopedStore also komplett umgehen -- z.B. PATCH .../{fremde-id}/edit
    hätte trotz Owner-Scoping in der UI fremde Daten ändern können. Deckt
    nur ab, was devices/folders wirklich brauchen (kein type:list, kein
    on_create/on_update/preview_fn -- siehe htmx_crud_router.py als Vorlage
    für das vollständige Muster)."""
    import yaml
    from fastapi import APIRouter, Header, HTTPException, Request, Response
    from fastapi.responses import HTMLResponse

    router = APIRouter()

    def _load_schema() -> dict:
        return yaml.safe_load(schema_path.read_text()) or {}

    def _list_response(request: Request):
        from astrapi_core.ui.render import render

        content = render(
            request,
            "partials/lists/list_wrapper_inner.html",
            {
                "cfg": ui_store.list(),
                "module": key,
                "content_template": f"{key}/partials/card_body.html",
                "container_id": f"mod-{key}",
                "loading_id": f"{key}-loading",
                "running": {},
            },
        ).body.decode()
        return HTMLResponse(content, headers={"HX-Retarget": f"#mod-{key}", "HX-Reswap": "innerHTML"})

    def _clean(data: dict) -> dict:
        return {
            k: v
            for k, v in data.items()
            if v is not None
            and not (isinstance(v, str) and v.strip() == "")
            and not (isinstance(v, list) and len(v) == 0)
        }

    def _parse_form(form, schema: dict) -> dict:
        payload = dict(form)
        for f in schema.get("fields", []):
            if f.get("type") == "multiselect" and f.get("name"):
                payload[f["name"]] = list(form.getlist(f["name"]))
        payload["enabled"] = payload.get("enabled") in ("on", "1", True)
        for f in schema.get("fields", []):
            if not f.get("name") or f.get("type") == "section":
                continue
            if f["name"] not in payload:
                payload[f["name"]] = ""
        return payload

    @router.post("/create")
    async def create_one(request: Request):
        form = await request.form()
        payload = _parse_form(form, _load_schema())
        item_id = ui_store.create(None, _clean(payload))
        if request.headers.get("HX-Request") == "true":
            return _list_response(request)
        return {"id": item_id, **payload}

    @router.patch("/{item_id}/edit")
    async def patch_one(item_id: str, request: Request):
        """_parse_form() liefert IMMER einen Wert für jedes Schema-Feld
        (leerer String/leere Liste als Default, siehe dort) -- ein
        absichtlich auf "kein Wert" zurückgesetztes Feld (z.B. Ordner aus
        einer Gruppe lösen, alle Haken bei folder_ids entfernen) ist von
        einem einfach nicht abgeschickten Feld also gar nicht
        unterscheidbar. _clean() hier anzuwenden (wie noch bei create_one)
        würde solche Werte vor dem Schreiben wieder verwerfen -- das alte,
        eigentlich zu ersetzende existing.update() bliebe dann bestehen,
        ein einmal gesetztes optionales Feld ließe sich nie mehr leeren."""
        existing = ui_store.get(item_id)
        if existing is None:
            raise HTTPException(404, "Item not found")
        form = await request.form()
        payload = _parse_form(form, _load_schema())
        existing.update(payload)
        ui_store.update(item_id, existing)
        if request.headers.get("HX-Request") == "true":
            return _list_response(request)
        return existing

    def _do_delete(request: Request, item_id: str, hx_request: str | None):
        if ui_store.get(item_id) is None:
            raise HTTPException(404, "Item not found")
        if can_delete_fn is not None:
            reason = can_delete_fn(item_id)
            if reason:
                raise HTTPException(409, reason)
        ui_store.delete(item_id)
        if hx_request:
            return _list_response(request)
        return Response(status_code=204)

    @router.delete("/{item_id}/delete")
    def delete_one(request: Request, item_id: str, hx_request: str | None = Header(None)):
        return _do_delete(request, item_id, hx_request)

    @router.delete("/{item_id}")
    def delete_one_plain(request: Request, item_id: str, hx_request: str | None = Header(None)):
        return _do_delete(request, item_id, hx_request)

    @router.post("/{item_id}/toggle")
    def toggle_item(request: Request, item_id: str, hx_request: str | None = Header(None)):
        try:
            new_val = ui_store.toggle(item_id)
        except KeyError:
            raise HTTPException(404, "Item not found")
        if hx_request:
            return _list_response(request)
        return {"status": "ok", "item": item_id, "enabled": new_val}

    return router
