param(
    [switch]$Offline,
    [string]$Wheelhouse = "",
    [string]$FfmpegDir = "",
    [string]$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    [switch]$SkipFfmpegDownload,
    [string]$DenoDir = "",
    [string]$DenoUrl = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
    [switch]$SkipDenoDownload
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
$FfmpegCacheDir = Join-Path $RootDir "dist\ffmpeg-cache"
$DenoCacheDir = Join-Path $RootDir "dist\deno-cache"
$WheelhouseWasProvided = -not [string]::IsNullOrWhiteSpace($Wheelhouse)
$FfmpegDirWasProvided = -not [string]::IsNullOrWhiteSpace($FfmpegDir)
$DenoDirWasProvided = -not [string]::IsNullOrWhiteSpace($DenoDir)

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

function Invoke-WebRequestWithRetry {
    param(
        [string]$Url,
        [string]$OutFile = "",
        [int]$Attempts = 5
    )

    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            if ([string]::IsNullOrWhiteSpace($OutFile)) {
                return (Invoke-WebRequest -Uri $Url -UseBasicParsing -UserAgent "YouTubeHarvester-Windows-Build")
            }
            Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -UserAgent "YouTubeHarvester-Windows-Build" |
                Out-Null
            return
        } catch {
            $lastError = $_
            if ($attempt -lt $Attempts) {
                $delay = [Math]::Min(10, [Math]::Pow(2, $attempt - 1))
                Write-Warning "Download attempt $attempt failed for $Url. Retrying in $delay seconds."
                Start-Sleep -Seconds ([int]$delay)
            }
        }
    }
    throw "Download failed after $Attempts attempts: $Url. $lastError"
}

function Get-RemoteSha256 {
    param([string]$Url)

    $response = Invoke-WebRequestWithRetry $Url
    $content = if ($response.Content -is [byte[]]) {
        [System.Text.Encoding]::UTF8.GetString([byte[]]$response.Content)
    } else {
        [string]$response.Content
    }
    $match = [regex]::Match($content, "(?i)\b[0-9a-f]{64}\b")
    if (-not $match.Success) {
        throw "Could not read SHA-256 from: $Url"
    }
    return $match.Value.ToLowerInvariant()
}

function Assert-FileSha256 {
    param(
        [string]$Path,
        [string]$Expected
    )

    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "SHA-256 mismatch for '$Path'. Expected $Expected, got $actual."
    }
    Write-Host "SHA-256 verified: $actual"
}

function Get-FfmpegBinDirFrom {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    $item = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $item -or -not $item.PSIsContainer) {
        return $null
    }

    $candidates = @(
        $item.FullName,
        (Join-Path $item.FullName "bin")
    )
    foreach ($candidate in $candidates) {
        if (
            (Test-Path (Join-Path $candidate "ffmpeg.exe")) -and
            (Test-Path (Join-Path $candidate "ffprobe.exe"))
        ) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }

    return $null
}

function Find-LocalFfmpegBinDir {
    param([string]$PreferredDir)

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($PreferredDir)) {
        $candidates += $PreferredDir
    }
    $candidates += @(
        (Join-Path $RootDir "tools\windows\ffmpeg"),
        (Join-Path $RootDir "ffmpeg"),
        (Join-Path $RootDir "..\ffmpeg")
    )

    foreach ($candidate in $candidates) {
        $found = Get-FfmpegBinDirFrom $candidate
        if ($found) {
            return $found
        }
    }

    $ffmpegCommand = Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue
    $ffprobeCommand = Get-Command "ffprobe.exe" -ErrorAction SilentlyContinue
    if ($ffmpegCommand -and $ffprobeCommand) {
        $ffmpegDir = Split-Path -Parent $ffmpegCommand.Source
        $ffprobeDir = Split-Path -Parent $ffprobeCommand.Source
        if ($ffmpegDir -eq $ffprobeDir) {
            return $ffmpegDir
        }
    }

    return $null
}

function Get-DownloadedFfmpegBinDir {
    param([string]$Url)

    New-Item -ItemType Directory -Force -Path $FfmpegCacheDir | Out-Null
    $zipPath = Join-Path $FfmpegCacheDir "ffmpeg-release-essentials.zip"
    $extractDir = Join-Path $FfmpegCacheDir "expanded"

    if (Test-Path $extractDir) {
        Remove-Item $extractDir -Recurse -Force
    }

    Write-Host "Downloading Windows ffmpeg/ffprobe:"
    Write-Host "  $Url"
    $expectedSha256 = Get-RemoteSha256 "${Url}.sha256"
    Invoke-WebRequestWithRetry $Url $zipPath
    Assert-FileSha256 $zipPath $expectedSha256
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $ffmpegExe = Get-ChildItem -LiteralPath $extractDir -Recurse -Filter "ffmpeg.exe" |
        Select-Object -First 1
    if (-not $ffmpegExe) {
        throw "Downloaded ffmpeg archive does not contain ffmpeg.exe"
    }

    $binDir = $ffmpegExe.Directory.FullName
    if (-not (Test-Path (Join-Path $binDir "ffprobe.exe"))) {
        throw "Downloaded ffmpeg archive does not contain ffprobe.exe next to ffmpeg.exe"
    }

    return $binDir
}

function Resolve-FfmpegBinDir {
    $found = Find-LocalFfmpegBinDir $FfmpegDir
    if ($found) {
        return $found
    }

    if ($Offline.IsPresent -or $SkipFfmpegDownload.IsPresent) {
        $expected = if ($FfmpegDirWasProvided) { $FfmpegDir } else { Join-Path $RootDir "..\ffmpeg" }
        throw "ffmpeg.exe and ffprobe.exe were not found. Put them in '$expected' or pass -FfmpegDir."
    }

    return Get-DownloadedFfmpegBinDir $FfmpegUrl
}

function Get-DenoExeFrom {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    $item = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $item) {
        return $null
    }
    if (-not $item.PSIsContainer) {
        if ($item.Name -ieq "deno.exe") {
            return $item.FullName
        }
        return $null
    }

    $candidates = @(
        (Join-Path $item.FullName "deno.exe"),
        (Join-Path $item.FullName "bin\deno.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }

    return $null
}

function Find-LocalDenoExe {
    param([string]$PreferredDir)

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($PreferredDir)) {
        $candidates += $PreferredDir
    }
    $candidates += @(
        (Join-Path $RootDir "tools\windows\deno"),
        (Join-Path $RootDir "deno"),
        (Join-Path $RootDir "..\deno")
    )

    foreach ($candidate in $candidates) {
        $found = Get-DenoExeFrom $candidate
        if ($found) {
            return $found
        }
    }

    $denoCommand = Get-Command "deno.exe" -ErrorAction SilentlyContinue
    if ($denoCommand) {
        return $denoCommand.Source
    }

    return $null
}

function Resolve-DenoDownloadUrl {
    if (-not [string]::IsNullOrWhiteSpace($DenoUrl)) {
        return $DenoUrl
    }

    Write-Host "Resolving latest Deno Windows x64 release..."
    $release = Invoke-RestMethod `
        -Uri "https://api.github.com/repos/denoland/deno/releases/latest" `
        -Headers @{ "User-Agent" = "YouTubeHarvester-Windows-Build" }
    $asset = $release.assets |
        Where-Object { $_.name -eq "deno-x86_64-pc-windows-msvc.zip" } |
        Select-Object -First 1
    if (-not $asset) {
        throw "Could not find deno-x86_64-pc-windows-msvc.zip in the latest Deno release."
    }
    return $asset.browser_download_url
}

function Get-DownloadedDenoExe {
    param([string]$Url)

    New-Item -ItemType Directory -Force -Path $DenoCacheDir | Out-Null
    $zipPath = Join-Path $DenoCacheDir "deno-x86_64-pc-windows-msvc.zip"
    $extractDir = Join-Path $DenoCacheDir "expanded"

    if (Test-Path $extractDir) {
        Remove-Item $extractDir -Recurse -Force
    }

    Write-Host "Downloading Windows Deno:"
    Write-Host "  $Url"
    $expectedSha256 = Get-RemoteSha256 "${Url}.sha256sum"
    Invoke-WebRequestWithRetry $Url $zipPath
    Assert-FileSha256 $zipPath $expectedSha256
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $denoExe = Get-ChildItem -LiteralPath $extractDir -Recurse -Filter "deno.exe" |
        Select-Object -First 1
    if (-not $denoExe) {
        throw "Downloaded Deno archive does not contain deno.exe"
    }

    return $denoExe.FullName
}

function Resolve-DenoExe {
    $found = Find-LocalDenoExe $DenoDir
    if ($found) {
        return $found
    }

    if ($Offline.IsPresent -or $SkipDenoDownload.IsPresent) {
        $expected = if ($DenoDirWasProvided) { $DenoDir } else { Join-Path $RootDir "..\deno" }
        throw "deno.exe was not found. Put it in '$expected' or pass -DenoDir."
    }

    return Get-DownloadedDenoExe (Resolve-DenoDownloadUrl)
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
        "pyinstaller==6.22.2",
        "pillow==12.3.0"
    )
} else {
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked $VenvPython @(
        "-m", "pip", "install",
        "--upgrade",
        "-r", (Join-Path $RootDir "requirements.txt"),
        "pyinstaller==6.22.2",
        "pillow==12.3.0"
    )
}

Invoke-Checked $VenvPython @(
    "-c",
    "import importlib.metadata, yt_dlp_ejs; print('yt-dlp-ejs ' + importlib.metadata.version('yt-dlp-ejs'))"
)

$FfmpegBinDir = Resolve-FfmpegBinDir
Write-Host "Bundling ffmpeg/ffprobe from:"
Write-Host "  $FfmpegBinDir"
$DenoExe = Resolve-DenoExe
Write-Host "Bundling Deno from:"
Write-Host "  $DenoExe"

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

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "YouTubeHarvester",
    "--icon", "$IconIco",
    "--collect-all", "yt_dlp",
    "--collect-all", "yt_dlp_ejs",
    "--add-data", "$RootDir\yth_common.py;.",
    "--add-data", "$RootDir\yth_updater.py;.",
    "--add-data", "$RootDir\yth_app_updater.py;.",
    "--add-data", "$RootDir\assets;assets",
    "--add-data", "$RootDir\scripts;scripts",
    "--add-binary", "$FfmpegBinDir\ffmpeg.exe;ffmpeg",
    "--add-binary", "$FfmpegBinDir\ffprobe.exe;ffmpeg",
    "--add-binary", "$DenoExe;deno",
    "--distpath", "$DistDir",
    "--workpath", "$WorkDir",
    "--specpath", "$SpecDir",
    (Join-Path $RootDir "tray_launcher.py")
)
Invoke-Checked $VenvPython $pyInstallerArgs

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $DistDir\YouTubeHarvester\YouTubeHarvester.exe"
