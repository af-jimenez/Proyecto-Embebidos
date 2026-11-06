#!/usr/bin/env python3
"""
Compara modelos de detección sobre una carpeta de imágenes.
Cuenta personas por imagen y, si hay verdad.csv, mide aciertos y errores.

  python comparar_carpeta.py                      # usa imagenes_prueba/ y verdad.csv
  python comparar_carpeta.py --hilos 1 --repeticiones 5
"""
import argparse
import csv
import os
import statistics
import time

import numpy as np
from PIL import Image

try:
    from ai_edge_litert.interpreter import Interpreter
except ImportError:
    from tensorflow.lite.python.interpreter import Interpreter

# (nombre, ruta, umbral). EfficientDet da scores más bajos, por eso su umbral es menor.
MODELOS = [
    ("SSD v1", "modelo_ia/detect.tflite", 0.50),
    ("SSD v2", "modelo_ia/ssd_mobilenet_v2_coco_quant_postprocess.tflite", 0.50),
    ("EfficientDet-Lite0", "modelo_ia/efficientdet_lite0.tflite", 0.35),
]
ID_PERSONA = 0  # "person" es la clase 0 (base 0) en estos modelos COCO


def preparar(img_path, detalle):
    _, h, w, _ = detalle["shape"]
    pix = np.asarray(Image.open(img_path).convert("RGB").resize((w, h)))
    if detalle["dtype"] == np.float32:
        pix = (pix.astype(np.float32) - 127.5) / 127.5
    return np.expand_dims(pix.astype(detalle["dtype"]), 0)


def leer(interp, d):
    t = interp.get_tensor(d["index"])
    if t.dtype != np.float32:
        escala, zero = d["quantization"]
        if escala > 0:
            t = (t.astype(np.float32) - zero) * escala
    return t


def clases_y_scores(interp, outs):
    salidas = [leer(interp, d) for d in outs]
    otros = [o.reshape(-1) for o in salidas if o.ndim == 2]
    entera = lambda a: np.allclose(a, np.round(a))
    cand = [o for o in otros if o.max() <= 1.0 and not entera(o)]
    scores = cand[0] if cand else otros[1]
    clases = next(o for o in otros if o is not scores)
    return clases, scores


def evaluar(nombre, ruta, umbral, imagenes, verdad, args):
    interp = Interpreter(model_path=ruta, num_threads=args.hilos)
    interp.allocate_tensors()
    entrada = interp.get_input_details()[0]
    outs = interp.get_output_details()
    filas = []
    for img in imagenes:
        interp.set_tensor(entrada["index"], preparar(img, entrada))
        interp.invoke()  # calentamiento
        t = []
        for _ in range(args.repeticiones):
            a = time.perf_counter()
            interp.invoke()
            t.append((time.perf_counter() - a) * 1000)
        cl, sc = clases_y_scores(interp, outs)
        n = sum(1 for c, s in zip(cl, sc) if int(c) == ID_PERSONA and s >= umbral)
        filas.append((os.path.basename(img), n, statistics.mean(t)))
    return filas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta", default="imagenes_prueba")
    ap.add_argument("--verdad", default="verdad.csv")
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--repeticiones", type=int, default=5)
    args = ap.parse_args()

    imagenes = sorted(os.path.join(args.carpeta, f) for f in os.listdir(args.carpeta)
                      if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if not imagenes:
        raise SystemExit(f"No hay imágenes en {args.carpeta}/")

    verdad = {}
    if os.path.exists(args.verdad):
        with open(args.verdad) as f:
            verdad = {r["imagen"]: int(r["personas"]) for r in csv.DictReader(f)}

    resumen = []
    for nombre, ruta, umbral in MODELOS:
        if not os.path.exists(ruta):
            print(f"\n[{nombre}] no encontrado en {ruta}, lo salto")
            continue
        try:
            filas = evaluar(nombre, ruta, umbral, imagenes, verdad, args)
        except Exception as e:
            print(f"\n[{nombre}] ERROR: {e}")
            continue
        print(f"\n=== {nombre} (umbral {umbral}) ===")
        exactos = sobran = faltan = 0
        falsas = perdidas = 0   # a nivel de imagen: ¿hubo alarma sin persona? ¿persona sin alarma?
        errores = []
        for img, n, ms in filas:
            real = verdad.get(img)
            txt = f"{img:<24} detecta {n:>2}"
            if real is not None:
                txt += f" | real {real:>2}"
                errores.append(abs(n - real))
                exactos += n == real
                sobran += max(0, n - real)
                faltan += max(0, real - n)
                falsas += real == 0 and n > 0
                perdidas += real > 0 and n == 0
            print(f"{txt} | {ms:6.1f} ms")
        resumen.append({
            "modelo": nombre,
            "ms": statistics.mean(f[2] for f in filas),
            "exactos": exactos, "con_verdad": len(errores),
            "mae": statistics.mean(errores) if errores else None,
            "sobran": sobran, "faltan": faltan,
            "falsas": falsas, "perdidas": perdidas,
        })

    print("\n\n================ RESUMEN ================")
    print(f"{'Modelo':<20}{'ms':>8}{'Exactos':>10}{'Error medio':>13}{'Sobran':>8}{'Faltan':>8}{'FalsaAlarma':>13}{'Perdidas':>10}")
    for r in resumen:
        ex = f"{r['exactos']}/{r['con_verdad']}" if r["con_verdad"] else "-"
        mae = f"{r['mae']:.2f}" if r["mae"] is not None else "-"
        print(f"{r['modelo']:<20}{r['ms']:>8.1f}{ex:>10}{mae:>13}{r['sobran']:>8}{r['faltan']:>8}{r['falsas']:>13}{r['perdidas']:>10}")
    print("\nSobran/Faltan = personas de más/de menos (conteo exacto).")
    print("FalsaAlarma = imágenes SIN personas donde el modelo alertó.")
    print("Perdidas = imágenes CON personas donde el modelo no detectó a nadie (lo más grave).")


if __name__ == "__main__":
    main()
