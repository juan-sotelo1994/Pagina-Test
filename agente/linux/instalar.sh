#!/bin/bash
# Instala el agente de soporte en Linux (Debian / Ubuntu) como servicio de systemd.
# Corre como root, arranca solo al encender el equipo y se reinicia si se cae.
#
# Uso:  sudo ./instalar.sh                      (usa config.json del paquete descargado)
#       sudo ./instalar.sh http://IP-DEL-PANEL:5711   (pide el token)
set -euo pipefail

SERVICIO="agente-soporte"
CARPETA="/opt/agente-soporte"
UNIDAD="/etc/systemd/system/${SERVICIO}.service"
ORIGEN="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Ejecuta con sudo: sudo $0" >&2
    exit 1
fi

if ! command -v systemctl >/dev/null; then
    echo "Este instalador necesita systemd (Debian 10+ / Ubuntu 18.04+)." >&2
    exit 1
fi

# Python 3 con venv: en Debian/Ubuntu el módulo venv viene en un paquete aparte
if ! python3 -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    echo "→ Instalando Python 3 y venv (apt)"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    echo "Se necesita Python 3.9 o superior." >&2
    exit 1
fi

# El paquete descargado desde el panel trae config.json con la URL y el token
leer_config() {
    python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "$ORIGEN/config.json" "$1" 2>/dev/null || true
}

SERVIDOR="${1:-}"
TOKEN="${AGENT_TOKEN:-}"
if [[ -f "$ORIGEN/config.json" ]]; then
    SERVIDOR="${SERVIDOR:-$(leer_config servidor)}"
    TOKEN="${TOKEN:-$(leer_config token)}"
    INTERVALO="${INTERVALO:-$(leer_config intervalo)}"
fi
if [[ -z "$SERVIDOR" ]]; then
    read -rp "URL del panel (p. ej. http://192.168.1.10:5711): " SERVIDOR
fi
if [[ -z "$TOKEN" ]]; then
    read -rsp "Token del agente: " TOKEN
    echo
fi
INTERVALO="${INTERVALO:-20}"

echo "→ Copiando el agente a $CARPETA"
mkdir -p "$CARPETA"
cp "$ORIGEN/agente.py" "$CARPETA/agente.py"

echo "→ Creando entorno de Python e instalando psutil"
python3 -m venv "$CARPETA/venv"
"$CARPETA/venv/bin/pip" install --quiet --upgrade pip
"$CARPETA/venv/bin/pip" install --quiet -r "$ORIGEN/requirements.txt"

echo "→ Guardando configuración (solo root puede leerla)"
umask 077
python3 - "$CARPETA/config.json" "$SERVIDOR" "$TOKEN" "$INTERVALO" <<'PY'
import json, sys
ruta, servidor, token, intervalo = sys.argv[1:]
json.dump({'servidor': servidor, 'token': token, 'intervalo': int(intervalo)}, open(ruta, 'w'), indent=2)
PY
umask 022
chown -R root:root "$CARPETA"
chmod 600 "$CARPETA/config.json"

echo "→ Registrando el servicio"
cat > "$UNIDAD" <<EOF
[Unit]
Description=Agente de soporte (monitoreo del equipo)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=${CARPETA}/venv/bin/python ${CARPETA}/agente.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SERVICIO" >/dev/null
systemctl restart "$SERVICIO"

echo
echo "✔ Agente instalado. Registro: journalctl -u $SERVICIO -f"
if ! (exec 3<>/dev/tcp/127.0.0.1/22) 2>/dev/null; then
    echo
    echo "⚠ SSH no está activo, así que no podrás conectarte remotamente."
    echo "  Para activarlo: sudo apt install openssh-server"
fi
