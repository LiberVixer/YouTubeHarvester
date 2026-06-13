param(
    [switch]$Offline,
    [string]$Wheelhouse = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
$IconPng = Join-Path $RootDir "assets\YTH-logo.png"
$IconIco = Join-Path $ScriptDir "yt-harvester.ico"
$DistDir = Join-Path $RootDir "dist\windows"
$WorkDir = Join-Path $RootDir "dist\pyinstaller-build"
$SpecDir = Join-Path $RootDir "dist\pyinstaller-spec"
$WheelhouseWasProvided = -not [string]::IsNullOrWhiteSpace($Wheelhouse)

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

if (-not (Test-Path $VenvPython)) {
    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        Invoke-Checked $pyLauncher.Source @("-3", "-m", "venv", (Join-Path $RootDir ".venv"))
    } else {
        Invoke-Checked "python" @("-m", "venv", (Join-Path $RootDir ".venv"))
    }
}

if (-not $Wheelhouse) {
    $Wheelhouse = Join-Path $RootDir "wheelhouse"
}

$OfflineMode = $Offline.IsPresent -or $WheelhouseWasProvided
if ($OfflineMode) {
    if (-not (Test-Path $Wheelhouse)) {
        throw "Offline wheelhouse was not found: $Wheelhouse"
    }
    Write-Host "Installing Python dependencies from local wheelhouse:"
    Write-Host "  $Wheelhouse"
    Invoke-Checked $VenvPython @(
        "-m", "pip", "install",
        "--no-index",
        "--disable-pip-version-check",
        "--find-links", "$Wheelhouse",
        "-r", (Join-Path $RootDir "requirements.txt"),
        "pyinstaller",
        "pillow"
    )
} else {
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked $VenvPython @(
        "-m", "pip", "install",
        "-r", (Join-Path $RootDir "requirements.txt"),
        "pyinstaller",
        "pillow"
    )
}

$iconScript = @"
from pathlib import Path
from PIL import Image

source = Path(r"$IconPng")
target = Path(r"$IconIco")
target.parent.mkdir(parents=True, exist_ok=True)
image = Image.open(source).convert("RGBA")
image.save(target, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
"@

$iconScript | & $VenvPython -
if ($LASTEXITCODE -ne 0) {
    throw "Icon conversion failed."
}

Invoke-Checked $VenvPython @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "YouTubeHarvester",
    "--icon", "$IconIco",
    "--collect-all", "yt_dlp",
    "--add-data", "$RootDir\assets;assets",
    "--add-data", "$RootDir\scripts;scripts",
    "--distpath", "$DistDir",
    "--workpath", "$WorkDir",
    "--specpath", "$SpecDir",
    (Join-Path $RootDir "tray_launcher.py")
)

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $DistDir\YouTubeHarvester\YouTubeHarvester.exe"
