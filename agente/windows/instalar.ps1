# Instala el agente de soporte en Windows como tarea del sistema (cuenta SYSTEM).
# Arranca sola al encender el equipo, sin que nadie inicie sesión.
#
# Uso: doble clic en instalar.bat (pide permisos de administrador), o en PowerShell como administrador:
#      .\instalar.ps1                                   (usa config.json del paquete descargado)
#      .\instalar.ps1 -Servidor http://IP-DEL-PANEL:5711   (pide el token)
#Requires -RunAsAdministrator
param(
    [string]$Servidor = '',
    [string]$Token = $env:AGENT_TOKEN,
    [int]$Intervalo = 5
)
$ErrorActionPreference = 'Stop'

$Tarea   = 'AgenteSoporte'
$Carpeta = Join-Path $env:ProgramData 'AgenteSoporte'
$Origen  = Split-Path -Parent $PSScriptRoot

function Paso($texto) { Write-Host "-> $texto" -ForegroundColor Cyan }

# ---------- Configuración: la trae el paquete descargado desde el panel ----------
$configPaquete = Join-Path $Origen 'config.json'
if (Test-Path $configPaquete) {
    $cfg = Get-Content $configPaquete -Raw | ConvertFrom-Json
    if (-not $Servidor) { $Servidor = $cfg.servidor }
    if (-not $Token) { $Token = $cfg.token }
}
if (-not $Servidor) { $Servidor = Read-Host 'URL del panel (p. ej. http://192.168.1.10:5711)' }
if (-not $Token) {
    $seguro = Read-Host 'Token del agente' -AsSecureString
    $Token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
}

# ---------- Python 3.9+ instalado para todos los usuarios ----------
function Buscar-Python {
    foreach ($nombre in @('py', 'python')) {
        $cmd = Get-Command $nombre -ErrorAction SilentlyContinue
        # El "python" de WindowsApps solo abre la Microsoft Store: se ignora
        if ($cmd -and $cmd.Source -notlike '*WindowsApps*') {
            $extra = @(); if ($nombre -eq 'py') { $extra = @('-3') }
            $ruta = & $nombre @extra -c "import sys; print(sys.executable if sys.version_info >= (3, 9) else '')" 2>$null
            if ($ruta) { return $ruta.Trim() }
        }
    }
    $candidato = Get-ChildItem "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($candidato) { return $candidato.FullName }
    return $null
}

$python = Buscar-Python
if (-not $python) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Paso 'Instalando Python 3.12 con winget (puede tardar unos minutos)'
        winget install -e --id Python.Python.3.12 --scope machine --silent --accept-package-agreements --accept-source-agreements | Out-Null
        $python = Buscar-Python
    }
    if (-not $python) {
        Write-Host 'No se encontró Python 3.9+. Instálalo desde https://www.python.org/downloads/windows/' -ForegroundColor Red
        Write-Host 'marcando "Install for all users" y "Add python.exe to PATH", y vuelve a ejecutar este instalador.' -ForegroundColor Red
        exit 1
    }
}
Paso "Usando Python: $python"

# ---------- Detener una instalación anterior ----------
if (Get-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue) {
    Paso 'Deteniendo la versión anterior'
    Stop-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $Tarea -Confirm:$false
    Start-Sleep -Seconds 2
}

# ---------- Copiar el agente y crear su entorno ----------
Paso "Copiando el agente a $Carpeta"
New-Item -ItemType Directory -Force -Path $Carpeta | Out-Null
Copy-Item (Join-Path $Origen 'agente.py') $Carpeta -Force

Paso 'Creando entorno de Python e instalando psutil'
& $python -m venv (Join-Path $Carpeta 'venv')
$pip = Join-Path $Carpeta 'venv\Scripts\python.exe'
& $pip -m pip install --quiet --upgrade pip
& $pip -m pip install --quiet -r (Join-Path $Origen 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar psutil (¿hay conexión a internet?)' }

Paso 'Guardando configuración (solo SYSTEM y administradores pueden leerla)'
$rutaConfig = Join-Path $Carpeta 'config.json'
$json = @{ servidor = $Servidor; token = $Token; intervalo = $Intervalo } | ConvertTo-Json
# UTF-8 sin BOM: Python no lee bien el BOM de PowerShell 5
[IO.File]::WriteAllText($rutaConfig, $json, (New-Object Text.UTF8Encoding $false))
# S-1-5-18 = SYSTEM, S-1-5-32-544 = Administradores (funciona en Windows en cualquier idioma)
icacls $rutaConfig /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null

# ---------- Registrar la tarea que mantiene el agente corriendo ----------
Paso 'Registrando la tarea del sistema'
$pythonw = Join-Path $Carpeta 'venv\Scripts\pythonw.exe'
$log = Join-Path $Carpeta 'agente.log'
$accion = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$Carpeta\agente.py`" --log `"$log`"" -WorkingDirectory $Carpeta
$disparador = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $Tarea -Action $accion -Trigger $disparador -Principal $principal -Settings $ajustes `
    -Description 'Agente de soporte: envía el estado del equipo al panel de Test-Lab' | Out-Null
Start-ScheduledTask -TaskName $Tarea

Write-Host ''
Write-Host "Agente instalado. Registro: $log" -ForegroundColor Green

$rdp = Test-NetConnection -ComputerName 127.0.0.1 -Port 3389 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $rdp) {
    Write-Host ''
    Write-Host 'Aviso: el Escritorio remoto está desactivado, así que no podrás conectarte remotamente.' -ForegroundColor Yellow
    Write-Host 'Actívalo en Configuración > Sistema > Escritorio remoto (requiere Windows Pro o superior).' -ForegroundColor Yellow
}
