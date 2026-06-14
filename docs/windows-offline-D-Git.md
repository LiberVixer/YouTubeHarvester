# Offline Windows Build From A Local Bundle

Эта инструкция описывает сборку Windows-артефактов на машине без доступа к
интернету. Она предполагает, что рядом лежат исходники проекта и заранее
скачанный `wheelhouse` с Python-зависимостями для Windows x64.

## 1. Подготовить папку

Скопируй на офлайн Windows-машину папку такого вида:

```text
YouTubeHarvester-offline\
  source\       исходники проекта
  wheelhouse\   Python wheel-зависимости для Windows x64
```

Главный файл сборки:

```text
YouTubeHarvester-offline\source\BUILD_WINDOWS_OFFLINE.cmd
```

## 2. Проверить инструменты

Открой PowerShell или `cmd.exe` и проверь:

```powershell
python --version
git --version
wix --version
ISCC.exe /?
```

Поддерживается Python 3.11 x64 или Python 3.12 x64. Для сборки установщиков
нужны Inno Setup 6 и WiX Toolset 7.

Если `ISCC.exe` не найден через `PATH`, сборочный скрипт также попробует найти
Inno Setup в стандартных папках:

```text
C:\Program Files (x86)\Inno Setup 6\ISCC.exe
C:\Program Files\Inno Setup 6\ISCC.exe
```

Если `wix` не найден, добавь папку с `wix.exe` в `PATH` для текущего окна.

## 3. Собрать Windows-релиз

В PowerShell:

```powershell
Set-Location "<offline-bundle>\source"
.\BUILD_WINDOWS_OFFLINE.cmd
```

В `cmd.exe`:

```bat
cd /d <offline-bundle>\source
BUILD_WINDOWS_OFFLINE.cmd
```

Скрипт:

1. Создаёт `.venv` внутри `source`.
2. Ставит зависимости только из локальной папки `..\wheelhouse`.
3. Собирает `YouTubeHarvester.exe` через PyInstaller.
4. Собирает portable ZIP.
5. Собирает installer EXE через Inno Setup.
6. Собирает MSI через WiX 7.
7. Считает SHA256.
8. Копирует готовые Windows-файлы в `<offline-bundle>\release-windows`.

## 4. Где будут файлы

Основная папка результата:

```text
<offline-bundle>\source\dist\release
```

Копия для удобства:

```text
<offline-bundle>\release-windows
```

Ожидаемые файлы:

```text
YouTubeHarvester_0.2.2-beta_windows_portable.zip
YouTubeHarvester_0.2.2-beta_windows_setup.exe
YouTubeHarvester_0.2.2-beta_windows_x64.msi
SHA256SUMS-windows.txt
```

## 5. Быстрая проверка результата

Проверь portable-версию:

```powershell
Set-Location "<offline-bundle>\source\dist\windows\YouTubeHarvester"
.\YouTubeHarvester.exe
```

Должно открыться приложение **YouTube Harvester 0.2.2-beta**.

Потом можно проверить installer EXE и MSI из папки:

```text
<offline-bundle>\release-windows
```

## 6. Если не собрался installer EXE

Проверь Inno Setup:

```powershell
where ISCC.exe
ISCC.exe /?
```

Если команда не найдена, добавь папку Inno Setup в `PATH` или установи Inno
Setup 6.

## 7. Если не собрался MSI

Проверь WiX:

```powershell
where wix
wix --version
```

WiX Toolset 7 использует команду `wix build`; старые `heat.exe`, `candle.exe`,
`light.exe` не обязательны.

Если WiX пишет:

```text
WIX7015: You must accept the Open Source Maintenance Fee (OSMF) EULA
```

прочитай условия WiX OSMF/EULA:

```text
https://wixtoolset.org/osmf/
```

Если согласен с условиями, выполни один раз:

```powershell
wix eula accept wix7
```

После этого повтори сборку:

```powershell
.\BUILD_WINDOWS_OFFLINE.cmd
```

## 8. Если pip пытается выйти в интернет

Запускай именно:

```powershell
.\BUILD_WINDOWS_OFFLINE.cmd
```

или вручную:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_release.ps1 -Offline -Wheelhouse ..\wheelhouse
```

Ключ `-Offline` заставляет pip ставить зависимости только из локального
`wheelhouse`.
