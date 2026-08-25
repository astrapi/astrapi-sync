# astrapi_sync/modules/devices/ui/pairing.py
"""Admin-Dialog: Pairing-Token für ein neues Gerät erzeugen und anzeigen."""
from fastapi import Request
from fastapi.responses import HTMLResponse

from astrapi_core.ui.render import render

from astrapi_sync.modules.devices.pairing_store import create_pairing_token, ttl_seconds
from astrapi_sync.modules.devices.ui.crud import KEY, router


@router.get(f"/ui/{KEY}/pair", response_class=HTMLResponse)
def pair_dialog(request: Request):
    token = create_pairing_token()
    server_url = str(request.base_url).rstrip("/")
    return render(
        request,
        f"{KEY}/dialogs/pair/modal.html",
        {
            "token": token,
            "server_url": server_url,
            "ttl_minutes": ttl_seconds() // 60,
        },
    )
