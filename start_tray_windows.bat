@echo off
setlocal
chcp 65001 >nul

set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

if not defined YTD_APP_DIR set "YTD_APP_DIR=%APP_DIR%"
if not defined YTD_DATA_DIR set "YTD_DATA_DIR=%LOCALAPPDATA%\YouTubeHarvester"
if not defined YTD_CONFIG_DIR set "YTD_CONFIG_DIR=%APPDATA%\YouTubeHarvester"
if not defined YTD_CACHE_DIR set "YTD_CACHE_DIR=%LOCALAPPDATA%\YouTubeHarvester\cache"
if not defined YTD_SETTINGS_FILE set "YTD_SETTINGS_FILE=%YTD_CONFIG_DIR%\settings.json"
if not defined YTD_SCHEDULES_FILE set "YTD_SCHEDULES_FILE=%YTD_CONFIG_DIR%\schedules.json"
if not defined YTD_ENV_FILE set "YTD_ENV_FILE=%YTD_CONFIG_DIR%\.env"
if not defined YTD_TEMP_DIR set "YTD_TEMP_DIR=%TEMP%\YTH"
if not defined YTD_FINAL_DIR set "YTD_FINAL_DIR=%USERPROFILE%\Downloads\YouTubeHarvester"
if not defined YTD_DOWNLOAD_ENGINE set "YTD_DOWNLOAD_ENGINE=python"

if not exist "%YTD_DATA_DIR%" mkdir "%YTD_DATA_DIR%"
if not exist "%YTD_CONFIG_DIR%" mkdir "%YTD_CONFIG_DIR%"
if not exist "%YTD_CACHE_DIR%" mkdir "%YTD_CACHE_DIR%"
if not exist "%YTD_TEMP_DIR%" mkdir "%YTD_TEMP_DIR%"
if not exist "%YTD_FINAL_DIR%" mkdir "%YTD_FINAL_DIR%"

if not exist "%YTD_ENV_FILE%" (
    > "%YTD_ENV_FILE%" echo # Telegram settings for YouTube Harvester.
    >> "%YTD_ENV_FILE%" echo # BOT_TOKEN=123456:telegram-bot-token
    >> "%YTD_ENV_FILE%" echo # CHANNEL_ID=-1001234567890
    >> "%YTD_ENV_FILE%" echo # PROXY_URL=127.0.0.1:9050
)

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%APP_DIR%\tray_launcher.py"
    exit /b
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%APP_DIR%\tray_launcher.py"
    exit /b
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py -3 "%APP_DIR%\tray_launcher.py"
    exit /b
)

python "%APP_DIR%\tray_launcher.py"
