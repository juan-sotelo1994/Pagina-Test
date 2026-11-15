#!/bin/bash
# Instala el agente de soporte en un Mac como servicio del sistema (LaunchDaemon).
# Corre como root, arranca solo al encender el equipo y se reinicia si se cae.
#
# Uso:  sudo ./instalar.sh http://IP-DEL-PANEL:5711
#       (pide el token del agente; es el AGENT_TOKEN del .env del panel)
set -euo pipefail

ETIQUETA="com.agentesoporte.agente"
CARPETA="/Library/Application Support/AgenteSoporte"
PLIST="/Library/LaunchDaemons/${ETIQUETA}.plist"
LOG="/Library/Logs/AgenteSoporte.log"
ORIGEN="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Ejecuta con sudo: sudo $0 http://IP-DEL-PANEL:5711" >&2
    exit 1
fi

SERVIDOR="${1:-}"
if [[ -z "$SERVIDOR" ]]; then
    read -rp "URL del panel (p. ej. http://192.168.1.10:5711): " SERVIDOR
fi
TOKEN="${AGENT_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
    read -rsp "Token del agente: " TOKEN
    echo
fi
INTERVALO="${INTERVALO:-5}"

# Python 3 viene con las herramientas de línea de comandos de Xcode
if ! /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    echo "Falta Python 3.9+. Instala las herramientas de Xcode con: xcode-select --install" >&2
    exit 1
fi

echo "→ Copiando el agente a $CARPETA"
mkdir -p "$CARPETA"
cp "$ORIGEN/agente.py" "$CARPETA/agente.py"

echo "→ Creando entorno de Python e instalando psutil"
/usr/bin/python3 -m venv "$CARPETA/venv"
"$CARPETA/venv/bin/pip" install --quiet --upgrade pip
"$CARPETA/venv/bin/pip" install --quiet -r "$ORIGEN/requirements.txt"

echo "→ Guardando configuración (solo root puede leerla)"
umask 077
/usr/bin/python3 - "$CARPETA/config.json" "$SERVIDOR" "$TOKEN" "$INTERVALO" <<'PY'
import json, sys
ruta, servidor, token, intervalo = sys.argv[1:]
json.dump({'servidor': servidor, 'token': token, 'intervalo': int(intervalo)}, open(ruta, 'w'), indent=2)
PY
umask 022
chown -R root:wheel "$CARPETA"
chmod 600 "$CARPETA/config.json"

echo "→ Registrando el servicio"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${ETIQUETA}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CARPETA}/venv/bin/python</string>
        <string>${CARPETA}/agente.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>${LOG}</string>
    <key>StandardErrorPath</key>
    <string>${LOG}</string>
</dict>
</plist>
EOF
chown root:wheel "$PLIST"
chmod 644 "$PLIST"

launchctl bootout system "$PLIST" 2>/dev/null || true
launchctl bootstrap system "$PLIST"

echo
echo "✔ Agente instalado. Registro: $LOG"
echo
if ! nc -z 127.0.0.1 5900 2>/dev/null; then
    echo "⚠ Compartir pantalla está desactivado, así que no podrás conectarte remotamente."
    echo "  Actívalo en: Ajustes del Sistema → General → Compartir → Compartir pantalla"
    echo "  (o 'Gestión remota' si usas Apple Remote Desktop) y permite el acceso a"
    echo "  los administradores. macOS no permite activarlo por script sin MDM."
fi
