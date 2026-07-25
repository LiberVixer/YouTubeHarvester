# Journal des modifications

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

Toutes les modifications importantes de **YouTube Harvester** sont listées ici.

## [1.1.1] - 2026-07-25

### Corrections

- Chaque vidéo terminée est désormais déplacée du dossier temporaire vers le
  dossier de téléchargement avant le démarrage de l'élément suivant.
- Un arrêt progressif conserve et déplace la vidéo déjà terminée.
- L'image de la chaîne active reste visible pendant le téléchargement, même
  après le déverrouillage du logo de victoire du jeu caché.
- De petits défauts d'interface et de fonctionnement ont été corrigés.

## [1.1.0] - 2026-07-25

### Ajouté

- Interface entièrement localisée en anglais, russe, ukrainien, français,
  espagnol, hindi, chinois et arabe ; l'anglais est choisi par défaut pour les
  nouvelles installations.
- README, journaux des modifications et captures d'écran propres à chaque
  langue.
- Diagnostic du système, X11/Wayland, zone de notification, raccourci,
  presse-papiers, outils, chemins, cache, droits d'écriture et espace libre.
- Vérification des versions actuelle et récente de `yt-dlp`.
- État du contenu payant par chaîne et recherche members-only facultative lors
  d'un contrôle explicite.
- Rapport quotidien séparant vidéos, Shorts, directs et éléments de la file.
- Filtres Tout, Important et Erreurs pour les journaux.
- Téléchargement immédiat et accès rapide depuis l'onglet Aperçu.
- Générateur reproductible de captures localisées utilisant les images de
  chaînes en cache.

### Modifié

- Version de l'application et des scripts de construction portée à `1.1.0`.
- File traitée avant les chaînes puis une seconde fois après leur contrôle.
- Les éléments members-only sont une information d'accès importante et non une
  erreur rouge.
- Le contrôle des chaînes indique et anime la section active et peut être arrêté
  par le même bouton.
- Espacements, contraste des cases, contrôles de chaînes, limites, barre Aperçu
  et fenêtre rapide affinés.
- Linux n'affiche plus que le moteur Python ; Bash reste du code historique
  désactivé.
- Un `YTD_CONFIG_DIR` explicite contient désormais tous les paramètres et isole
  les instances portables ou de test.

### Corrigé

- UTF-8 fiable pour le cyrillique et les emoji dans la console, les journaux,
  l'archive et les sous-processus Windows.
- Un fichier local réussi n'est plus supprimé après une erreur Telegram ou de
  post-traitement.
- Le nettoyage Linux/X11 ignore le marqueur `.yth-temp` et supprime prudemment
  les fichiers terminés.
- L'Aperçu remet l'image d'attente après un téléchargement manuel et ne montre
  plus l'ancienne chaîne au démarrage.
- Le presse-papiers ne rouvre plus la même fenêtre après le début du
  téléchargement.
- La fenêtre rapide conserve sa position, charge mieux l'image de chaîne,
  contient correctement la miniature et utilise une surbrillance ronde.

## [1.0.0] - 2026-07-02

### Ajouté

- Première version stable Linux et Windows.
- Aperçu, chaînes, file, planificateur, archive, journaux, téléchargement rapide,
  presse-papiers, raccourcis, Telegram, thèmes et modes de lancement.
- `.deb`, sources, Setup EXE, MSI, ZIP portable et sommes SHA256.
- `yt-dlp`, FFmpeg/FFprobe et Deno intégrés aux versions Windows.
- Règles d'utilisation responsable et notice des composants externes.

### Modifié

- Python est devenu le moteur commun à Linux et Windows.
- Les fonctions partagées ont été placées dans `yth_common.py` et tous les
  paquets.
- Une demande rapide est transmise à l'instance existante sans processus en
  double.

### Corrigé

- Les erreurs Telegram ne bloquent ni ne suppriment le média local.
- Les codes de sortie signalent correctement les éléments en échec.
- Le nettoyage temporaire valide le marqueur et le chemin.
- Les helpers PyInstaller importent les modules du projet.

## [0.2.5-beta] - 2026-06-28

- Ajout de la fenêtre rapide avec presse-papiers, métadonnées, résolution, file
  et Telegram.
- Ajout du raccourci natif Windows, de `pynput` sous X11 et du raccourci système
  Wayland.
- Passage de Linux au moteur Python, interface plus compacte et aperçus plus
  fiables.

## [0.2.4-beta] - 2026-06-25

- Intégration de `ffmpeg.exe`, `ffprobe.exe` et `deno.exe` sous Windows.
- Correction de l'UTF-8, des chemins avec espaces, des noms Windows et du
  nettoyage temporaire après échec.

## [0.2.3-beta] - 2026-06-18

- La progression conserve le nombre de chaînes vérifiées pendant un
  téléchargement.
- Shorts utilise désormais une icône éclair claire.

## [0.2.2-beta] - 2026-06-13

- Ajout des règles, paramètres, moteur Python expérimental, préparation Windows,
  paquets et GitHub Actions.
- Limites compactes, progression, étapes, pauses après sections et rapport au
  repos.
- Correction des doublons file/archive et des emoji Windows.

## [0.2.0-beta.1] - 2026-06-12

- Première bêta publique avec Aperçu, images de chaînes, file, planificateur,
  paramètres, Telegram, thèmes, journaux et `.deb` Linux.
- Correction de la zone de notification, des journaux, des emoji et du nettoyage
  temporaire.

## [0.1.0] - 2026-06-11

- Première version empaquetée avec zone de notification, chaînes, planification,
  file, journaux et Telegram.
