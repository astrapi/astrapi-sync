# astrapi_sync/api/user_context.py
"""Aktueller Web-Nutzer für die Owner-Scoping-Filterung (folders/devices UI).

Getrennt von der Geräte-Bearer-Token-Auth (api/auth.py) -- die kennt keine
Web-Logins und braucht das hier nicht. Wird über eine Middleware in _app.py
pro Request gesetzt (aus der Session-Cookie, siehe astrapi_core.system.auth),
danach über contextvars für den restlichen Request-Verlauf abrufbar.

contextvars.ContextVar statt threading.local(): Starlette kopiert den
Kontext korrekt in den Worker-Thread, der einen Request behandelt --
threading.local() würde bei Thread-Pool-Wiederverwendung zwischen
Requests leaken (ein Thread könnte den User eines VORHERIGEN Requests
sehen)."""
import contextvars

_current_user: contextvars.ContextVar["dict | None"] = contextvars.ContextVar(
    "current_user", default=None
)


def set_current_user(user: "dict | None") -> None:
    _current_user.set(user)


def get_current_user() -> "dict | None":
    return _current_user.get()


def current_user_id() -> int:
    """Für UI-Filterung: eingeloggter Nutzer, sonst der implizite
    Default-User (Rückwärtskompatibilität, z.B. wenn auth.enabled=false
    oder für Alt-Daten vor dieser Erweiterung)."""
    user = _current_user.get()
    if user is not None:
        return user["id"]
    from astrapi_core.system.auth import _default_user_id

    return _default_user_id()
