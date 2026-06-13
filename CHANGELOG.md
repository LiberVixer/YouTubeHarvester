# Changelog

All notable changes to **YT Harvester** are documented here.

## [0.2.0-beta.1] - 2026-06-12

First public beta release.

### English

#### Added

- New overview tab with live downloader status, counters, current channel artwork, and current video thumbnail.
- Channel grid with cached channel images.
- Per-channel toggles for videos, Shorts, and streams.
- Manual YouTube video queue with URL preview and fallback queueing when metadata cannot be read.
- Combined horizontal queue and scheduler tab with dedicated artwork.
- Settings tab with download folder, temp folder, media limits, max resolution, log retention, autostart, temp cleanup, and queue retry options.
- Telegram settings block with masked `BOT_TOKEN`, `CHANNEL_ID`, and `PROXY_URL` fields plus eye buttons.
- Dark, light, and system theme modes.
- Linux `.deb` packaging for Linux Mint and Ubuntu-like systems.
- GitHub README screenshots and bilingual documentation.

#### Changed

- Default download folder is now `~/Downloads/YouTubeHarvester`.
- Default temp folder is now `~/temp/YTH`.
- Logs are now shown in the lower part of the Settings tab.
- `yt-dlp` quality selection is configurable while keeping `1080p` as the default.
- Telegram can be disabled, allowing local-only downloads without bot credentials.

#### Fixed

- More reliable tray double-click window opening.
- Cleaner log positioning and refresh behavior.
- Better emoji rendering in PyQt labels and buttons.
- Safer temp cleanup behavior when processing errors occur.

### Русский

#### Добавлено

- Новая вкладка обзора со статусом скачивания, счётчиками, картинкой текущего канала и заставкой текущего видео.
- Сетка каналов с кешированными картинками.
- Для каждого канала отдельные переключатели видео, Shorts и стримов.
- Ручная очередь YouTube-видео с предпросмотром ссылки и возможностью добавить ссылку даже без метаданных.
- Объединённая горизонтальная вкладка очереди и планировщика с отдельной иллюстрацией.
- Вкладка настроек: папка загрузки, временная папка, лимиты типов, максимальное разрешение, хранение логов, автозапуск, очистка TEMP и повтор очереди.
- Telegram-блок с маскированными полями `BOT_TOKEN`, `CHANNEL_ID`, `PROXY_URL` и кнопками-глазами.
- Ночной, дневной и системный режимы темы.
- Сборка `.deb` для Linux Mint и Ubuntu-подобных систем.
- Скриншоты и двуязычный README для GitHub.

#### Изменено

- Папка загрузки по умолчанию: `~/Downloads/YouTubeHarvester`.
- Временная папка по умолчанию: `~/temp/YTH`.
- Логи теперь находятся в нижней части вкладки настроек.
- Выбор качества `yt-dlp` теперь настраивается, при этом `1080p` остаётся значением по умолчанию.
- Telegram можно отключить и скачивать локально без токена бота.

#### Исправлено

- Более надёжное открытие окна по двойному клику на иконке в трее.
- Более аккуратное отображение и обновление логов.
- Улучшено отображение emoji в PyQt-интерфейсе.
- Более безопасная очистка временной папки при ошибках обработки.

## [0.1.0] - 2026-06-11

### English

- Initial packaged build.
- Tray launcher for the downloader script.
- Channel list, scheduled runs, manual queue, logs, and Telegram delivery.

### Русский

- Первая пакетная сборка.
- Трей-лаунчер для скрипта скачивания.
- Список каналов, запуск по расписанию, ручная очередь, логи и отправка в Telegram.
