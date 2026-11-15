#!/bin/bash
# Quita el agente de soporte de Linux (servicio, archivos y configuración).
set -euo pipefail

SERVICIO="agente-soporte"

if [[ $EUID -ne 0 ]]; then
    echo "Ejecuta con sudo: sudo $0" >&2
    exit 1
fi

systemctl disable --now "$SERVICIO" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICIO}.service"
systemctl daemon-reload
rm -rf /opt/agente-soporte

echo "✔ Agente desinstalado. El equipo seguirá en el panel hasta que lo elimines de la lista."
