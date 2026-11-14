#!/bin/bash
# Detiene y elimina el agente de soporte de este Mac.
set -euo pipefail

ETIQUETA="com.agentesoporte.agente"
PLIST="/Library/LaunchDaemons/${ETIQUETA}.plist"

if [[ $EUID -ne 0 ]]; then
    echo "Ejecuta con sudo: sudo $0" >&2
    exit 1
fi

launchctl bootout system "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
rm -rf "/Library/Application Support/AgenteSoporte"
rm -f "/Library/Logs/AgenteSoporte.log"
echo "✔ Agente desinstalado."
