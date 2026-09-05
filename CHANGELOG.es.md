# Registro de cambios

<p align="center">
  <a href="CHANGELOG.md">🇺🇸 🇬🇧 English</a> ·
  <a href="CHANGELOG.ru.md">🇷🇺 Русский</a> ·
  <a href="CHANGELOG.uk.md">🇺🇦 Українська</a> ·
  <a href="CHANGELOG.be.md">🇧🇾 Беларуская</a> ·
  <a href="CHANGELOG.fr.md">🇫🇷 Français</a> ·
  <a href="CHANGELOG.es.md">🇪🇸 Español</a> ·
  <a href="CHANGELOG.hi.md">🇮🇳 हिन्दी</a> ·
  <a href="CHANGELOG.zh.md">🇨🇳 中文</a> ·
  <a href="CHANGELOG.ja.md">🇯🇵 日本語</a> ·
  <a href="CHANGELOG.ar.md">🇸🇦 العربية</a>
</p>

Aquí se documentan todos los cambios importantes de **YouTube Harvester**.

## Sin publicar

- Escritorio: canales Rutube con deduplicación de alias, nombres y avatares,
  búsqueda de Vídeos/Shorts, límites, programación y marcado de archivo según la fuente.
- Las comprobaciones de emisiones y contenido de pago de Rutube quedan desactivadas.
  Nuevos elementos traducidos a diez idiomas; el port de Android no cambia.
- Se conservan las líneas del archivo sin salto final; la búsqueda del canal por
  nombre en el archivo se limita al mismo servicio de vídeo.

## [1.2.0-beta] - 2026-08-29

### Añadido

- Descarga opcional de vídeos individuales de YouTube, Rutube y VK desde el
  campo URL de Resumen, Descarga rápida, el portapapeles, la cola manual y el
  archivo.
- Registros de archivo conscientes del origen, enlaces canónicos y símbolos
  monocromos `Ⓥ` y `Ⓡ` para las entradas de VK y Rutube.
- Botón de cierre junto al selector de tema y límites de 160 px para la columna
  de canal y 155 px para la columna de ID.
- Pruebas automáticas de URL compatibles, migración y compatibilidad del
  archivo, movimiento de ficheros y descarga segura de vistas previas.
- Bloqueo completo de dependencias de Windows y configuración de Dependabot.

### Cambiado

- La aplicación y las herramientas de publicación marcan esta versión como la
  versión preliminar `1.2.0-beta`; Debian usa `1.2.0~beta1` para ordenar bien.
- Se fijaron `yt-dlp 2026.08.19`, `yt-dlp-ejs 0.8.0`, Deno `2.9.6`,
  FFmpeg/FFprobe para Windows `9.0.1`, PyQt5 `5.15.11`, pynput `1.8.2`,
  PyInstaller `6.22.2` y Pillow `12.3.0`.
- Las compilaciones Windows en línea y sin conexión verifican versiones y
  sumas exactas, ejecutan `pip check` y usan un lock completo de dependencias.
- GitHub Actions queda fijado a commits revisados y la guía sin conexión se
  actualizó para las herramientas fijadas e Inno Setup 7.1.
- Los metadatos de Linux describen un descargador de vídeos con cola manual de
  YouTube, Rutube y VK.
- Las nuevas etiquetas de URL y origen del archivo están traducidas a todos
  los idiomas de la interfaz.

### Corregido

- La comparación de actualizaciones ordena correctamente alpha, beta, release
  candidate y estable, sin degradar una beta a una versión estable antigua.
- Cola, duplicados, variantes de calidad y pistas, borrado, informes y migración
  usan «origen + ID», evitando colisiones entre servicios.
- Las entradas antiguas siguen siendo compatibles como YouTube; la migración
  no adivina ID ambiguos y elimina la marca de origen del nombre final.
- Los métodos alternativos de metadatos y HTTP 403 de YouTube ya no se aplican
  a Rutube o VK; la falta del flujo de salida de `yt-dlp` se gestiona sin fallo.
- Las funciones de canal capturan el canal y tipo actuales; la salida de los
  comandos de configuración se decodifica explícitamente como UTF-8.
- La compilación Windows ignora FFmpeg o Deno incompatibles de `PATH` y descarga
  en línea la versión fijada y verificada.

### Seguridad

- Las vistas previas se descargan atómicamente solo por HTTP(S), sin
  credenciales en la URL, con validación de redirecciones, tiempo límite,
  máximo de 12 MiB y limpieza de ficheros incompletos.
- Los paquetes FFmpeg y Deno se verifican con SHA-256, que también sustituye a
  SHA-1 en los resúmenes de variantes y nombres.
- El archivo de fuentes incluye locks, pruebas y nuevos ficheros necesarios
  incluso si se genera antes de un commit.

## [1.1.3] - 2026-08-20

### Añadido

- Un actualizador integrado descarga el instalador, archivo portátil, paquete
  Linux o fuentes correspondientes desde las versiones oficiales de GitHub.
- Las descargas pueden reanudarse y se verifican con la suma SHA-256 publicada
  y el resumen del recurso de GitHub antes de abrirse.
- Interfaz, reglas, README, historial, metadatos de escritorio y capturas
  totalmente localizados al bielorruso.
- Acciones seguras de integración de instancia única y notificaciones del
  sistema para integraciones de escritorio como FriendsHub.

### Cambiado

- El `yt-dlp` incluido se actualizó a `2026.08.19`; también se actualizaron las
  dependencias de Windows y GitHub Actions.
- El actualizador de `yt-dlp` instala atómicamente un ejecutable verificado
  desde Configuración.
- Tras un HTTP 403 se renueva la URL multimedia de YouTube y se reintenta con
  un cliente alternativo antes de mostrar el error final.

### Corregido

- Los modos bandeja, barra de tareas y combinado se aplican de forma coherente
  a las ventanas principal y de Descarga rápida.
- El registro del archivo se confirma solo cuando el fichero terminado llega a
  su destino final.
- Los bloqueos, solicitudes de inicio y eventos usan ubicaciones privadas por
  usuario y rechazan archivos inseguros en Linux.

## [1.1.2] - 2026-08-01

### Añadido

- La Descarga rápida permite seleccionar e integrar en un solo MP4 varias
  pistas de audio y varias pistas de subtítulos manuales o automáticas.
- Interfaz completa, reglas de uso, README, registro de cambios y capturas de
  pantalla en japonés.
- Los menús de audio y subtítulos priorizan las pistas originales o manuales,
  seguidas de ruso, inglés, ucraniano y los demás idiomas de la interfaz; el
  resto aparece por orden alfabético en un grupo separado.

### Cambiado

- El archivo considera cada combinación de resolución, pistas de audio y
  subtítulos como una variante distinta del mismo vídeo.
- La columna de calidad muestra solo la resolución; su ayuda emergente enumera
  las pistas de audio y subtítulos una por línea.
- Las pistas de audio del MP4 combinado reciben metadatos de idioma ISO 639.
- El selector de subtítulos usa el icono `🔤`, compatible con la fuente.
- Los subtítulos manuales/originales y automáticos aparecen separados
  visualmente en el menú de pistas.

### Corregido

- La Descarga rápida usa un cliente adicional de metadatos de YouTube para
  encontrar doblajes alternativos omitidos por el cliente predeterminado.
- Si falla un subtítulo, incluso por HTTP 429, `yt-dlp` reintenta sin esa pista;
  si fallan todos, el vídeo y el audio se descargan igualmente.
- En Windows se retrasa el guardado de la posición para que la ventana de
  Descarga rápida no dé tirones al arrastrarla.
- Se corrigió la comparación entre variantes con varias pistas y registros
  antiguos; los nombres compatibles con Windows conservan una longitud segura.
- La acción Detener de la bandeja usa el icono `🛑`, que se muestra claramente
  en todos los idiomas.

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
