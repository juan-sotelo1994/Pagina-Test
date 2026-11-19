# Crea el usuario y la base de datos del panel en PostgreSQL 18.
# Uso (desde la carpeta del proyecto):  powershell -ExecutionPolicy Bypass -File db\crear_base.ps1
# Pide la contraseña del usuario «postgres» (la que pusiste al instalar PostgreSQL).
# Los datos de la base nueva salen de DATABASE_URL en el archivo .env.

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$envArchivo = Join-Path $raiz '.env'

$linea = Get-Content -LiteralPath $envArchivo -Encoding UTF8 | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
if (-not $linea) { throw 'No encontré DATABASE_URL en el archivo .env.' }
$url = ($linea -split '=', 2)[1].Trim()
if ($url -notmatch '^postgres(ql)?://(?<usuario>[^:]+):(?<clave>[^@]+)@(?<servidor>[^:/]+)(:(?<puerto>\d+))?/(?<base>[^?]+)') {
    throw 'DATABASE_URL no tiene el formato postgresql://usuario:clave@servidor:puerto/base'
}
# Se copian ya: cualquier -match posterior reemplaza $Matches
$usuario, $clave, $servidor, $base = $Matches.usuario, $Matches.clave, $Matches.servidor, $Matches.base
$puerto = if ($Matches.puerto) { $Matches.puerto } else { '5432' }

$psql = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\18\\' } | Select-Object -First 1
if (-not $psql) { $psql = Get-Command psql -ErrorAction SilentlyContinue }
if (-not $psql) { throw 'No encontré psql de PostgreSQL 18.' }

Write-Host "Creando el usuario '$usuario' y la base '$base' en ${servidor}:${puerto} ..."
Write-Host 'Escribe la contraseña del usuario postgres cuando la pida.'
& $psql.FullName -U postgres -h $servidor -p $puerto -d postgres -v ON_ERROR_STOP=1 `
    -v "usuario=$usuario" -v "clave=$clave" -v "base=$base" `
    -f (Join-Path $PSScriptRoot 'crear_base.sql')
if ($LASTEXITCODE -ne 0) { throw 'psql terminó con error.' }
Write-Host ''
Write-Host 'Listo. Ahora crea las tablas con:  .venv\Scripts\python.exe db\migrar.py'
