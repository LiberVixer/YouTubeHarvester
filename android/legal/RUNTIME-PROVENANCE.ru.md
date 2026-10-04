# Происхождение Встроенного Runtime

Проверка 2026-10-03 относится к приватным dev32 APK. Полного соответствующего
исходного комплекта пока нет. Баннер и SHA-256 бинарника помогают поиску,
но не доказывают набор патчей или воспроизводимость.

## Инвентаризация

`scripts/runtime_inventory.py` читает `lib/` и вложенные архивы из APK без
исполнения на Linux. Сохраняет пути, размеры, SHA-256 и ELF NEEDED через
`readelf`; ограничивает глубину/распакованный размер и отвергает дубли ZIP-имён.
Явно записывает `correspondingSourcesVerified=false`. Отчёт:
`build/qa-dev32/release-runtime-inventory-20261003.json`.
DEX/ресурсы не охвачены; yt-dlp отдельно закреплён в `runtime.properties`.

| ABI | Файлы/архивы | ELF, включая Python extensions |
| --- | ---: | ---: |
| arm64-v8a | 1128 | 258 |
| armeabi-v7a | 1128 | 258 |
| x86 | 1130 | 260 |
| x86_64 | 1130 | 260 |

Это файлы, не число проектов. 16-КБ проверка применяется к 64-битным ABI.
В runtime нет METADATA/PKG-INFO Python-пакетов; это не означает отсутствие пакетов.

## Наблюдаемые Версии

Баннеры прочитаны из работающего x86_64 debug-runtime; на другие ABI эти
версии автоматически не переносятся. Свидетельства в `build/qa-dev32/`:
`release-runtime-versions-20261003.txt`, `release-runtime-ffmpeg-version-20261003.txt`.

| Компонент | Наблюдение |
| --- | --- |
| Python | 3.12.11, clang 19.0.1, сборка 2025-08-27 |
| FFmpeg | 7.1.1, `--enable-gpl --enable-version3` |
| QuickJS | 2025-04-26 |
| OpenSSL, используемый Python ssl | 3.5.2 |
| PyCryptodome, пространство имён Cryptodome | 3.23.0 |
| WebP / SharpYUV replacement bundle | 1.6.0; исходники и rebuild script уже в проекте |

QuickJS `--help` показывает баннер и завершает справку кодом 1, не ошибкой
приложения. Импорт `Crypto` не найден; `Cryptodome` подтвердил версию 3.23.0.
Сеть и VPN при чтении версий не менялись.

В ELF-перечне также есть x264/x265/xvid, libaom/dav1d, SVT-AV1/rav1e,
Vorbis/Opus/Theora, GnuTLS/nettle/GMP, glib/harfbuzz/freetype, libass,
ncurses/readline, SQLite, zlib/bzip2/lzma, FFTW/rubberband, libssh/SRT,
libvpx/vmaf/vidstab, libxml2, ZeroMQ и Android compatibility libraries.
Версии в SONAME сами по себе не доказывают соответствие исходников.

## Следующие Шаги

1. Сопоставить бинарные хеши с upstream/Termux artifacts и закрепить точные
   коммиты recipes, версии и патчи для каждой библиотеки, не движущийся master.
2. Собрать исходники, лицензии и команды сборки, включая Python extensions,
   bootstrap binaries и Android compatibility libraries.
3. Проверить актуальные security advisories и применимость. Python 3.12.11 уже
   заменён новым security-выпуском на странице upstream; это повод для аудита,
   не доказательство конкретной уязвимости приложения. При необходимости
   пересобрать runtime из управляемых исходников и повторить приёмку.
4. Независимо проверить полный исходный архив и инструкции, закрепить SHA-256
   и лишь затем настраивать `ANDROID_SOURCE_BUNDLE` для упаковки.

## Первичные Источники

- [Python 3.12.11](https://www.python.org/downloads/release/python-31211/).
- [QuickJS: выпуски и MIT](https://bellard.org/quickjs/).
- [PyCryptodome 3.23.0: лицензия](https://github.com/Legrandin/pycryptodome/blob/v3.23.0/LICENSE.rst).
- [OpenSSL 3.5.2: лицензия](https://github.com/openssl/openssl/blob/openssl-3.5.2/LICENSE.txt).
- [WebP: наша сборка](../native/README.md).

Эта ведомость не является заверением о лицензионной полноте или безопасности.
