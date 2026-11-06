"""Captura de fotogramas conectándose al flujo RTSP de MediaMTX."""
import logging
import subprocess
from pathlib import Path
import config as C

log = logging.getLogger("camara")

def capturar(ruta, intentos=3):
    """Guarda un frame en `ruta` conectándose a MediaMTX vía RTSP."""
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-rtsp_transport", "tcp", "-i", C.RTSP_URL,
        "-vf", "select=gte(n\\,15)", "-fps_mode", "vfr",
        "-frames:v", "1", "-q:v", "2", str(ruta),
    ]
    for n in range(1, intentos + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if Path(ruta).exists() and Path(ruta).stat().st_size > 0:
                log.info("Captura exitosa en %s (intento %d)", ruta.name, n)
                return True
            log.warning("Intento %d sin imagen válida: %s", n, r.stderr.strip()[-200:])
        except subprocess.TimeoutExpired:
            log.warning("Intento %d: tiempo de espera agotado al conectar a %s", n, C.RTSP_URL)
        except Exception as e:
            log.error("Error al ejecutar ffmpeg: %s", e)
    return False

def rotar(carpeta, maximo):
    """Mantiene solo las últimas `maximo` fotos para proteger el espacio en disco."""
    try:
        carpeta = Path(carpeta)
        if not carpeta.exists():
            return
        fotos = sorted(carpeta.glob("mov_*.jpg"), key=lambda p: p.stat().st_mtime)
        if maximo > 0 and len(fotos) > maximo:
            a_borrar = fotos[:-maximo]
            for p in a_borrar:
                p.unlink(missing_ok=True)
            log.info("Rotación: se eliminaron %d capturas antiguas", len(a_borrar))
    except Exception as e:
        log.error("Error en la rotación de capturas: %s", e)
