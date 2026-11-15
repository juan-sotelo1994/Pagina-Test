# Quita el agente de soporte de Windows (tarea, archivos y configuración).
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'

$Tarea = 'AgenteSoporte'
$Carpeta = Join-Path $env:ProgramData 'AgenteSoporte'

if (Get-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $Tarea -Confirm:$false
    Start-Sleep -Seconds 2
}
if (Test-Path $Carpeta) { Remove-Item $Carpeta -Recurse -Force }

Write-Host 'Agente desinstalado. El equipo seguirá en el panel hasta que lo elimines de la lista.' -ForegroundColor Green
