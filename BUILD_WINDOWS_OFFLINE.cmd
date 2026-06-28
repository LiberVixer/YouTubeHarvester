@echo off
setlocal

set "SOURCE_DIR=%~dp0"
set "BUNDLE_DIR=%SOURCE_DIR%.."
set "WHEELHOUSE=%BUNDLE_DIR%\wheelhouse"
if not defined FFMPEG_DIR set "FFMPEG_DIR=%BUNDLE_DIR%\ffmpeg"
if not defined DENO_DIR set "DENO_DIR=%BUNDLE_DIR%\deno"
set "WINDOWS_RELEASE=%BUNDLE_DIR%\release-windows"

if not exist "%WHEELHOUSE%" (
    echo Wheelhouse not found: "%WHEELHOUSE%"
    echo.
    echo Put the wheelhouse folder next to the source folder:
    echo   YouTubeHarvester-0.2.5-beta-offline\wheelhouse
    echo   YouTubeHarvester-0.2.5-beta-offline\source
    exit /b 1
)

if not exist "%FFMPEG_DIR%\ffmpeg.exe" if not exist "%FFMPEG_DIR%\bin\ffmpeg.exe" (
    echo ffmpeg/ffprobe not found: "%FFMPEG_DIR%"
    echo.
    echo Put Windows x64 ffmpeg files next to the source folder:
    echo   YouTubeHarvester-0.2.5-beta-offline\ffmpeg\bin\ffmpeg.exe
    echo   YouTubeHarvester-0.2.5-beta-offline\ffmpeg\bin\ffprobe.exe
    echo.
    echo Or set FFMPEG_DIR to a folder that contains ffmpeg.exe and ffprobe.exe.
    exit /b 1
)
if not exist "%FFMPEG_DIR%\ffprobe.exe" if not exist "%FFMPEG_DIR%\bin\ffprobe.exe" (
    echo ffprobe not found: "%FFMPEG_DIR%"
    echo.
    echo Put ffprobe.exe next to ffmpeg.exe, or set FFMPEG_DIR to the correct folder.
    exit /b 1
)

if not exist "%DENO_DIR%\deno.exe" if not exist "%DENO_DIR%\bin\deno.exe" (
    echo Deno not found: "%DENO_DIR%"
    echo.
    echo Put Windows x64 deno next to the source folder:
    echo   YouTubeHarvester-0.2.5-beta-offline\deno\deno.exe
    echo.
    echo Or set DENO_DIR to a folder that contains deno.exe.
    exit /b 1
)

set "PIP_NO_INDEX=1"
set "PIP_FIND_LINKS=%WHEELHOUSE%"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SOURCE_DIR%packaging\windows\build_release.ps1" -Offline -Wheelhouse "%WHEELHOUSE%" -FfmpegDir "%FFMPEG_DIR%" -DenoDir "%DENO_DIR%"
if errorlevel 1 exit /b %errorlevel%

if not exist "%WINDOWS_RELEASE%" mkdir "%WINDOWS_RELEASE%"
copy /Y "%SOURCE_DIR%dist\release\YouTubeHarvester_0.2.5-beta_windows*" "%WINDOWS_RELEASE%\" >nul 2>nul
copy /Y "%SOURCE_DIR%dist\release\SHA256SUMS-windows.txt" "%WINDOWS_RELEASE%\" >nul 2>nul

echo.
echo Windows release files:
echo   %SOURCE_DIR%dist\release
echo.
echo Copied to:
echo   %WINDOWS_RELEASE%
