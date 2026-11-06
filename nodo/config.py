"""Configuración del Nodo de Seguridad para entorno Dockerizado."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
# Cargar .env si existe localmente (en Docker las variables se inyectan directamente)
load_dotenv(BASE / ".env")
load_dotenv(Path("/app/.env"))

def _int(nombre, defecto):
    try:
        return int(os.getenv(nombre, defecto))
    except (ValueError, TypeError):
        return defecto

# --- Credenciales ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip("\"'")
TELEGRAM_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID", "")).strip("\"'")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip("\"'")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip("\"'")

# --- Enlace al Dashboard / Video ---
DASHBOARD_PUBLIC_URL = os.getenv("DASHBOARD_PUBLIC_URL", "https://seguridad.lab-j.lat").rstrip("/")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "labj_seguridad_2026")
URL_VIVO = f"{DASHBOARD_PUBLIC_URL}/?auth={DASHBOARD_TOKEN}#video"

# --- Streaming y Captura ---
RTSP_URL = os.getenv("RTSP_URL", "rtsp://mediamtx:8554/cam")
PUERTO_RTSP = 8554

# --- Hardware y Lógica de Alertas ---
PIN_PIR = _int("PIN_PIR", 17)
MIN_SEGUNDOS = _int("MIN_SEGUNDOS", 5)
MIN_POSITIVOS = _int("MIN_POSITIVOS", 1)
COOLDOWN_ALERTA = _int("COOLDOWN_ALERTA", 60)
MAX_CAPTURAS = _int("MAX_CAPTURAS", 500)

# --- Rutas de Volúmenes Docker ---
CARPETA_CAPTURAS = Path(os.getenv("CARPETA_CAPTURAS", "/datos/capturas"))
CSV_RESULTADOS = Path(os.getenv("CSV_RESULTADOS", "/datos/resultados.csv"))
DIR_MODELOS_IA = Path(os.getenv("DIR_MODELOS_IA", "/modelos"))

# --- Umbrales de Modelos ---
UMBRAL_SSD = float(os.getenv("UMBRAL_SSD", "0.50"))
UMBRAL_EFFDET = float(os.getenv("UMBRAL_EFFDET", "0.50"))
UMBRAL_SSD2 = float(os.getenv("UMBRAL_SSD2", "0.50"))

# --- Base de Datos ---
DB_COLUMNAS_EXTRA = os.getenv("DB_COLUMNAS_EXTRA", "1") == "1"
TABLA_EVENTOS = "eventos_seguridad"
