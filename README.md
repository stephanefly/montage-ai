# Montage AI

Montage AI parcourt les vidéos événementielles, détecte les passages intéressants, analyse les sourires et réactions avec Ollama Vision, reconnaît les machines MySelfieBooth, conserve la progression dans SQLite et prépare un projet After Effects.

Les vidéos originales ne sont jamais modifiées, déplacées ou supprimées.

## Fonctions principales

- indexation progressive des vidéos du NAS dans SQLite ;
- reprise sans rescanner tout le NAS avec `--skip-index` ;
- détection des changements de scène avec FFmpeg ;
- extraction de cinq images par passage, regroupées en grille haute résolution ;
- analyse des sourires, réactions, énergie et qualité ;
- reconnaissance indépendante Photobooth, VogueBooth, 360Booth et MiroirBooth ;
- cache SQLite des analyses pour accélérer les relances identiques ;
- invalidation automatique des anciens résultats après un changement de modèle ou de pipeline ;
- classement automatique par score ;
- génération d'un Top 10 Photobooth ;
- export CSV avec timecodes ;
- génération d'un script JSX pour After Effects ;
- conservation de la progression après une interruption.

## Installation

Installe une seule fois :

1. Python 3 ;
2. FFmpeg ;
3. Ollama ;
4. un compte Ollama gratuit pour le mode cloud, ou le modèle local `gemma3`.

### Installer FFmpeg sous Windows

```powershell
winget install -e --id Gyan.FFmpeg
```

Ferme puis relance PyCharm ou PowerShell après l'installation.

Vérifie ensuite :

```powershell
ffmpeg -version
ffprobe -version
```

### Préparer Ollama Cloud Free — recommandé

```powershell
ollama signin
ollama pull qwen3-vl:235b-cloud
```

Le navigateur s'ouvre pour connecter le compte Ollama. Le modèle reste exécuté
dans le cloud : seules les grilles JPEG extraites sont envoyées, jamais les
vidéos originales. Le mode cloud est sélectionné par défaut dans l'IHM.

### Installer le modèle Ollama local — solution de secours

```powershell
ollama pull gemma3
```

Vérifie les modèles installés :

```powershell
ollama list
```

## Photos de référence des machines

Ajoute au moins une photo claire de chaque machine dans les dossiers suivants :

```text
machine_references/Photobooth
machine_references/VogueBooth
machine_references/360Booth
machine_references/MiroirBooth
```

Ces images rendent la reconnaissance des machines plus fiable.

## Test rapide sur 5 vidéos

Double-clique sur :

```text
TESTER_5_VIDEOS.bat
```

Ou lance directement :

```powershell
python main.py --max-index 5 --max-videos 5 --candidates 3 --top-moments 2
```

Cette commande :

1. indexe seulement 5 fichiers ;
2. analyse au maximum 5 vidéos ;
3. teste 3 passages par vidéo ;
4. conserve 2 passages maximum par vidéo.

## Interface graphique Windows

Double-clique sur :

```text
LANCER_IHM.bat
```

L'interface permet de choisir les dossiers, régler le nombre de vidéos et de
candidats, relancer les vidéos en erreur, démarrer ou arrêter l'analyse et
suivre les messages du programme en direct. Elle utilise uniquement Tkinter,
fourni avec l'installation standard de Python.

Une aide intégrée explique chaque réglage. Trois préréglages sont disponibles :
`Rapide`, `Équilibré` et `Qualité`. Le mode Équilibré est recommandé pour une
première analyse.

## Analyser 5 vidéos déjà indexées

Cette commande ne rescane pas le NAS :

```powershell
python main.py --skip-index --max-videos 5
```

C'est la commande recommandée pour tester l'analyse après avoir interrompu une longue indexation.

## Indexer sans analyser

Pour indexer toutes les vidéos puis s'arrêter :

```powershell
python main.py --index-only
```

Pour indexer par petits lots de 500 fichiers :

```powershell
python main.py --index-only --max-index 500
```

Relance la commande plusieurs fois. Les vidéos inchangées déjà connues ne sont plus analysées avec FFprobe, ce qui accélère les passages suivants.

## Analyser un lot depuis SQLite

```powershell
python main.py --skip-index --max-videos 50
```

Pour analyser toutes les vidéos encore en attente :

```powershell
python main.py --skip-index --max-videos 0
```

## Réessayer les vidéos en erreur

```powershell
python main.py --skip-index --max-videos 20 --retry-errors
```

Si Ollama renvoie une réponse vide ou des jetons `<unused...>`, arrête le lot,
ferme puis relance Ollama. Le programme déclenche automatiquement un
coupe-circuit afin de ne pas classer les vidéos suivantes en erreur.

## Réanalyser des vidéos déjà terminées

```powershell
python main.py --skip-index --max-videos 10 --reanalyze
```

## Générer uniquement les exports

```powershell
python main.py --export-only
```

Cette commande relit SQLite et recrée les CSV et le script After Effects sans utiliser FFmpeg ni Ollama.

## Obtenir un Top 10 par machine

Top 10 Photobooth :

```powershell
python main.py --export-only --top-machine Photobooth --top-limit 10
```

Top 20 VogueBooth :

```powershell
python main.py --export-only --top-machine VogueBooth --top-limit 20
```

## Fichiers générés

```text
resultats/video_index.sqlite3
resultats/moments.csv
resultats/top_10_photobooth.csv
resultats/MSB_Creer_Projet_After_Effects.jsx
```

| Fichier | Utilité |
|---|---|
| `video_index.sqlite3` | Base de progression et résultats d'analyse |
| `moments.csv` | Tous les passages classés par score |
| `top_10_photobooth.csv` | Les meilleurs passages Photobooth |
| `MSB_Creer_Projet_After_Effects.jsx` | Création automatique des compositions After Effects |

## Utilisation dans After Effects

Dans After Effects :

```text
Fichier > Scripts > Exécuter un fichier de script
```

Sélectionne :

```text
resultats/MSB_Creer_Projet_After_Effects.jsx
```

Le script crée :

- une composition verticale de 30 secondes ;
- une composition `SELECTS_REVIEW` pour visionner les passages retenus ;
- des marqueurs indiquant le score, la machine et la description.

## Arrêter proprement

Pendant l'indexation ou l'analyse :

```text
Ctrl + C
```

La progression déjà enregistrée dans SQLite est conservée.

Relance ensuite l'analyse sans indexation :

```powershell
python main.py --skip-index --max-videos 5
```

## Commande d'aide

```powershell
python main.py --help
```
