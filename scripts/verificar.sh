#!/usr/bin/env bash
# ==============================================================================
# Script de Verificación Integral del Sistema de Seguridad
# ==============================================================================
set -e

echo "=== VERIFICACIÓN DEL SISTEMA DE SEGURIDAD (DOCKER) ==="

# 1. Comprobar Contenedores
echo -n "1. Estado de los contenedores Docker: "
if docker compose ps | grep -q "Up"; then
    echo "OK"
    docker compose ps
else
    echo "ALERTA: Algunos o todos los contenedores no están activos."
fi

# 2. Comprobar Puertos
echo -n "2. Verificando puertos (8554 RTSP, 8888 HLS, 8000 Dashboard): "
for PORT in 8554 8888 8000; do
    if ss -ltn | grep -q ":$PORT "; then
        echo -n "[:$PORT OK] "
    else
        echo -n "[:$PORT NO ESCUCHA] "
    fi
done
echo ""

# 3. Comprobar Archivos de Modelos
echo "3. Verificando modelos en ./modelos:"
for M in detect.tflite efficientdet_lite0.tflite ssd_mobilenet_v2_coco_quant_postprocess.tflite labelmap.txt; do
    if [ -f "./modelos/$M" ]; then
        echo "   - $M: PRESENTE ($(du -h ./modelos/$M | cut -f1))"
    else
        echo "   - $M: FALTA"
    fi
done

# 4. Comprobar Dispositivos de Hardware
echo "4. Verificando hardware en la Raspberry Pi:"
[ -e /dev/video0 ] && echo "   - Cámara V4L2 (/dev/video0): DETECTADA" || echo "   - Cámara (/dev/video0): NO DETECTADA"
[ -e /dev/gpiochip0 ] && echo "   - Interfaz GPIO (/dev/gpiochip0): DETECTADA" || echo "   - GPIO (/dev/gpiochip0): NO DETECTADA"

# 5. Comprobar Temperatura y Carga
if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    TEMP=$(awk '{printf "%.1f °C\n", $1/1000}' /sys/class/thermal/thermal_zone0/temp)
    echo "5. Temperatura CPU: $TEMP"
fi

echo "=== FIN DE LA VERIFICACIÓN ==="
