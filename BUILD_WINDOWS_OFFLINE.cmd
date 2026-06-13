@echo off
setlocal

set "SOURCE_DIR=%~dp0"
set "BUNDLE_DIR=%SOURCE_DIR%.."
set "WHEELHOUSE=%BUNDLE_DIR%\wheelhouse"
set "WINDOWS_RELEASE=%BUNDLE_DIR%\release-windows"

if not exist "%WHEELHOUSE%" (
    echo Wheelhouse not found: "%WHEELHOUSE%"
    echo.
    echo Put the wheelhouse folder next to the source folder:
    echo   YouTubeHarvester-0.2.2-beta-offline\wheelhouse
    echo   YouTubeHarvester-0.2.2-beta-offline\source
    exit /b 1
)

set "PIP_NO_INDEX=1"
set "PIP_FIND_LINKS=%WHEELHOUSE%"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SOURCE_DIR%packaging\windows\build_release.ps1" -Offline -Wheelhouse "%WHEELHOUSE%"
if errorlevel 1 exit /b %errorlevel%

if not exist "%WINDOWS_RELEASE%" mkdir "%WINDOWS_RELEASE%"
copy /Y "%SOURCE_DIR%dist\release\YouTubeHarvester_0.2.2-beta_windows*" "%WINDOWS_RELEASE%\" >nul 2>nul
copy /Y "%SOURCE_DIR%dist\release\SHA256SUMS-windows.txt" "%WINDOWS_RELEASE%\" >nul 2>nul

echo.
echo Windows release files:
echo   %SOURCE_DIR%dist\release
echo.
echo Copied to:
echo   %WINDOWS_RELEASE%
