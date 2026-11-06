"""Cliente HTTP directo para la API de Bots de Telegram."""
import json
import logging
import requests
import config as C

log = logging.getLogger("telegram")

def _api_url(metodo):
    return f"https://api.telegram.org/bot{C.TELEGRAM_TOKEN}/{metodo}"

def enviar_texto(texto, chat_id=None):
    if not C.TELEGRAM_TOKEN:
        log.warning("TELEGRAM_TOKEN no configurado; no se envió el mensaje.")
        return False
    destino = str(chat_id or C.TELEGRAM_CHAT_ID)
    try:
        r = requests.post(_api_url("sendMessage"), timeout=15, json={
            "chat_id": destino,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        return r.ok and r.json().get("ok", False)
    except Exception as e:
        log.error("Error al enviar mensaje a Telegram (%s)", type(e).__name__)
        return False

def enviar_foto(ruta, caption, chat_id=None):
    if not C.TELEGRAM_TOKEN:
        return False
    destino = str(chat_id or C.TELEGRAM_CHAT_ID)
    try:
        with open(ruta, "rb") as f:
            r = requests.post(
                _api_url("sendPhoto"),
                timeout=45,
                data={
                    "chat_id": destino,
                    "caption": caption[:1024],
                    "parse_mode": "HTML",
                },
                files={"photo": f},
            )
        if not r.ok:
            log.warning("Telegram rechazó la foto: %s", r.text[:200])
        return r.ok and r.json().get("ok", False)
    except Exception as e:
        log.error("Error al enviar fotografía a Telegram (%s)", type(e).__name__)
        return False

def registrar_comandos():
    if not C.TELEGRAM_TOKEN:
        return
    comandos = [
        {"command": "estado", "description": "Estado del sistema y telemetría"},
        {"command": "foto", "description": "Capturar y analizar una foto ahora"},
        {"command": "vivo", "description": "Enlace al video en vivo y Dashboard"},
        {"command": "ultimo", "description": "Últimos incidentes registrados"},
        {"command": "pausa", "description": "Pausar alertas de movimiento"},
        {"command": "reanudar", "description": "Reanudar alertas de movimiento"},
        {"command": "ayuda", "description": "Lista de comandos disponibles"},
    ]
    try:
        requests.post(_api_url("setMyCommands"), timeout=15, json={"commands": comandos})
    except Exception as e:
        log.error("No se pudieron registrar comandos en Telegram: %s", e)

def escuchar(on_comando, stop_event):
    """Bucle de Long Polling para recibir comandos del chat autorizado."""
    offset = None
    log.info("Iniciando escucha de comandos de Telegram...")
    while not stop_event.is_set():
        try:
            r = requests.get(_api_url("getUpdates"), timeout=35, params={
                "timeout": 25,
                "offset": offset,
                "allowed_updates": json.dumps(["message"]),
            })
            if not r.ok:
                stop_event.wait(5)
                continue

            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                m = u.get("message") or {}
                chat_id_recibido = str(m.get("chat", {}).get("id"))
                
                # Validar que pertenezca al chat autorizado
                if chat_id_recibido != C.TELEGRAM_CHAT_ID:
                    log.warning("Mensaje ignorado de chat no autorizado: %s", chat_id_recibido)
                    continue

                texto = (m.get("text") or "").strip()
                if texto.startswith("/"):
                    cmd = texto.split()[0].split("@")[0].lower()
                    on_comando(cmd)

        except Exception as e:
            log.error("Excepción en polling de Telegram (%s)", type(e).__name__)
            stop_event.wait(5)
