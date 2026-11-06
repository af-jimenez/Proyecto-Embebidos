"""Nodo de Seguridad Inteligente: PIR -> Inferencia TFLite -> Supabase + Telegram."""
import html
import logging
import signal
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

from logging.handlers import RotatingFileHandler

import camara
import config as C
import registro
import telegram_bot as tg
from detector import NOMBRES, Detector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("nodo")

# Registro en archivo compartido para visualización en el Dashboard
LOG_PATH = Path("/datos/sensor.log")
try:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _fh = RotatingFileHandler(str(LOG_PATH), maxBytes=300_000, backupCount=2, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(_fh)
except Exception as _e:
    log.warning("No se pudo iniciar el archivo de logs compartido: %s", _e)

lock = threading.Lock()
stop = threading.Event()
detector = None

class Estado:
    activo = True
    inicio = time.time()
    ultima_alerta = 0.0
    ultimo_error = 0.0
    ultimo_texto = "Sistema iniciado sin eventos."

def lineas_modelos(res):
    return "\n".join(
        f"{'🟢' if r['positivo'] else '⚪'} {NOMBRES.get(r['modelo'], r['modelo'])}: "
        f"{r['confianza']:.0%} ({r['ms']} ms)" for r in res
    )

def capturar_y_analizar():
    ahora = datetime.now()
    C.CARPETA_CAPTURAS.mkdir(parents=True, exist_ok=True)
    ruta = C.CARPETA_CAPTURAS / f"mov_{ahora:%Y%m%d_%H%M%S}.jpg"

    if not camara.capturar(ruta):
        return None, []

    res = detector.analizar(ruta)
    registro.guardar_csv(ahora.isoformat(timespec="seconds"), ruta.name, res)
    camara.rotar(C.CARPETA_CAPTURAS, C.MAX_CAPTURAS)
    return ruta, res

def avisar_fallo_camara():
    if time.time() - Estado.ultimo_error > 300:
        Estado.ultimo_error = time.time()
        tg.enviar_texto("⚠️ Se detectó movimiento pero la cámara no pudo capturar el fotograma. Verifica MediaMTX.")

def procesar_evento_pir():
    with lock:
        ruta, res = capturar_y_analizar()
        if ruta is None:
            avisar_fallo_camara()
            return

        pos = [r for r in res if r["positivo"]]
        hora = datetime.now().strftime("%H:%M:%S")
        max_conf = max((r["confianza"] for r in res), default=0.0)
        log.info("Captura procesada %s: %d/%d modelos positivos (máx confianza IA: %.1f%%)", ruta.name, len(pos), len(res), max_conf * 100)

        if len(pos) < C.MIN_POSITIVOS:
            Estado.ultimo_texto = f"{hora} - Movimiento detectado pero descartado (IA: {max_conf:.0%}, sin persona)."
            return

        if time.time() - Estado.ultima_alerta < C.COOLDOWN_ALERTA:
            log.info("Alerta silenciada por cooldown (%ds restantes)", int(C.COOLDOWN_ALERTA - (time.time() - Estado.ultima_alerta)))
            return

        Estado.ultima_alerta = time.time()
        Estado.ultimo_texto = f"{hora} - PERSONA DETECTADA ({len(pos)}/{len(res)} modelos)."

        max_conf = max(r["confianza"] for r in pos) if pos else 0.0
        id_ev = registro.crear_evento(max_conf, res, ruta.name)

        caption = (
            "🚨 <b>¡ALERTA DE SEGURIDAD!</b>\n"
            f"🕒 Fecha: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"👤 Humano detectado: <b>{len(pos)}/{len(res)} modelos</b>\n"
            f"{lineas_modelos(res)}\n"
            + (f"☁️ Evento Supabase: #{id_ev}\n" if id_ev else "")
            + f"\n📹 <b>Ver Video y Dashboard:</b>\n{C.URL_VIVO}"
        )

        enviado = tg.enviar_foto(ruta, caption)
        if id_ev:
            registro.actualizar_estado(id_ev, "enviado" if enviado else "error_telegram")

# --- Comandos del Bot ---
def temperatura_cpu():
    for p in ["/sys/class/thermal/thermal_zone0/temp", "/sys/class/hwmon/hwmon0/temp1_input"]:
        try:
            with open(p, "r") as f:
                return f"{int(f.read().strip()) / 1000:.1f} °C"
        except Exception:
            continue
    return "N/D"

def cmd_estado():
    minutos = int((time.time() - Estado.inicio) // 60)
    tg.enviar_texto(
        "📟 <b>Estado del Sistema de Seguridad</b>\n"
        f"• Alertas PIR: <b>{'ACTIVAS' if Estado.activo else 'EN PAUSA'}</b>\n"
        f"• Modelos TFLite: {', '.join(NOMBRES.get(k, k) for k in detector.modelos)}\n"
        f"• Temperatura CPU: <b>{temperatura_cpu()}</b>\n"
        f"• Tiempo activo: {minutos // 60}h {minutos % 60}m\n"
        f"• Último suceso: {html.escape(Estado.ultimo_texto)}\n"
        f"• Dashboard: {C.DASHBOARD_PUBLIC_URL}/?auth={C.DASHBOARD_TOKEN}"
    )

def cmd_foto():
    tg.enviar_texto("📸 Capturando y analizando fotograma manual...")
    with lock:
        ruta, res = capturar_y_analizar()
    if ruta is None:
        tg.enviar_texto("❌ No se pudo capturar imagen. Revisa el estado de la cámara.")
        return
    pos = [r for r in res if r["positivo"]]
    caption = (
        f"📸 <b>Captura Manual</b> ({len(pos)}/{len(res)} modelos detectan persona)\n"
        f"{lineas_modelos(res)}\n\n"
        f"📹 Dashboard: {C.URL_VIVO}"
    )
    tg.enviar_foto(ruta, caption)

def cmd_ultimo():
    eventos = registro.ultimos_eventos(3)
    if not eventos:
        tg.enviar_texto("Sin eventos recientes registrados en la base de datos.")
        return
    lineas = [
        f"#{e['id']} | Confianza: {float(e.get('confianza_ia') or 0):.0%} | "
        f"Estado: {e.get('estado_alerta')} | {str(e.get('created_at', ''))[:19]}"
        for e in eventos
    ]
    tg.enviar_texto("🗂 <b>Últimos Eventos Registrados:</b>\n" + "\n".join(lineas))

def on_comando(cmd):
    log.info("Comando Telegram recibido: %s", cmd)
    if cmd in ("/start", "/ayuda"):
        tg.enviar_texto(
            "🤖 <b>Bot de Seguridad Inteligente</b>\n"
            "/estado - Telemetría y estado de modelos\n"
            "/foto - Disparar foto y análisis inmediato\n"
            "/vivo - Enlace al Dashboard y streaming\n"
            "/ultimo - Últimos incidentes en Supabase\n"
            "/pausa - Pausar alertas automáticas del PIR\n"
            "/reanudar - Reanudar alertas del PIR"
        )
    elif cmd == "/estado":
        cmd_estado()
    elif cmd == "/foto":
        cmd_foto()
    elif cmd == "/vivo":
        tg.enviar_texto(f"📹 <b>Acceso al Dashboard y Video en Vivo:</b>\n{C.URL_VIVO}")
    elif cmd == "/ultimo":
        cmd_ultimo()
    elif cmd == "/pausa":
        Estado.activo = False
        tg.enviar_texto("⏸ Alertas de movimiento pausadas. Usa /reanudar para activarlas.")
    elif cmd == "/reanudar":
        Estado.activo = True
        tg.enviar_texto("▶️ Alertas de movimiento activadas.")

def main():
    global detector
    signal.signal(signal.SIGTERM, lambda *a: stop.set())
    signal.signal(signal.SIGINT, lambda *a: stop.set())

    log.info("Inicializando Nodo de Seguridad...")
    detector = Detector()
    tg.registrar_comandos()

    # Hilo para comandos de Telegram
    threading.Thread(target=tg.escuchar, args=(on_comando, stop), daemon=True).start()

    # Inicializar PIR con gpiozero
    try:
        from gpiozero import DigitalInputDevice
        pir = DigitalInputDevice(C.PIN_PIR, pull_up=False)
        log.info("Sensor PIR configurado en GPIO %d", C.PIN_PIR)
    except Exception as e:
        log.error("No se pudo inicializar GPIO para PIR (¿dispositivo no accesible?): %s", e)
        pir = None

    tg.enviar_texto(f"🟢 <b>Sistema de Seguridad Iniciado</b>\nDashboard: {C.DASHBOARD_PUBLIC_URL}/?auth={C.DASHBOARD_TOKEN}")
    log.info("Nodo de Seguridad completamente operativo.")

    if pir:
        log.info("Esperando estabilización del sensor PIR...")
        t0 = time.time()
        while pir.value == 1 and time.time() - t0 < 30 and not stop.is_set():
            time.sleep(0.5)
        log.info("Sensor PIR estabilizado y activo para monitoreo.")

        en_episodio = False
        ultima_captura = 0.0

        while not stop.wait(0.05):
            v = pir.value
            if v and not en_episodio:
                en_episodio = True
                log.info("PIR: Movimiento detectado (flanco de subida)")
                ahora = time.time()
                if Estado.activo:
                    if ahora - ultima_captura >= C.MIN_SEGUNDOS:
                        ultima_captura = ahora
                        # Disparar captura y análisis de inmediato en hilo independiente
                        threading.Thread(target=procesar_evento_pir, daemon=True).start()
                    else:
                        log.info("Captura en pausa por intervalo mínimo (%.1fs restantes)", C.MIN_SEGUNDOS - (ahora - ultima_captura))
            elif not v and en_episodio:
                en_episodio = False
                log.info("PIR: Fin de movimiento")
        pir.close()
    else:
        # Bucle pasivo si no hay PIR físico accesible (para pruebas)
        while not stop.wait(1.0):
            pass

    log.info("Nodo de Seguridad detenido.")

if __name__ == "__main__":
    main()
