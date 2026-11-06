"""Persistencia de incidentes: CSV local (offline) y Supabase (Cloud REST)."""
import csv
import logging
import requests
import config as C

log = logging.getLogger("registro")

def guardar_csv(fecha, imagen, resultados):
    """Guarda siempre los resultados en el archivo CSV local."""
    try:
        nuevo = not C.CSV_RESULTADOS.exists()
        C.CSV_RESULTADOS.parent.mkdir(parents=True, exist_ok=True)
        with open(C.CSV_RESULTADOS, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["fecha", "imagen", "modelo", "positivo", "confianza", "ms"])
            for r in resultados:
                w.writerow([
                    fecha,
                    imagen,
                    r["modelo"],
                    int(r["positivo"]),
                    f"{r['confianza']:.2f}",
                    r["ms"],
                ])
    except Exception as e:
        log.error("Error al escribir en CSV local: %s", e)

def _headers():
    return {
        "apikey": C.SUPABASE_KEY,
        "Authorization": f"Bearer {C.SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def crear_evento(confianza, resultados, imagen):
    """Registra una nueva intrusión en Supabase usando la API REST directa."""
    if not C.SUPABASE_URL or not C.SUPABASE_KEY:
        log.warning("No hay credenciales de Supabase configuradas; omitiendo registro en la nube.")
        return None

    url = f"{C.SUPABASE_URL.rstrip('/')}/rest/v1/{C.TABLA_EVENTOS}"
    payload = {
        "confianza_ia": round(float(confianza), 4),
        "estado_alerta": "pendiente",
        "imagen": imagen,
        "modelos_positivos": sum(r["positivo"] for r in resultados),
        "modelos_totales": len(resultados),
    }

    try:
        resp = requests.post(url, json=payload, headers=_headers(), timeout=10)
        if resp.status_code in (200, 201):
            data = resp.json()
            if data and isinstance(data, list):
                return data[0].get("id")
        log.warning("Supabase respondió con error %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        log.error("Fallo de conexión con Supabase (%s): %s", type(e).__name__, e)
    return None

def actualizar_estado(id_evento, estado):
    """Actualiza el estado de la alerta (ej. 'enviado' o 'error_telegram') en Supabase."""
    if not id_evento or not C.SUPABASE_URL or not C.SUPABASE_KEY:
        return
    url = f"{C.SUPABASE_URL.rstrip('/')}/rest/v1/{C.TABLA_EVENTOS}?id=eq.{id_evento}"
    try:
        requests.patch(url, json={"estado_alerta": estado}, headers=_headers(), timeout=10)
    except Exception as e:
        log.error("No se pudo actualizar el estado del evento #%s: %s", id_evento, e)

def ultimos_eventos(n=5):
    """Obtiene los últimos eventos registrados desde Supabase."""
    if not C.SUPABASE_URL or not C.SUPABASE_KEY:
        return []
    url = f"{C.SUPABASE_URL.rstrip('/')}/rest/v1/{C.TABLA_EVENTOS}?select=*&order=id.desc&limit={n}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=10)
        if resp.ok:
            return resp.json()
    except Exception as e:
        log.error("Error al consultar últimos eventos en Supabase: %s", e)
    return []
