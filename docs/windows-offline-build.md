# Offline Windows Build

Target machine used for the 0.2.2 Beta Windows build:

- Python 3.11 x64 or Python 3.12 x64
- Git for Windows x64
- Inno Setup 6
- WiX Toolset 7
- No internet access

## 1. Prepare Files On A Machine With Internet

Use a Windows x64 machine with the same Python version as the offline target
machine. For Python 3.11:

```powershell
git clone https://github.com/LiberVixer/YouTubeHarvester.git
cd YouTubeHarvester
py -3.11 -m pip download -r requirements.txt pyinstaller pillow pefile pywin32-ctypes -d wheelhouse
```

For Python 3.12:

```powershell
py -3.12 -m pip download -r requirements.txt pyinstaller pillow pefile pywin32-ctypes -d wheelhouse
```

Copy the whole `YouTubeHarvester` folder, including the new `wheelhouse` folder,
to the offline Windows machine.

If you already copied the repository another way, copy only `wheelhouse` into the
project root:

```text
YouTubeHarvester\
  wheelhouse\
  packaging\
  tray_launcher.py
  ...
```

## 2. Check Offline Windows Machine

Open PowerShell in the project root and check:

```powershell
python --version
git --version
ISCC.exe /?
wix --version
```

If `ISCC.exe` or `wix` is not found, add the Inno Setup and WiX `bin` folders to
`PATH`, then open PowerShell again.

## 3. Build Release Files Offline

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_release.ps1 -Offline -Wheelhouse .\wheelhouse
```

Expected output files:

```text
dist\release\YouTubeHarvester_0.2.2-beta_windows_portable.zip
dist\release\YouTubeHarvester_0.2.2-beta_windows_setup.exe
dist\release\YouTubeHarvester_0.2.2-beta_windows_x64.msi
dist\release\SHA256SUMS-windows.txt
```

## 4. If MSI Fails

The portable ZIP and Inno Setup EXE can still be valid even if MSI fails.
For WiX 7, make sure `wix.exe` is available in `PATH`.

The build script also supports old WiX 3 tools (`heat.exe`, `candle.exe`,
`light.exe`) as a fallback, but WiX 7 should be preferred.
