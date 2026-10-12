# Ingénieur LMU

Ingénieur de course vocal **100 % français et hors ligne** pour Le Mans Ultimate,
dans l'esprit de CrewChief. Il lit la mémoire partagée native du jeu (`LMU_Data`)
20 fois par seconde et annonce à la radio ce qui compte en course.

## Lancer

1. Télécharger `Ingenieur LMU.exe` (artefact *Ingenieur-LMU-exe* du workflow GitHub Actions).
2. Le lancer **avant ou pendant** Le Mans Ultimate, puis monter en piste.
3. Pour écouter sans le jeu : choisir **Démo (course simulée)** puis **▶ Démarrer**
   (course de 8 tours d'environ 6 minutes avec toutes les annonces).

Aucun réglage du jeu n'est nécessaire : la mémoire partagée est activée par défaut dans LMU.

## Ce qu'il annonce

| Thème | Annonces |
|---|---|
| Spotter | voiture à gauche / à droite, trois de front, dégagé, toujours là (coupe la parole aux autres messages) |
| Course | tour de formation, feux, « feu vert », position gagnée / perdue, encore 10 / 5 / 2 tours, plus que 30…1 minutes, dernier tour, drapeau à damier et résultat, pluie |
| Écarts | voiture devant / derrière, « tu reprends X dixièmes par tour », « la voiture derrière revient », alerte à moins d'une seconde |
| Chrono | temps au tour (essais / qualif), meilleur tour et gain, tour invalidé |
| Carburant | consommation moyenne, tours restants, ce qu'il manque pour finir, alertes 4 / 2 / 1 tour ; énergie virtuelle pour les Hypercars et LMGT3 |
| Pneus et freins | usure 50 / 75 / 90 %, pneus trop chauds ou froids, crevaison, roue perdue, freins trop chauds |
| Moteur et dégâts | surchauffe eau / huile, chocs |
| Drapeaux | jaune (secteur et local), full course yellow / voiture de sécurité, stands ouverts, drapeau vert, bleu, rouge, pénalités, limites de piste |
| Stands | arrêt demandé, oubli du limiteur, sortie des stands avec le carburant à bord |

Chaque thème se coupe dans la fenêtre. Les réglages sont gardés dans
`%APPDATA%\IngenieurLMU\reglages.json`.

## Voix

- **Par défaut** : la voix française de Windows (Microsoft Hortense sur un Windows français).
  S'il n'y en a pas : Paramètres > Heure et langue > Voix > ajouter le français.
- **Option Piper** (voix plus naturelle, toujours hors ligne) : créer un dossier `piper`
  à côté de l'exe avec `piper.exe` ([rhasspy/piper](https://github.com/rhasspy/piper/releases))
  et une voix française `.onnx` + `.onnx.json` (par exemple `fr_FR-siwis-medium`).
  L'appli l'utilise automatiquement au démarrage.

## Si le spotter inverse gauche et droite

Cocher **Inverser gauche / droite (spotter)** dans la fenêtre.

## Développement

```
python ingenieur/appli.py --demo          # fenêtre + démo
python ingenieur/appli.py --demo --console
python tests/test_ingenieur.py
```

- `lmu_shm.py` : structure de la mémoire partagée LMU (d'après pyLMUSharedMemory)
- `source_lmu.py` : conversion vers un état de course simple (`etat.py`)
- `moteur.py` : règles d'annonces et spotter
- `voix.py` : file à priorités et voix (SAPI / Piper / console)
- `demo.py` : course simulée
