# Screenshot Catalog

Captured on 2026-10-04 from YouTube Harvester **1.2.1**, in **dark theme**:

- Desktop: 40 PNGs, four tabs per language, 1200 x 820.
- Android: 50 PNGs, five tabs per language, 1080 x 1859.
- Languages: English, Russian, Ukrainian, Belarusian, French, Spanish, Hindi,
  Chinese, Japanese, Arabic (including right-to-left layout).

## Galleries

Each localized project README contains the desktop and Android galleries.

| Language | README | Desktop Overview | Android Overview |
| --- | --- | --- | --- |
| English | [README](../../README.md) | [PNG](en/overview.png) | [PNG](android/en/overview.png) |
| Russian | [README](../../README.ru.md) | [PNG](ru/overview.png) | [PNG](android/ru/overview.png) |
| Ukrainian | [README](../../README.uk.md) | [PNG](uk/overview.png) | [PNG](android/uk/overview.png) |
| Belarusian | [README](../../README.be.md) | [PNG](be/overview.png) | [PNG](android/be/overview.png) |
| French | [README](../../README.fr.md) | [PNG](fr/overview.png) | [PNG](android/fr/overview.png) |
| Spanish | [README](../../README.es.md) | [PNG](es/overview.png) | [PNG](android/es/overview.png) |
| Hindi | [README](../../README.hi.md) | [PNG](hi/overview.png) | [PNG](android/hi/overview.png) |
| Chinese | [README](../../README.zh.md) | [PNG](zh/overview.png) | [PNG](android/zh/overview.png) |
| Japanese | [README](../../README.ja.md) | [PNG](ja/overview.png) | [PNG](android/ja/overview.png) |
| Arabic | [README](../../README.ar.md) | [PNG](ar/overview.png) | [PNG](android/ar/overview.png) |

Reusable paths, relative to the repository root:

```text
docs/screenshots/<language>/{overview,channels,queue,settings}.png
docs/screenshots/android/<language>/{overview,channels,queue,archive,settings}.png
```

Android images use `width="260"` in the galleries; the original files retain
their full resolution. No frames, recoloring, image-generation, or graphical
retouching was applied.

## Capture Provenance

Desktop screenshots render the actual PyQt interface offscreen on Linux. This
interface is shared with Windows; these are not separate Windows OS captures.
Settings, queue, archive, status, and logs use temporary demonstration fixtures.
Existing public channel metadata is copied to a temporary cache before capture.
The working application's configuration, archive, and credentials are not changed.

Android screenshots render the actual Compose screen components in LDPlayer
(Android API 34, x86_64). A documentation-only package,
`com.liberivixer.youtubeharvester.screenshots`, keeps them separate from installed
user/tester apps. It supplies demonstration state, forces dark theme and the
selected language, and captures the Compose content without Android system bars.
Statistics and archive records are examples, not evidence of completed downloads.
Public channel names, video titles, and thumbnails remain in their original
language. The displayed version is 1.2.1 without a beta suffix; these screenshots
do not imply that the public Android release acceptance gates are closed.

[manifest.json](manifest.json) records the version, date, dimensions, and SHA-256
of all 90 PNGs. [android/capture.json](android/capture.json) records the isolated
Android package/version and the 50 device-captured PNG checksums.

## Repeat Capture

Run from the repository root. Provide a real thumbnail JPEG and its matching
oEmbed JSON (`title` and `author_name`), as well as a local public channel cache.
The current example uses `https://www.youtube.com/watch?v=tYh-7USx09E`.

```bash
QT_QPA_PLATFORM=offscreen PYNPUT_BACKEND=dummy .venv/bin/python \
  scripts/generate_readme_screenshots.py \
  --preview /path/to/video.jpg \
  --preview-metadata /path/to/video.json \
  --output /tmp/yth-capture/desktop

(cd android && ./gradlew --offline -PythTestBuildType=screenshots \
  assembleScreenshots assembleScreenshotsAndroidTest)

.venv/bin/python android/scripts/capture_readme_screenshots.py \
  --preview /path/to/video.jpg \
  --preview-metadata /path/to/video.json \
  --output /tmp/yth-capture/android
```

Gradle requires the configured Android SDK and JDK 17. For a forwarded Windows
ADB server, append `--host 127.0.0.1 --port 15037`; the device defaults to
`emulator-5554`. The capture script refuses to install the normal user package.
Review every language, dark backgrounds, thumbnails, text fitting, and Arabic
RTL before promoting the PNGs. Regenerate both manifests when replacing images.

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_readme_screenshot*.py' -v
```
