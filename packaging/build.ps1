# Сборка системы видеомониторинга АЗС в установщик.
#
#   1. PyInstaller  -> dist\AZS-Monitoring\AZS-Monitoring.exe
#   2. Inno Setup   -> installer_output\AZS-Monitoring-Setup.exe
#
# Запуск из корня проекта:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1

$ErrorActionPreference = 'Stop'

$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
Write-Host "== Корень проекта: $root ==" -ForegroundColor Cyan

# --- Python из виртуального окружения проекта ---
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

# --- Убедимся, что PyInstaller установлен ---
Write-Host "== Проверка PyInstaller ==" -ForegroundColor Cyan
& $py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller не найден — устанавливаю..." -ForegroundColor Yellow
    & $py -m pip install pyinstaller
}

# --- Шаг 1: сборка .exe ---
Write-Host "== PyInstaller: сборка (это может занять много времени и места) ==" -ForegroundColor Cyan
& $py -m PyInstaller "AZS-Monitoring.spec" --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с ошибкой" }

$exe = Join-Path $root 'dist\AZS-Monitoring\AZS-Monitoring.exe'
if (-not (Test-Path $exe)) { throw "Не найден собранный exe: $exe" }
Write-Host "== .exe собран: $exe ==" -ForegroundColor Green

# --- Шаг 2: поиск компилятора Inno Setup ---
Write-Host "== Поиск Inno Setup (ISCC.exe) ==" -ForegroundColor Cyan
$iscc = $null
$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
foreach ($c in $candidates) { if (Test-Path $c) { $iscc = $c; break } }
if (-not $iscc) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}

if (-not $iscc) {
    Write-Host "Inno Setup не установлен." -ForegroundColor Yellow
    Write-Host "Установи его:  winget install -e --id JRSoftware.InnoSetup" -ForegroundColor Yellow
    Write-Host "Затем снова запусти этот скрипт (шаг сборки .exe пропустится при --clean — будет пересборка)." -ForegroundColor Yellow
    Write-Host ".exe уже готов в dist\AZS-Monitoring — установщик можно собрать позже." -ForegroundColor Green
    exit 0
}

# --- Шаг 3: сборка установщика ---
Write-Host "== Inno Setup: сборка установщика ==" -ForegroundColor Cyan
& $iscc "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup завершился с ошибкой" }

$setup = Join-Path $root 'installer_output\AZS-Monitoring-Setup.exe'
Write-Host "==========================================" -ForegroundColor Green
Write-Host " ГОТОВО! Установщик: $setup" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
