# astrapi_sync/modules/devices/ui/pairing.py
"""Admin-Dialog: Pairing-Token für ein neues Gerät erzeugen und anzeigen."""
import json

from fastapi import Request
from fastapi.responses import HTMLResponse

from astrapi_core.ui.render import render

from astrapi_sync.modules.devices.pairing_store import create_pairing_token, ttl_seconds
from astrapi_sync.modules.devices.ui.crud import KEY, router


def _qr_svg(server_url: str, token: str) -> str:
    """QR-Code (SVG, kein Pillow nötig) mit Server-URL + Pairing-Token als
    JSON -- für einen künftigen Kamera-Scanner in der Android-/GTK4-App,
    die dieselben zwei Felder braucht wie der manuelle CLI-Befehl. Rein
    serverseitig; noch kein Scanner-Client, der es liest."""
    import qrcode
    import qrcode.image.svg

    payload = json.dumps({"server_url": server_url, "token": token})
    img = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return img.to_string().decode("utf-8")


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
            "qr_svg": _qr_svg(server_url, token),
        },
    )


@router.get(f"/ui/{KEY}/{{item_id}}/reconnect", response_class=HTMLResponse)
def reconnect_dialog(item_id: str, request: Request):
    """Erzeugt einen Pairing-Code, der beim Einlösen NICHT ein neues Gerät
    anlegt, sondern nur das Token des bestehenden ersetzt -- Plattform,
    Beschreibung und Ordner-Zugriff bleiben unverändert."""
    from astrapi_sync.modules.devices.ui.crud import store as devices_store

    device = devices_store.get(item_id)
    if device is None:
        return HTMLResponse("Gerät nicht gefunden", status_code=404)

    token = create_pairing_token(device_id=item_id)
    server_url = str(request.base_url).rstrip("/")
    return render(
        request,
        f"{KEY}/dialogs/pair/modal.html",
        {
            "token": token,
            "server_url": server_url,
            "ttl_minutes": ttl_seconds() // 60,
            "device_description": device.get("description"),
            "qr_svg": _qr_svg(server_url, token),
        },
    )
