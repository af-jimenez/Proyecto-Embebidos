"""Servidor Web y Dashboard Unificado con Autenticación y Streaming Optimizado (FastAPI)."""
import os
import csv
import hmac
import hashlib
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, FileResponse, Response, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx

app = FastAPI(title="Dashboard de Seguridad IoT")

BASE_DIR = Path(__file__).resolve().parent
CAPTURA_DIR = Path("/datos/capturas")
CSV_PATH = Path("/datos/resultados.csv")
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Variables de Configuración y Seguridad
MEDIAMTX_HLS_URL = os.getenv("MEDIAMTX_HLS_URL", "http://127.0.0.1:8888").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "javeriana2026")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "labj_seguridad_2026")
COOKIE_NAME = "seguridad_session"

# Pool HTTP Persistente para Streaming HLS (evita sobrecarga de TCP)
hls_client = httpx.AsyncClient(
    base_url=MEDIAMTX_HLS_URL,
    timeout=httpx.Timeout(10.0, connect=3.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
)

def generar_session_token():
    return hmac.new(DASHBOARD_PASSWORD.encode(), b"seguridad_session_valida", hashlib.sha256).hexdigest()

def esta_autenticado(request: Request) -> bool:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and hmac.compare_digest(cookie, generar_session_token()):
        return True
    return False

@app.middleware("http")
async def verificar_seguridad(request: Request, call_next):
    path = request.url.path

    # Rutas públicas sin autenticación
    if path in ("/login", "/favicon.ico") or path.startswith("/static/"):
        return await call_next(request)

    # Acceso por token directo en URL (ej. enlace de Telegram ?auth=TOKEN)
    token_query = request.query_params.get("auth")
    if token_query and hmac.compare_digest(token_query, DASHBOARD_TOKEN):
        response = await call_next(request)
        response.set_cookie(
            key=COOKIE_NAME,
            value=generar_session_token(),
            max_age=7 * 24 * 3600,
            httponly=True,
            samesite="lax",
        )
        return response

    # Verificar sesión por cookie
    if esta_autenticado(request):
        return await call_next(request)

    # Si no está autenticado:
    if path.startswith(("/api/", "/stream/", "/capturas/")):
        return Response(content='{"error": "No autorizado"}', status_code=401, media_type="application/json")

    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if esta_autenticado(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, password: str = Form(...)):
    if password == DASHBOARD_PASSWORD:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key=COOKIE_NAME,
            value=generar_session_token(),
            max_age=7 * 24 * 3600,
            httponly=True,
            samesite="lax",
        )
        return response
    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Clave incorrecta. Inténtalo de nuevo."})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response

def get_telemetria():
    """Lee métricas de hardware de la Raspberry Pi."""
    temp_str = "N/D"
    for p in ["/sys/class/thermal/thermal_zone0/temp", "/sys/class/hwmon/hwmon0/temp1_input"]:
        try:
            if os.path.exists(p):
                with open(p, "r") as f:
                    temp_str = f"{int(f.read().strip()) / 1000:.1f} °C"
                    break
        except Exception:
            continue

    mem_info = {"total": "1.0 GB", "usada": "N/D", "pct": 0}
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        data = {}
        for l in lines:
            parts = l.split(":")
            if len(parts) == 2:
                data[parts[0].strip()] = int(parts[1].split()[0])
        total = data.get("MemTotal", 0)
        avail = data.get("MemAvailable", 0)
        if total > 0:
            usada = total - avail
            mem_info["total"] = f"{total / 1024 / 1024:.1f} GB"
            mem_info["usada"] = f"{usada / 1024:.0f} MB"
            mem_info["pct"] = int((usada / total) * 100)
    except Exception:
        pass

    return {"temperatura": temp_str, "memoria": mem_info}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    telemetria = get_telemetria()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "telemetria": telemetria,
            "public_url": os.getenv("DASHBOARD_PUBLIC_URL", ""),
        }
    )

@app.get("/api/estado")
async def api_estado():
    return get_telemetria()

@app.get("/api/eventos")
async def api_eventos():
    """Obtiene eventos desde Supabase o recurre al CSV local si no hay internet."""
    eventos = []
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    f"{SUPABASE_URL}/rest/v1/eventos_seguridad?select=*&order=id.desc&limit=25",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Authorization": f"Bearer {SUPABASE_KEY}",
                    }
                )
                if r.is_success:
                    return {"fuente": "supabase", "data": r.json()}
        except Exception:
            pass

    # Fallback local desde CSV
    if CSV_PATH.exists():
        try:
            with open(CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                filas = list(reader)
                agrupados = {}
                for row in reversed(filas):
                    img = row.get("imagen")
                    if img not in agrupados:
                        agrupados[img] = {
                            "created_at": row.get("fecha"),
                            "imagen": img,
                            "confianza_ia": float(row.get("confianza", 0)),
                            "estado_alerta": "offline_csv",
                            "modelos": []
                        }
                    agrupados[img]["modelos"].append({
                        "modelo": row.get("modelo"),
                        "positivo": row.get("positivo") == "1",
                        "confianza": float(row.get("confianza", 0)),
                        "ms": int(row.get("ms", 0))
                    })
                return {"fuente": "csv_local", "data": list(agrupados.values())[:25]}
        except Exception:
            pass

    return {"fuente": "ninguna", "data": []}

@app.get("/api/capturas")
async def api_capturas():
    """Lista las capturas guardadas en el disco."""
    if not CAPTURA_DIR.exists():
        return []
    archivos = sorted(CAPTURA_DIR.glob("mov_*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{
        "archivo": a.name,
        "tamano_kb": int(a.stat().st_size / 1024),
        "fecha": datetime.fromtimestamp(a.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    } for a in archivos[:40]]

@app.get("/capturas/{nombre}")
async def servir_captura(nombre: str):
    """Entrega la imagen fotográfica solicitada."""
    archivo = CAPTURA_DIR / nombre
    if not archivo.exists() or not archivo.is_file():
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    return FileResponse(archivo, media_type="image/jpeg")

@app.get("/stream/hls/{ruta:path}")
async def proxy_hls(ruta: str):
    """Proxy HTTP inverso optimizado con pool persistente para MediaMTX."""
    try:
        r = await hls_client.get(f"/{ruta}")
        media_type = r.headers.get("content-type", "application/octet-stream")
        
        # Cabeceras de caché: no cachear listas de reproducción .m3u8, pero cachear segmentos estáticos .m4s/.mp4
        headers = {}
        if ruta.endswith(".m3u8"):
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        else:
            headers["Cache-Control"] = "public, max-age=10"

        return Response(content=r.content, status_code=r.status_code, media_type=media_type, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error conectando a MediaMTX: {e}")
