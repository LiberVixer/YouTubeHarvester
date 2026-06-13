# Сборка YouTube Harvester на офлайн Windows из `D:\Git`

Эта инструкция рассчитана на твою машину:

- Windows без интернета
- Python 3.11.0 x64 или Python 3.12.x x64
- Git for Windows 2.54.0 x64
- Inno Setup 6.0.5 Rus
- WiX Toolset v7.0.0
- Общая папка Linux: `/media/sf_Data/Git`
- Та же папка в Windows: `D:\Git`

## 1. Что уже лежит в `D:\Git`

Я подготовил папку:

```text
D:\Git\YouTubeHarvester-0.2.2-beta-offline
```

Внутри:

```text
source\          исходники программы
wheelhouse\      Python wheel-зависимости для Windows x64 / Python 3.11 и 3.12
release-linux\   уже собранные Linux-файлы
```

Главный файл для запуска сборки:

```text
D:\Git\YouTubeHarvester-0.2.2-beta-offline\source\BUILD_WINDOWS_OFFLINE.cmd
```

## 2. Проверить PATH

Открой PowerShell и выполни:

```powershell
python --version
git --version
wix --version
ISCC.exe /?
```

Ожидаемо:

```text
Python 3.11.0 или Python 3.12.x
git version 2.54.0.windows...
7.0.0
Inno Setup Compiler
```

Важно: если сейчас показывается `Python 3.11.0`, это нормально. Я добавил в
`wheelhouse` отдельные зависимости под Python 3.11.

Если `ISCC.exe /?` пишет, что команда не найдена, это не страшно, если Inno
Setup установлен в обычную папку. Сборочный скрипт сам попробует найти:

```text
C:\Program Files (x86)\Inno Setup 6\ISCC.exe
C:\Program Files\Inno Setup 6\ISCC.exe
```

Если `ISCC.exe` не найден, добавь Inno Setup в PATH для текущего окна PowerShell:

```powershell
$env:Path += ";C:\Program Files (x86)\Inno Setup 6"
```

Если `wix` не найден, найди `wix.exe` и добавь его папку в PATH. Обычно что-то вроде:

```powershell
$env:Path += ";C:\Program Files\WiX Toolset v7\bin"
```

или:

```powershell
$env:Path += ";C:\Program Files (x86)\WiX Toolset v7\bin"
```

После этого снова проверь:

```powershell
ISCC.exe /?
wix --version
```

## 3. Собрать Windows-релиз

В PowerShell:

```powershell
Set-Location "D:\Git\YouTubeHarvester-0.2.2-beta-offline\source"
.\BUILD_WINDOWS_OFFLINE.cmd
```

Или в обычном `cmd.exe`:

```bat
D:
cd \Git\YouTubeHarvester-0.2.2-beta-offline\source
BUILD_WINDOWS_OFFLINE.cmd
```

Скрипт делает:

1. Создаёт `.venv` внутри `source`.
2. Ставит зависимости только из локальной папки `..\wheelhouse`.
3. Собирает `YouTubeHarvester.exe` через PyInstaller.
4. Собирает portable ZIP.
5. Собирает installer EXE через Inno Setup.
6. Собирает MSI через WiX 7.
7. Считает SHA256.
8. Копирует готовые Windows-файлы в общую папку `release-windows`.

## 4. Где будут файлы

Основная папка результата:

```text
D:\Git\YouTubeHarvester-0.2.2-beta-offline\source\dist\release
```

Копия для удобства:

```text
D:\Git\YouTubeHarvester-0.2.2-beta-offline\release-windows
```

Ожидаемые файлы:

```text
YouTubeHarvester_0.2.2-beta_windows_portable.zip
YouTubeHarvester_0.2.2-beta_windows_setup.exe
YouTubeHarvester_0.2.2-beta_windows_x64.msi
SHA256SUMS-windows.txt
```

## 5. Быстрая проверка результата

Проверь portable-версию в PowerShell:

```powershell
Set-Location "D:\Git\YouTubeHarvester-0.2.2-beta-offline\source\dist\windows\YouTubeHarvester"
.\YouTubeHarvester.exe
```

Должно открыться приложение **YouTube Harvester 0.2.2-beta**.

Потом проверь установщики:

```powershell
D:\Git\YouTubeHarvester-0.2.2-beta-offline\release-windows\YouTubeHarvester_0.2.2-beta_windows_setup.exe
```

и:

```powershell
msiexec /i D:\Git\YouTubeHarvester-0.2.2-beta-offline\release-windows\YouTubeHarvester_0.2.2-beta_windows_x64.msi
```

## 6. Если не собрался installer EXE

Проверь Inno Setup:

```powershell
where ISCC.exe
ISCC.exe /?
```

Если `where ISCC.exe` ничего не показывает:

```powershell
$env:Path += ";C:\Program Files (x86)\Inno Setup 6"
```

И повтори:

```powershell
.\BUILD_WINDOWS_OFFLINE.cmd
```

## 7. Если не собрался MSI

Проверь WiX:

```powershell
where wix
wix --version
```

Если `wix` не найден, добавь путь к `wix.exe` в PATH.

Важно: у тебя WiX Toolset v7, поэтому сборочный скрипт использует новый `wix build`.
Старые `heat.exe`, `candle.exe`, `light.exe` не обязательны.

Если WiX пишет:

```text
WIX7015: You must accept the Open Source Maintenance Fee (OSMF) EULA
```

сначала открой и прочитай условия WiX OSMF/EULA:

```text
https://wixtoolset.org/osmf/
```

Если ты согласен с условиями, выполни один раз:

```powershell
wix eula accept wix7
```

После этого повтори:

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

Ключ `-Offline` заставляет pip ставить зависимости только из `wheelhouse`.

## 9. Что выкладывать на GitHub

Из Windows после сборки нужны файлы:

```text
D:\Git\YouTubeHarvester-0.2.2-beta-offline\release-windows\YouTubeHarvester_0.2.2-beta_windows_portable.zip
D:\Git\YouTubeHarvester-0.2.2-beta-offline\release-windows\YouTubeHarvester_0.2.2-beta_windows_setup.exe
D:\Git\YouTubeHarvester-0.2.2-beta-offline\release-windows\YouTubeHarvester_0.2.2-beta_windows_x64.msi
D:\Git\YouTubeHarvester-0.2.2-beta-offline\release-windows\SHA256SUMS-windows.txt
```

Linux-файлы уже лежат здесь:

```text
D:\Git\YouTubeHarvester-0.2.2-beta-offline\release-linux
```
