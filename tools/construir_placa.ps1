# construir_placa.ps1 · corre en orden los pasos de la fase 3 de la placa (tarea 3.10).
#
# Uso:
#   powershell -File tools/construir_placa.ps1                 # desde la colocación (conserva la placa creada)
#   powershell -File tools/construir_placa.ps1 -Setup          # además recrea la placa vacía con pcb_setup.py --forzar
#   powershell -File tools/construir_placa.ps1 -Placa placas/otra-placa
#
# Orden: colocar -> rutear -> costura -> DRC -> (unir_gnd -> rutear --reusar -> costura -> DRC) hasta que no queden
# grupos de GND sueltos -> serigrafía -> sincronizar con el esquemático -> DRC final.
# Cada herramienta es idempotente y determinista; el registro completo queda en reportes/construccion.txt.
# Cierra KiCad antes de correrlo. El ruteo completo tarda unos 25 a 40 minutos.
param(
    [string]$Placa = "placas/entrenamiento-328p",
    [switch]$Setup
)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
Set-Location (Split-Path -Parent $PSScriptRoot)
$registro = Join-Path $Placa "reportes/construccion.txt"
"Construccion de la placa" | Out-File $registro -Encoding utf8
$script:ultimo = 0

function Paso([string]$titulo, [string[]]$orden, [bool]$tolerar = $false) {
    Write-Host "== $titulo"
    Add-Content -Path $registro -Value "== $titulo" -Encoding utf8
    $salida = & py -3.12 -u -P @orden 2>&1 | ForEach-Object { "$_" }
    $script:ultimo = $LASTEXITCODE
    Add-Content -Path $registro -Value $salida -Encoding utf8
    $salida | Select-Object -Last 2 | ForEach-Object { Write-Host "   $_" }
    if ($script:ultimo -ne 0 -and -not $tolerar) { throw "Fallo: $titulo (codigo $($script:ultimo)). Mira $registro" }
}

if ($Setup) { Paso "pcb_setup --forzar" @("tools/pcb_setup.py", $Placa, "--forzar") }
Paso "colocar" @("tools/colocar.py", $Placa)
Paso "rutear (completo)" @("tools/rutear.py", $Placa) $true
Paso "costura" @("tools/costura.py", $Placa)
Paso "drc" @("tools/drc.py", $Placa) $true
foreach ($i in 1..5) {
    Paso "unir_gnd ($i)" @("tools/unir_gnd.py", $Placa) $true
    $ninguno = (Get-Content $registro | Select-String "No hay grupos de GND sueltos" | Measure-Object).Count -gt 0
    Paso "rutear --reusar ($i)" @("tools/rutear.py", $Placa, "--reusar") $true
    Paso "costura ($i)" @("tools/costura.py", $Placa)
    Paso "drc ($i)" @("tools/drc.py", $Placa) $true
    if ($ninguno) { break }
}
Paso "serigrafia" @("tools/serigrafia.py", $Placa)
Paso "sincronizar" @("tools/sincronizar.py", $Placa)
Paso "modelos3d" @("tools/modelos3d.py", $Placa)
Paso "drc (final)" @("tools/drc.py", $Placa) $true
Write-Host "Codigo final del DRC: $($script:ultimo)"
exit $script:ultimo
