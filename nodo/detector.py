"""Modelos de detección de personas con TensorFlow Lite. Se cargan una sola vez en memoria."""
import logging
import time
import numpy as np
from PIL import Image

try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite.python.interpreter import Interpreter

import config as C

log = logging.getLogger("detector")

NOMBRES = {
    "ia_ssd": "MobileNet SSD v1",
    "efficientdet": "EfficientDet-Lite0",
    "ssd2": "MobileNet SSD v2",
}

class _Deteccion:
    """Modelo con salidas estándar TFLite: cajas, clases, puntuaciones, cantidad."""
    def __init__(self, ruta, umbral, es_persona, hilos=2):
        self.interp = Interpreter(model_path=str(ruta), num_threads=hilos)
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.out = self.interp.get_output_details()
        self.h, self.w = self.inp["shape"][1], self.inp["shape"][2]
        self.umbral = umbral
        self.es_persona = es_persona

    def __call__(self, img):
        arr = np.asarray(img.resize((self.w, self.h)), dtype=self.inp["dtype"])
        self.interp.set_tensor(self.inp["index"], np.expand_dims(arr, 0))
        self.interp.invoke()
        clases = self.interp.get_tensor(self.out[1]["index"])[0]
        scores = self.interp.get_tensor(self.out[2]["index"])[0]
        n = int(np.ravel(self.interp.get_tensor(self.out[3]["index"]))[0])
        n = min(n, len(clases), len(scores))
        mejor = 0.0
        for i in range(n):
            if self.es_persona(int(clases[i])) and float(scores[i]) > mejor:
                mejor = float(scores[i])
        return mejor >= self.umbral, mejor

class Detector:
    def __init__(self):
        self.modelos = {}
        etiquetas_path = C.DIR_MODELOS_IA / "labelmap.txt"
        if not etiquetas_path.is_file():
            raise FileNotFoundError(f"No se encontró labelmap.txt en {etiquetas_path}")

        with open(etiquetas_path, "r", encoding="utf-8") as f:
            etiquetas = [l.strip().lower() for l in f]

        def persona_labelmap(c):
            i = c + 1
            return 0 <= i < len(etiquetas) and etiquetas[i] == "person"

        definiciones = [
            ("ia_ssd", "detect.tflite", C.UMBRAL_SSD, persona_labelmap),
            ("efficientdet", "efficientdet_lite0.tflite", C.UMBRAL_EFFDET, lambda c: c == 0),
            ("ssd2", "ssd_mobilenet_v2_coco_quant_postprocess.tflite", C.UMBRAL_SSD2, persona_labelmap),
        ]

        for clave, archivo, umbral, es_persona in definiciones:
            ruta = C.DIR_MODELOS_IA / archivo
            if not ruta.is_file():
                log.warning("Falta archivo de modelo: %s; se omite %s", ruta.name, clave)
                continue
            try:
                self.modelos[clave] = _Deteccion(ruta, umbral, es_persona)
                log.info("Modelo cargado exitosamente: %s", NOMBRES[clave])
            except Exception as e:
                log.exception("Error al cargar modelo %s: %s", clave, e)

        if not self.modelos:
            raise RuntimeError("No se pudo cargar ningún modelo TFLite desde " + str(C.DIR_MODELOS_IA))

    def analizar(self, ruta_imagen):
        img = Image.open(ruta_imagen).convert("RGB")
        resultados = []
        for clave, modelo in self.modelos.items():
            t0 = time.perf_counter()
            try:
                pos, conf = modelo(img)
            except Exception as e:
                log.exception("Error durante la inferencia con %s: %s", clave, e)
                continue
            resultados.append({
                "modelo": clave,
                "positivo": bool(pos),
                "confianza": float(conf),
                "ms": int((time.perf_counter() - t0) * 1000),
            })
        return resultados
