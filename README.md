# YT Harvester

YT Harvester is a Linux tray application for watching YouTube channels and a manual video queue, downloading new videos through `yt-dlp`, and optionally sending Telegram notifications.

## Install on Linux Mint / Ubuntu-like systems

Download the deb package from `dist/` or a GitHub release, then run:

```bash
sudo apt install ./yt-harvester_0.1.0_all.deb
```

After installation, edit:

```bash
~/.config/yt-harvester/.env
```

Fill `BOT_TOKEN` and `CHANNEL_ID`, then start **YT Harvester** from the Internet menu or run:

```bash
yt-harvester
```

## User Data

Installed package data lives outside `/opt`:

- `~/.local/share/yt-harvester`
- `~/.config/yt-harvester/.env`
- `~/.cache/yt-harvester`

Source-tree runs keep using the current project directory by default.

## Build Deb

```bash
packaging/build_deb.sh 0.1.0
```

The package is written to:

```bash
dist/yt-harvester_0.1.0_all.deb
```

