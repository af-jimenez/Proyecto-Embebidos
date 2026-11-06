#!/usr/bin/env bash
# Descarga modelos TFLite y valida que sean archivos reales (cabecera "TFL3").
# Si la descarga falla o devuelve HTML, NO toca el archivo existente.
#
# Uso:  bash descargar_modelos.sh [carpeta_destino]     (por defecto: modelo_ia)
set -u
DEST="${1:-modelo_ia}"
mkdir -p "$DEST"

# Un .tflite válido tiene "TFL3" en los bytes 4-7
es_tflite() { [ "$(dd if="$1" bs=1 skip=4 count=4 2>/dev/null)" = "TFL3" ]; }

bajar() {  # bajar <url> <archivo_destino>
  local url="$1" out="$2" tmp
  tmp="$(mktemp)"
  if curl -fL --retry 3 -o "$tmp" "$url" && es_tflite "$tmp"; then
    mv "$tmp" "$out"
    echo "OK     -> $out ($(du -h "$out" | cut -f1))"
  else
    rm -f "$tmp"
    echo "FALLÓ  -> $url"
    echo "          (no se modificó $out)"
  fi
}

# EfficientDet-Lite0 (URL oficial del ejemplo de TensorFlow para Raspberry Pi)
bajar "https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/object_detection/rpi/lite-model_efficientdet_lite0_detection_metadata_1.tflite" \
      "$DEST/efficientdet_lite0.tflite"

# Verificación de los modelos que ya tengas en las carpetas
echo
echo "== Verificando archivos .tflite existentes =="
for f in "$DEST"/*.tflite modelo_yolo/*.tflite; do
  [ -f "$f" ] || continue
  if es_tflite "$f"; then echo "válido    $f"; else echo "CORRUPTO  $f  (bórralo)"; fi
done
