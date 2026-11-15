# Agente de soporte (macOS, Windows, Debian y Ubuntu)

Programa pequeño que se instala en cada equipo al que le das soporte. Cada 20 segundos
envía al panel (**Soporte → Equipos**):

- Nombre del equipo, modelo, número de serie, sistema operativo y usuario con sesión abierta
- CPU, memoria y discos (uso y espacio)
- Red: velocidad de bajada/subida en tiempo real por interfaz y su IP
- Batería y tiempo encendido
- Si **VNC / Compartir pantalla**, **SSH** y **Escritorio remoto** (RDP) están activos

El agente corre como servicio del sistema y arranca solo al encender el equipo:

| Sistema | Cómo corre | Carpeta | Registro |
| --- | --- | --- | --- |
| macOS | LaunchDaemon (root) | `/Library/Application Support/AgenteSoporte` | `/Library/Logs/AgenteSoporte.log` |
| Windows | Tarea programada (SYSTEM) | `C:\ProgramData\AgenteSoporte` | `C:\ProgramData\AgenteSoporte\agente.log` |
| Debian / Ubuntu | Servicio systemd `agente-soporte` | `/opt/agente-soporte` | `journalctl -u agente-soporte -f` |

## La forma fácil: descargar desde el panel

En **Soporte → Equipos → Instalar el agente** escribe la dirección del panel en la red y
pulsa el botón del sistema. El `.zip` ya trae `config.json` con la dirección y el token,
así que la instalación no pregunta nada:

- **macOS:** `cd macos && sudo ./instalar.sh`
- **Windows:** doble clic en `windows\instalar.bat` (si no hay Python, lo instala con winget)
- **Debian / Ubuntu:** `cd linux && sudo ./instalar.sh` (instala `python3-venv` con apt si falta)

Los pasos de abajo son para instalar a mano desde esta carpeta.

## 1. Preparar el panel

En el `.env` del panel:

```
AGENT_TOKEN=<genera uno con: python -c "import secrets; print(secrets.token_urlsafe(32))">
HOST=0.0.0.0        # para que los Mac de la red puedan llegar al panel
FLASK_DEBUG=0       # recomendado cuando el panel es accesible desde la red
```

Reinicia el panel. Los Mac deben llegar al panel por la misma red local o por la VPN.

## 2. Instalar en cada Mac

Copia la carpeta `agente/` al Mac (USB, AirDrop, `scp`…) y en Terminal:

```bash
cd agente/macos
sudo ./instalar.sh http://IP-DEL-PANEL:5711
```

Te pide el token (el `AGENT_TOKEN` del panel). Si el Mac no tiene Python 3, primero
ejecuta `xcode-select --install`.

En unos segundos el equipo aparece en **Soporte → Equipos**.

## 3. Activar el acceso remoto en el Mac

macOS no tiene servidor RDP; usa **Compartir pantalla** (VNC). Apple no permite
activarlo por script sin un MDM, así que se hace una vez a mano en cada Mac:

1. **Ajustes del Sistema → General → Compartir**
2. Activa **Compartir pantalla** (o **Gestión remota** si usas Apple Remote Desktop)
3. En "Permitir acceso a", deja **Solo estos usuarios → Administradores**
4. Opcional: activa **Sesión remota** para conectarte por SSH

El panel avisa en cada equipo si Compartir pantalla está desactivado.

## 4. Conectarte a un equipo

En el detalle del equipo, **Compartir pantalla** abre un enlace `vnc://IP`:

- **Desde un Mac:** se abre la app Compartir pantalla.
- **Desde Linux:** Remmina abre los enlaces `vnc://`. Si el navegador no lo abre, usa
  **Copiar IP** y conéctate con `remmina -c vnc://IP`.
- **Desde Windows:** usa un cliente VNC (TigerVNC, RealVNC) con la IP.

Inicia sesión con un **usuario administrador del Mac**. Las contraseñas no se guardan
en el panel.

## Mantenimiento

| Acción | Comando en el Mac |
| --- | --- |
| Ver el registro | `tail -f /Library/Logs/AgenteSoporte.log` |
| Reiniciar el agente | `sudo launchctl kickstart -k system/com.agentesoporte.agente` |
| Actualizar | volver a ejecutar `sudo ./instalar.sh http://IP-DEL-PANEL:5711` |
| Desinstalar | `sudo ./desinstalar.sh` |

En **Windows**: reiniciar con `Restart-ScheduledTask AgenteSoporte` (PowerShell como
administrador), desinstalar con doble clic en `windows\desinstalar.bat`.
En **Linux**: reiniciar con `sudo systemctl restart agente-soporte`, desinstalar con
`sudo ./linux/desinstalar.sh`.

## Probar sin instalar

```bash
pip install psutil
python3 agente.py --una-vez --mostrar                         # solo imprime el reporte
python3 agente.py --servidor http://127.0.0.1:5711 --token XXX # envía al panel cada 5 s
```

## Seguridad

- El token va en `/Library/Application Support/AgenteSoporte/config.json`, que solo root puede leer.
- Si cambias `AGENT_TOKEN` en el panel, hay que reinstalar el agente en todos los equipos.
- El tráfico va por HTTP: úsalo solo en tu red local o VPN. Si el panel queda en
  internet, ponlo detrás de HTTPS (por ejemplo con nginx) y usa `https://` en el instalador.
