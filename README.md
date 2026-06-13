# YT Harvester

> 🇷🇺 [Русская версия ниже](#русский) · 🇬🇧 [English version](#english) · [Changelog](CHANGELOG.md)

<p align="center">
  <img src="assets/yt-harvester.png" alt="YT Harvester logo" width="128">
</p>

<p align="center">
  A Linux tray downloader for YouTube channels, manual video queues, schedules, and Telegram delivery.
  <br>
  <a href="#english">English</a> · <a href="#русский">Русский</a>
</p>

![Overview](docs/screenshots/overview.png)

## English

**YT Harvester** is a compact PyQt5 desktop app for Linux Mint, Ubuntu, and similar systems. It sits in the system tray, watches selected YouTube channels, downloads new videos through `yt-dlp`, keeps a manual queue, and can publish downloaded items to a Telegram channel.

### Highlights

- Tray-first app: open the main window from the tray icon or tray menu.
- Channel grid with cached channel images and per-channel toggles for videos, Shorts, and streams.
- Manual queue: paste a YouTube video URL, preview title/thumbnail, and download it with the same rules as the regular workflow.
- Built-in scheduler and queue view in one tab.
- Live overview with status, counters, current channel, current media type, and video thumbnail.
- Soft stop button: finishes safely instead of killing the downloader mid-step.
- Dark, light, and system theme modes.
- `.deb` package support for Linux Mint and Ubuntu-like distributions.

### Screenshots

| Channels | Queue & Scheduler |
| --- | --- |
| ![Channels](docs/screenshots/channels.png) | ![Queue and scheduler](docs/screenshots/queue.png) |

### Install From Deb

Download the latest package from [GitHub Releases](https://github.com/LiberVixer/YouTubeHarvester/releases) or use the package from `dist/`:

```bash
sudo apt install ./yt-harvester_0.2.0~beta1_all.deb
```

After installation, configure Telegram delivery:

```bash
nano ~/.config/yt-harvester/.env
```

Fill these values:

```bash
BOT_TOKEN=123456:telegram-bot-token
CHANNEL_ID=-1001234567890
```

Then start **YT Harvester** from the Internet menu or run:

```bash
yt-harvester
```

### Run From Source

```bash
sudo apt install python3 python3-pyqt5 yt-dlp curl bash coreutils findutils grep sed
cp .env.example .env
nano .env
./start_tray.sh
```

### Channel Rules

Each channel card has three small toggles:

- `🎬` videos
- `📱` Shorts
- `🔴` streams

Green means enabled, red means disabled. Rules are saved separately from `channels.txt`, so the channel list stays clean and easy to edit.

### User Data

Installed package data is stored outside `/opt`:

- data: `~/.local/share/yt-harvester`
- config: `~/.config/yt-harvester`
- cache: `~/.cache/yt-harvester`

Source-tree runs use the current project directory by default.

### Build Deb

```bash
packaging/build_deb.sh 0.2.0~beta1
```

The package will be written to:

```bash
dist/yt-harvester_0.2.0~beta1_all.deb
```

### Notes

YT Harvester uses `yt-dlp` for downloading. Make sure your use follows YouTube terms, copyright law, and the rules of your local jurisdiction.

---

## Русский

**YT Harvester** — небольшая программа для Linux Mint, Ubuntu и похожих систем. Она живёт в трее, следит за выбранными YouTube-каналами, скачивает новые ролики через `yt-dlp`, умеет работать с ручной очередью и отправлять найденные видео в Telegram-канал.

### Возможности

- Работа из трея: окно открывается по иконке или из меню трея.
- Красивая сетка каналов с кешированными картинками.
- Для каждого канала можно отдельно включать и выключать скачивание видео, Shorts и стримов.
- Ручная очередь: вставил ссылку на YouTube-видео, увидел название/обложку, добавил в очередь.
- Планировщик и очередь объединены в одной вкладке.
- Вкладка обзора показывает статус, счётчики, текущий канал, тип поиска/скачивания и заставку видео.
- Кнопка остановки завершает скачивание мягко, без грубого убийства процесса.
- Ночной, дневной и системный режим темы.
- Готовая сборка `.deb` для Linux Mint и Ubuntu-подобных систем.

### Скриншоты

| Каналы | Очередь и планировщик |
| --- | --- |
| ![Каналы](docs/screenshots/channels.png) | ![Очередь и планировщик](docs/screenshots/queue.png) |

### Установка Deb

Скачайте пакет из [GitHub Releases](https://github.com/LiberVixer/YouTubeHarvester/releases) или используйте файл из `dist/`:

```bash
sudo apt install ./yt-harvester_0.2.0~beta1_all.deb
```

После установки заполните настройки Telegram:

```bash
nano ~/.config/yt-harvester/.env
```

Нужно указать:

```bash
BOT_TOKEN=123456:telegram-bot-token
CHANNEL_ID=-1001234567890
```

После этого запустите **YT Harvester** из раздела Internet/Интернет или командой:

```bash
yt-harvester
```

### Запуск Из Исходников

```bash
sudo apt install python3 python3-pyqt5 yt-dlp curl bash coreutils findutils grep sed
cp .env.example .env
nano .env
./start_tray.sh
```

### Настройки Каналов

На каждой карточке канала есть три маленькие кнопки:

- `🎬` видео
- `📱` Shorts
- `🔴` стримы

Зелёная подложка значит “скачивать”, красная — “не скачивать”. Эти настройки хранятся отдельно от `channels.txt`, поэтому список каналов остаётся простым и чистым.

### Где Хранятся Данные

После установки `.deb` пользовательские данные лежат не в `/opt`, а здесь:

- данные: `~/.local/share/yt-harvester`
- настройки: `~/.config/yt-harvester`
- кеш: `~/.cache/yt-harvester`

При запуске прямо из папки проекта программа по умолчанию использует текущую директорию.

### Сборка Deb

```bash
packaging/build_deb.sh 0.2.0~beta1
```

Готовый пакет появится здесь:

```bash
dist/yt-harvester_0.2.0~beta1_all.deb
```

### Важно

YT Harvester использует `yt-dlp` для скачивания. Используйте программу с учётом правил YouTube, авторского права и законодательства вашей страны.
