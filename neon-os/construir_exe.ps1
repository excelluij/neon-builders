# Construye el programa NeonOS.exe (PyInstaller, formato carpeta, sin ventana de consola) con el logo de Neon OS.
#
#   .\construir_exe.ps1                     deja el resultado en .\dist_exe\NeonOS\
#   .\construir_exe.ps1 -Salida C:\otra     deja el resultado en C:\otra\NeonOS\
#
# Antes: si cambiaste logo.png, ejecuta  python preparar_logo.py  (genera logo_app.png y logo.ico).
# El .exe lleva dentro el código y el logo; el .env, neon_os.db y la carpeta materiales_neon NO se incluyen: van JUNTO a NeonOS.exe
# (al actualizar una instalación copia solo NeonOS.exe y la carpeta _internal, y conserva esos archivos). Ver docs/CORREO.md.
param([string]$Salida = (Join-Path $PSScriptRoot "dist_exe"))

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No encuentro $python. Crea el entorno: python -m venv .venv ; .venv\Scripts\python -m pip install -r requirements.txt pyinstaller" }
foreach ($archivo in "logo_app.png", "logo.ico", "APP_final.py") {
    if (-not (Test-Path (Join-Path $PSScriptRoot $archivo))) { throw "Falta $archivo (para el logo ejecuta: python preparar_logo.py)" }
}

& $python -m PyInstaller --noconfirm --clean --windowed --name NeonOS `
    --icon (Join-Path $PSScriptRoot "logo.ico") `
    --add-data ((Join-Path $PSScriptRoot "logo_app.png") + ";.") `
    --add-data ((Join-Path $PSScriptRoot "logo.ico") + ";.") `
    --distpath $Salida --workpath (Join-Path $Salida "_build") --specpath (Join-Path $Salida "_build") `
    (Join-Path $PSScriptRoot "APP_final.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló (código $LASTEXITCODE)" }
Write-Host "Listo: $(Join-Path $Salida 'NeonOS\NeonOS.exe')"
