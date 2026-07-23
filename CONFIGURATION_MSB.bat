@echo off
rem Configuration MySelfieBooth personnalisee pour le poste de Stephane.

set "MSB_MONTAGE_ROOT=P:\Montage-EVENT\ALL_MONTAGE"

rem Taille conseillée pour un catalogue d'environ 1000 vidéos.
set "MSB_MAX_VIDEOS=100"

rem Une session s'arrête proprement après 4 heures et reprend au prochain lancement.
set "MSB_MAX_RUNTIME_MINUTES=240"

rem Profil optimise pour environ 1000 videos sur le NAS.
set "MSB_SPEED_PROFILE=fast"
set "MSB_PROBE_WORKERS=6"

rem Ne pas exclure FINAL ou EXPORTS : ils peuvent contenir des montages utiles.
set "MSB_EXCLUDE_FOLDERS=cache;.cache;temp;tmp;proxy;proxies;preview;previews;miniatures;thumbnails;resultats;after_effects;autosave;auto-save"
