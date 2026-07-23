# MySelfieBooth Video AI + After Effects

Analyse localement les vidéos d'un NAS, détecte les meilleurs moments, identifie les machines MySelfieBooth et génère automatiquement un projet After Effects organisé.

## Fonctions principales

| Étape | Fonction |
|---|---|
| Préfiltrage | Changements de scène, mouvement et pics sonores avec FFmpeg |
| Vision IA | Sourires, réactions, émotion, énergie et qualité avec Ollama Vision |
| Machines | Photobooth, VogueBooth, 360Booth et MiroirBooth avec photos de référence |
| Historique | Index SQLite, reprise automatique et recherche |
| Montage | Styles équilibré, dynamique, émotion et publicité |
| After Effects | Imports, compositions, découpes, marqueurs, recadrage et file de rendu |
| Finition | Transitions, mouvement subtil, mixage audio et composition de validation |
| V3.2 | Dédoublonnage visuel, arc narratif, textes IA, proxies NAS et contrôle qualité |
| V3.3 | Lots intelligents, tableau de bord, projet global et contrôle de production |
| V3.4 | Préfiltrage en une passe, planches IA compactes et arrêt anticipé |

## Nouveautés V3.4 — analyses plus rapides

Le profil `fast`, activé par défaut pour `P:\Montage-EVENT\ALL_MONTAGE`, réduit fortement le travail inutile avant et pendant Ollama.

| Optimisation | Effet |
|---|---|
| Une seule lecture FFmpeg | Scènes, mouvement et son sont calculés dans le même processus |
| Préfiltre basse résolution | L'analyse technique travaille en 256 px de large en mode rapide |
| FFprobe parallèle | Jusqu'à six métadonnées vidéo sont lues en parallèle |
| Planche de trois instants | Un seul JPEG est envoyé à Ollama au lieu de trois images séparées |
| Références compactées | Les quatre machines sont réunies dans une planche 2x2 |
| Références ciblées | La planche des machines est envoyée seulement aux meilleurs candidats |
| Budget IA adaptatif | 12 candidats maximum par vidéo en mode rapide, contre 45 en qualité |
| Arrêt anticipé | L'analyse s'arrête dès que cinq moments suffisamment forts sont trouvés |
| Filtre faible signal | Une vidéo sans scène, mouvement ou pic sonore significatif évite Ollama |
| Cache images et SQLite | Les références et analyses déjà calculées sont réutilisées |
| Export clips facultatif | Aucun transcodage MP4 n'est fait par défaut avant After Effects |

### Profils disponibles

```text
fast       catalogue de 1 000 vidéos, meilleur rapport vitesse/résultat
balanced   événement important, analyse plus détaillée
quality    analyse exhaustive, plus lente
custom     conserve tous les réglages passés manuellement
```

Commande recommandée pour le catalogue :

```powershell
python nas_video_ai_analyzer.py "P:\Montage-EVENT\ALL_MONTAGE" ^
  --output resultats ^
  --speed-profile fast ^
  --probe-workers 6 ^
  --max-videos 100 ^
  --priority unprocessed
```

Le lanceur `LANCER_PIPELINE_COMPLET.bat` demande maintenant le profil de vitesse. L'export des passages MP4 est désactivé par défaut, car After Effects peut découper directement les fichiers originaux avec les timecodes SQLite.

### Mesurer la vitesse sur cinq vidéos

Double-cliquer sur `TESTER_VITESSE.bat`. Le test choisit cinq vidéos courtes non traitées, utilise le profil rapide et génère le tableau de bord sans exporter de clips.

## Nouveautés V3.3 pour les 1 000 vidéos

La V3.3 est conçue pour traiter `P:\Montage-EVENT\ALL_MONTAGE` progressivement sans recommencer le catalogue.

| Outil | Utilisation |
|---|---|
| `INDEXER_CATALOGUE.bat` | Inventorie toutes les vidéos sans lancer Ollama |
| `LANCER_PIPELINE_COMPLET.bat` | Analyse un lot puis prépare After Effects |
| `LANCER_LOT_NUIT.bat` | Analyse jusqu'à 150 vidéos pendant huit heures maximum |
| `OUVRIR_TABLEAU_DE_BORD.bat` | Régénère et ouvre l'avancement du catalogue |
| `GENERER_PROJET_GLOBAL.bat` | Réunit les meilleurs moments de tous les lots |

À partir de la deuxième indexation, les durées et la présence d'audio sont relues depuis SQLite lorsque les fichiers n'ont pas changé. Cela évite de relancer FFprobe sur les 1 000 vidéos à chaque session.

Le tableau de bord est créé dans :

```text
resultats/catalogue_dashboard.html
resultats/catalogue_dashboard.json
resultats/catalogue_videos.csv
```

Il indique le nombre de vidéos indexées, terminées ou en erreur, la durée totale, les meilleurs moments, les machines détectées et l'espace disque disponible.

### Priorités de traitement

```text
--priority unprocessed   vidéos jamais terminées en premier
--priority errors        uniquement les vidéos en erreur
--priority newest        fichiers les plus récents
--priority shortest      vidéos les plus rapides à traiter
--priority score         meilleur score technique du premier scanner
```

### Sessions à durée limitée

```powershell
python nas_video_ai_analyzer.py "P:\Montage-EVENT\ALL_MONTAGE" ^
  --output resultats ^
  --max-videos 150 ^
  --priority unprocessed ^
  --max-runtime-minutes 480 ^
  --checkpoint-every 5
```

Le programme termine la vidéo en cours, sauvegarde SQLite et s'arrête proprement. Une relance passe aux fichiers suivants.

### Projet After Effects global

```powershell
python generate_after_effects_project.py "resultats\video_index.sqlite3" ^
  --output "resultats\after_effects_global" ^
  --all-runs ^
  --machine-review-comps ^
  --quality-gate warn
```

`--all-runs` rassemble les meilleurs moments de toutes les sessions et supprime les doublons produits par plusieurs analyses du même passage.

## Prérequis

- Windows 10 ou 11 ;
- Python 3.10 ou plus récent ;
- FFmpeg et FFprobe accessibles dans le `PATH` ;
- Ollama ;
- un modèle de vision Ollama, par exemple `gemma3` ;
- Adobe After Effects.

Aucune bibliothèque Python externe n'est nécessaire.

```powershell
ollama pull gemma3
ffmpeg -version
ffprobe -version
python --version
```

Ajoute ensuite 3 à 8 photos nettes de chaque machine :

```text
machine_references/
├── Photobooth/
├── VogueBooth/
├── 360Booth/
└── MiroirBooth/
```

## Utilisation la plus simple

Glisse un dossier NAS, une vidéo ou `videos.csv` sur :

```text
LANCER_PIPELINE_COMPLET.bat
```

Le lanceur demande :

- le nom de l'événement ;
- le style de montage ;
- la transition ;
- le type de texte automatique ;
- la création éventuelle de proxies locaux.

Le programme analyse les rushs, conserve les résultats dans SQLite, sélectionne les meilleurs passages et génère le script After Effects.

## Génération After Effects seule

```powershell
python generate_after_effects_project.py "resultats\video_index.sqlite3" ^
  --output "resultats\after_effects" ^
  --event-name "Mariage Amira et Karim" ^
  --event-date "12 septembre 2026" ^
  --style dynamic ^
  --story-arc rising ^
  --visual-dedup ^
  --caption-mode description ^
  --background-mode blur ^
  --transition-style fade ^
  --auto-motion ^
  --review-comp ^
  --save-project ^
  --queue-render
```

Pour une publicité avec logo, musique, labels et proxies :

```powershell
python generate_after_effects_project.py "resultats\video_index.sqlite3" ^
  --output "resultats\after_effects" ^
  --event-name "MySelfieBooth" ^
  --style promo ^
  --story-arc promo ^
  --logo "D:\MySelfieBooth\logo.png" ^
  --music "D:\Musiques\reel.mp3" ^
  --music-beats ^
  --transition-style flash ^
  --machine-labels ^
  --caption-mode both ^
  --proxies ^
  --mute-source-audio ^
  --save-project ^
  --queue-render
```

## Améliorations V3.2

### Dédoublonnage visuel

Le générateur extrait une petite image au centre de chaque passage et calcule une empreinte dHash. Les plans presque identiques sont pénalisés, même s'ils proviennent de fichiers différents.

```text
--visual-dedup
--dedup-threshold 8
```

Le cache `fingerprints_cache.json` évite de recalculer les empreintes lors d'une nouvelle génération.

### Arc narratif

Le montage peut être ordonné selon sa position dans la vidéo :

| Arc | Fonction |
|---|---|
| `rising` | début propre, montée progressive, climax énergique, finale positive |
| `emotion` | progression orientée regards, sourires et émotion |
| `promo` | présence des machines et efficacité publicitaire |
| `none` | classement sans structure narrative |

```text
--story-arc rising
```

### Textes automatiques

After Effects peut afficher le type de machine, la description IA ou les deux :

```text
--caption-mode none
--caption-mode machine
--caption-mode description
--caption-mode both
```

Les textes sont limités, positionnés dans une zone sûre et animés par un fondu court.

### Proxies locaux

Pour éviter de monter directement les gros rushs sur le NAS :

```text
--proxies --proxy-height 720 --proxy-crf 28
```

FFmpeg crée un proxy H.264 local par vidéo. Le JSX importe le fichier source puis lui associe automatiquement son proxy dans After Effects. Le projet reste donc relié aux rushs originaux pour le rendu final.

### Rapport de contrôle qualité

Chaque génération crée :

```text
rapport_qualite.html
rapport_qualite.json
```

Le rapport vérifie :

- les médias manquants ;
- les passages de faible qualité ;
- les plans visuellement proches ;
- la répartition des machines ;
- la dépendance excessive à un seul rush ;
- le remplissage réel de chaque composition.

## Styles de montage

| Style | Priorité |
|---|---|
| `balanced` | Mix équilibré entre émotion, énergie et machines |
| `dynamic` | Réactions, danse, mouvements et rythme |
| `emotion` | Sourires, regards, complicité et moments humains |
| `promo` | Machines visibles, utilisation réelle et qualité publicitaire |

## Compositions générées

| Composition | Format |
|---|---:|
| `REEL_VERTICAL_15S` | 1080 × 1920 |
| `REEL_VERTICAL_30S` | 1080 × 1920 |
| `REEL_VERTICAL_60S` | 1080 × 1920 |
| `INSTAGRAM_CARRE_30S` | 1080 × 1080 |
| `PAYSAGE_16X9_60S` | 1920 × 1080 |
| `SELECTS_REVIEW` | 1920 × 1080, validation des meilleurs plans |

Chaque plan comporte son point d'entrée, son point de sortie, des marqueurs détaillés, une couleur par machine et un recadrage adapté.

## Ouvrir dans After Effects

1. Active `Autoriser les scripts à écrire des fichiers et à accéder au réseau` dans les préférences `Scripts et expressions`.
2. Ouvre `Fichier > Scripts > Exécuter un fichier de script`.
3. Sélectionne `resultats\after_effects\MSB_Creer_Projet_After_Effects.jsx`.

Le panneau optionnel s'installe avec :

```text
INSTALLER_PANNEAU_AFTER_EFFECTS.bat
```

Après redémarrage :

```text
Fenêtre > MSB_AutoMontage_Panel
```

La V3.3 permet aussi d'ouvrir directement le tableau de bord du catalogue, le plan CSV, le rapport qualité, le manifeste, les proxies et les rendus depuis le panneau.

## Résultats

```text
resultats/
├── video_index.sqlite3
├── moments_forts_v2.csv
├── galerie_moments_v2.html
└── after_effects/
    ├── MSB_Creer_Projet_After_Effects.jsx
    ├── after_effects_manifest.json
    ├── plan_de_montage.csv
    ├── rapport_qualite.html
    ├── rapport_qualite.json
    ├── fingerprints_cache.json
    ├── proxies/
    ├── renders/
    └── MSB_<EVENEMENT>.aep
```

## Tests

```powershell
python -m py_compile nas_video_ai_analyzer.py
python -m py_compile generate_after_effects_project.py
python -m unittest discover -s tests -v  # 24 tests
```

## Confidentialité

Par défaut, Ollama est appelé sur `http://localhost:11434`. Les images extraites restent analysées localement et les vidéos du NAS ne sont pas téléversées vers un service externe.

## Licence

MIT — Stéphane FAURE, 2026.

## Dossier de montages configuré

Le projet est préconfiguré pour utiliser ce dossier comme source principale :

```text
P:\Montage-EVENT\ALL_MONTAGE
```

Cette valeur se trouve dans `CONFIGURATION_MSB.bat`. Lors du lancement de
`LANCER_PIPELINE_COMPLET.bat`, appuie simplement sur **Entrée** pour scanner ce
dossier, ou colle le chemin d'un sous-dossier correspondant à un événement précis.

Le lanceur propose aussi un nombre maximal de vidéos :

- `100` : traitement progressif recommandé pour commencer ;
- `0` : analyse de toutes les vidéos ;
- toute autre valeur : limite personnalisée.

La base SQLite conserve les résultats, donc les exécutions suivantes reprennent le
travail sans refaire les analyses IA déjà enregistrées. Les dossiers de cache,
proxies, miniatures et résultats sont ignorés. Les dossiers `FINAL` et `EXPORTS`
ne sont pas exclus afin que les anciens montages terminés puissent aussi être
réutilisés.
