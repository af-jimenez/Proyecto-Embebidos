#!/bin/bash

ARCHIVO="recursos_$(date +%Y%m%d_%H%M%S).csv"

echo "fecha,ram_total_mib,ram_usada_mib,ram_disponible_mib,swap_usada_mib,cpu_proceso_pct,ram_proceso_kib" > "$ARCHIVO"

while true; do
    FECHA=$(date '+%Y-%m-%d %H:%M:%S')

    read TOTAL USADA DISPONIBLE SWAP < <(
        free -m | awk '/^Mem:/ {t=$2; u=$3; a=$7} /^Swap:/ {s=$3} END {print t,u,a,s}'
    )

    read CPU RSS < <(
        ps -C python -o %cpu=,rss= --sort=-rss |
        awk 'NR==1 {print $1,$2; exit}'
    )

    echo "$FECHA,$TOTAL,$USADA,$DISPONIBLE,$SWAP,${CPU:-0},${RSS:-0}" >> "$ARCHIVO"

    sleep 2
done
