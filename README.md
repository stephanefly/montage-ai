# Montage AI

Projet Python simple pour analyser les vidéos de :

```text
P:\Montage-EVENT\ALL_MONTAGE
```

Il détecte des passages intéressants, analyse les sourires et réactions avec Ollama, reconnaît les machines MySelfieBooth, mémorise la progression dans SQLite et génère un script After Effects.

## Installation

Installe une seule fois :

1. Python 3 ;
2. FFmpeg ;
3. Ollama ;
4. le modèle de vision :

```powershell
ollama pull gemma3
```

Ajoute éventuellement une photo de référence dans chacun de ces dossiers :

```text
machine_references/Photobooth
machine_references/VogueBooth
machine_references/360Booth
machine_references/MiroirBooth
```

## Utilisation

Double-clique sur :

```text
LANCER.bat
```

Choisis 50 ou 100 vidéos par lot. Une nouvelle exécution reprend automatiquement les vidéos non terminées grâce à SQLite.

À la fin, dans After Effects :

```text
Fichier > Scripts > Exécuter un fichier de script
```

Ouvre :

```text
resultats/MSB_Creer_Projet_After_Effects.jsx
```

Les vidéos originales ne sont jamais modifiées, déplacées ou supprimées.
