# Changelog

All notable changes to **YouTube Harvester** are documented here.

## [0.2.3-beta] - 2026-06-18

### English

#### Changed

- The upper overview progress bar keeps showing checked channels while a video is downloading.
- Shorts now use a clear lightning icon throughout the interface and downloader messages.

### Русский

#### Изменено

- Верхний прогресс-бар продолжает показывать проверенные каналы во время скачивания видео.
- Для Shorts во всём интерфейсе и сообщениях движков используется понятная иконка молнии.

## [0.2.2-beta] - 2026-06-13

### English

#### Added

- First-run responsible-use dialog with required acknowledgement checkboxes.
- Settings button for reopening the usage rules and third-party component notice.
- Download engine selector with stable Bash mode and experimental Python mode.
- Experimental `scripts/downloader.py` engine for portability testing.
- Windows launch preparation through `start_tray_windows.bat`, platform-specific user-data paths, Current User registry autostart, and Windows system theme detection.
- Windows EXE build script based on PyInstaller.
- `requirements.txt` for source launches on Windows and other pip-based environments.
- Release packaging scripts and GitHub Actions for `.deb`, Windows installer `.exe`, Windows `.msi`, portable `.zip`, and source `.tar.gz` artifacts.

#### Changed

- Settings media limits are back on one compact line.
- Overview event list now has more vertical space, and idle download status says that the app is waiting for a download.
- Overview search status now shows checked channels as a progress bar.
- Download progress now names the active stage: video, audio, merging, or post-processing.
- The idle overview no longer shows an empty download progress section.
- Channel scanning pauses for one second after each checked Videos, Shorts, and Streams section.
- The idle event panel now shows a clean emoji summary of the latest download run.
- Linux desktop launcher metadata now uses the final app name and localized labels.
- README now includes expanded responsible-use and third-party component notes.
- Windows runs the Python downloader engine only; Bash remains a Linux option.

#### Fixed

- Manual queue now refuses videos already present in the archive.
- Downloader skips already archived queued videos and avoids duplicate detailed archive entries.
- Windows Python downloader no longer crashes when the system console encoding cannot represent emoji.

### Русский

#### Добавлено

- Диалог правил ответственного использования при первом запуске с обязательными галочками подтверждения.
- Кнопка в настройках для повторного открытия правил и сведений о внешних компонентах.
- Выбор движка скачивания: стабильный Bash и экспериментальный Python.
- Экспериментальный движок `scripts/downloader.py` для проверки переносимости.
- Подготовка запуска на Windows: `start_tray_windows.bat`, платформенные пользовательские папки, автозапуск через реестр Current User и определение системной темы Windows.
- Скрипт сборки Windows EXE на базе PyInstaller.
- `requirements.txt` для запуска из исходников на Windows и в других pip-окружениях.
- Скрипты упаковки релиза и GitHub Actions для `.deb`, Windows installer `.exe`, Windows `.msi`, portable `.zip` и исходного `.tar.gz`.

#### Изменено

- Лимиты типов во вкладке настроек снова отображаются в одну компактную строку.
- На главном экране блок событий стал выше, а простой блока скачивания показывает ожидание скачивания.
- Во время поиска верхняя плашка показывает прогресс проверенных каналов.
- При скачивании блок прогресса показывает текущий этап: видео, аудио, объединение или обработка.
- В простое пустой блок прогресса скачивания больше не отображается.
- После проверки каждого включённого раздела Видео, Shorts и Трансляции выдерживается пауза в одну секунду.
- В простое панель событий показывает чистый отчёт с эмодзи о последнем запуске скачивания.
- Метаданные ярлыка Linux приведены к финальному названию программы и русским подписям.
- README расширен правилами ответственного использования и сведениями о внешних компонентах.
- На Windows используется только Python-движок; Bash остаётся вариантом для Linux.

#### Исправлено

- Ручная очередь больше не принимает видео, которое уже есть в архиве.
- Скрипт скачивания пропускает уже архивные ссылки из очереди и не создаёт дубли в подробном архиве.
- Python-движок на Windows больше не падает, если системная кодировка консоли не поддерживает emoji.

## [0.2.0-beta.1] - 2026-06-12

First public beta release.

### English

#### Added

- New overview tab with live downloader status, counters, current channel artwork, and current video thumbnail.
- Channel grid with cached channel images.
- Per-channel toggles for videos, Shorts, and live broadcasts.
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
- Для каждого канала отдельные переключатели Видео, Shorts и Трансляция.
- Ручная очередь YouTube-видео с предпросмотром ссылки и возможностью добавить ссылку даже без метаданных.
- Объединённая горизонтальная вкладка очереди и планировщика с отдельной иллюстрацией.
- Вкладка настроек: папка загрузки, временная папка, лимиты типов, максимальное разрешение, хранение логов, автозапуск, очистка временной папки и повтор очереди.
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
