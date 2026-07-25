# Registro de cambios

<p align="center">
  <a href="CHANGELOG.md">🇺🇸 🇬🇧 English</a> ·
  <a href="CHANGELOG.ru.md">🇷🇺 Русский</a> ·
  <a href="CHANGELOG.uk.md">🇺🇦 Українська</a> ·
  <a href="CHANGELOG.fr.md">🇫🇷 Français</a> ·
  <a href="CHANGELOG.es.md">🇪🇸 Español</a> ·
  <a href="CHANGELOG.hi.md">🇮🇳 हिन्दी</a> ·
  <a href="CHANGELOG.zh.md">🇨🇳 中文</a> ·
  <a href="CHANGELOG.ar.md">🇸🇦 العربية</a>
</p>

Aquí se documentan todos los cambios importantes de **YouTube Harvester**.

## [1.1.1] - 2026-07-25

### Corregido

- Cada vídeo terminado se mueve ahora de la carpeta temporal a la carpeta de
  descargas antes de comenzar el siguiente elemento.
- Una parada suave conserva y mueve el vídeo que ya ha terminado.
- La imagen del canal activo permanece visible durante la descarga incluso
  después de desbloquear el logotipo de victoria del juego oculto.
- Se han corregido pequeños detalles de interfaz y funcionamiento.

## [1.1.0] - 2026-07-25

### Añadido

- Interfaz completamente localizada en inglés, ruso, ucraniano, francés,
  español, hindi, chino y árabe; inglés es el idioma predeterminado para nuevas
  instalaciones.
- README, registros de cambios y capturas propias para cada idioma.
- Diagnóstico del sistema, X11/Wayland, bandeja, atajo, portapapeles,
  herramientas, rutas, caché, escritura y espacio libre.
- Comprobación de la versión actual y más reciente de `yt-dlp`.
- Estado de contenido de pago por canal y búsqueda members-only opcional durante
  una comprobación explícita.
- Informe diario separado por Vídeos, Shorts, Emisiones y elementos de cola.
- Filtros Todos, Importante y Errores para los registros.
- Descarga inmediata y acceso rápido en la pestaña principal.
- Generador reproducible de capturas localizadas con imágenes de canal en caché.

### Modificado

- Aplicación y scripts de compilación actualizados a `1.1.0`.
- La cola se procesa antes de los canales y otra vez después de revisarlos.
- Members-only se muestra como información importante de acceso y no como error
  rojo.
- La comprobación indica y anima la sección activa y puede detenerse con el
  mismo botón.
- Mejoras de espaciado, contraste de casillas, controles de canal, límites,
  barra principal y ventana rápida.
- Linux solo ofrece el motor Python; Bash permanece como código heredado
  desactivado.
- Un `YTD_CONFIG_DIR` explícito contiene toda la configuración y aísla las
  instancias portables y de prueba.

### Corregido

- UTF-8 seguro para cirílico y emoji en consola, registros, archivo y procesos
  secundarios de Windows.
- Un archivo local descargado correctamente ya no se elimina por un fallo de
  Telegram o posprocesado.
- La limpieza Linux/X11 ignora `.yth-temp` y elimina con seguridad los archivos
  temporales terminados.
- La vista principal recupera la imagen de espera y no muestra el canal anterior
  al comenzar.
- El portapapeles ya no abre repetidamente la misma ventana tras iniciar una
  descarga.
- Descarga rápida conserva su posición, carga mejor la imagen del canal, ajusta
  la miniatura y usa un resaltado circular.

## [1.0.0] - 2026-07-02

### Añadido

- Primera versión estable para Linux y Windows.
- Vista general, canales, cola, programador, archivo, registros, descarga rápida,
  portapapeles, atajos, Telegram, temas y modos de inicio.
- `.deb`, fuentes, Setup EXE, MSI, ZIP portable y sumas SHA256.
- `yt-dlp`, FFmpeg/FFprobe y Deno integrados en Windows.
- Reglas de uso responsable y aviso de componentes externos.

### Modificado

- Python se convirtió en el motor común de Linux y Windows.
- Las funciones compartidas se trasladaron a `yth_common.py` y a todos los
  paquetes.
- Las peticiones rápidas se entregan a una única instancia.

### Corregido

- Los errores de Telegram no bloquean ni eliminan el archivo local.
- Los códigos de salida informan correctamente de elementos fallidos.
- La limpieza temporal valida marcador y ruta.
- Los helpers PyInstaller importan los módulos del proyecto.

## [0.2.5-beta] - 2026-06-28

- Añadida Descarga rápida con portapapeles, metadatos, resolución, cola y
  Telegram.
- Añadidos atajo nativo Windows, `pynput` para X11 y atajo del sistema Wayland.
- Linux cambió a Python, la interfaz se compactó y los previsualizadores se
  hicieron más fiables.

## [0.2.4-beta] - 2026-06-25

- Añadidos `ffmpeg.exe`, `ffprobe.exe`, `deno.exe` y publicación automatizada.
- Corregidos UTF-8, rutas con espacios, nombres seguros de Windows y limpieza
  temporal tras errores.

## [0.2.3-beta] - 2026-06-18

- El progreso sigue mostrando canales comprobados durante una descarga.
- Shorts utiliza un icono de rayo claro.

## [0.2.2-beta] - 2026-06-13

- Añadidas reglas, configuración, motor Python experimental, preparación de
  Windows, paquetes y GitHub Actions.
- Límites compactos, progreso, etapas, pausas tras secciones e informe en reposo.
- Corregidos duplicados de cola/archivo y emoji de Windows.

## [0.2.0-beta.1] - 2026-06-12

- Primera beta pública con vista general, imágenes de canales, cola,
  programador, configuración, Telegram, temas, registros y `.deb` Linux.
- Corregidos bandeja, actualización de registros, emoji y limpieza temporal.

## [0.1.0] - 2026-06-11

- Primera compilación empaquetada con bandeja, canales, programación, cola,
  registros y Telegram.
