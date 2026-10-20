# LMU Analyzer

Dashboard d'analyse **en temps réel** pour **Le Mans Ultimate** : il lit la télémétrie du jeu pendant que tu roules, compare chaque tour à ton meilleur tour, mètre par mètre, et te montre tes **points forts** et tes **points faibles**, avec une couleur par secteur d'analyse.

| Bloc | Ce qu'il montre |
|---|---|
| Barre haute | Circuit, voiture, session, position, écarts devant / derrière, météo, temps restant |
| Chrono | Tour en cours, **delta en direct** vs meilleur tour, temps prédit, dernier, meilleur, théorique |
| Secteurs | S1 / S2 / S3 du dernier tour (violet = meilleur de la session, vert = record perso, jaune = plus lent) |
| Carte | Tracé enregistré, virages colorés selon le temps gagné ou perdu, position de la voiture |
| Delta cumulé | Où le temps se gagne ou se perd sur la distance |
| Freinage & accélération | Courbes frein / gaz sur le virage le plus coûteux, comparées au meilleur tour |
| Points faibles / forts | Top 3 des virages, la cause (freinage, accélération, vitesse en courbe) et un conseil |
| 6 secteurs d'analyse | Freinage (orange) · Accélération (vert) · Vitesse en courbe (bleu) · Pneus (rose) · Énergie (jaune) · Régularité (violet) |

## Installation (PC de jeu, Windows)

1. Installe **Python 3.9 ou plus récent** depuis [python.org](https://www.python.org/downloads/) et coche « Add Python to PATH ». Aucune autre dépendance n'est nécessaire.
2. Télécharge ce dépôt (bouton **Code → Download ZIP**) et décompresse-le.
3. Active la **mémoire partagée** dans Le Mans Ultimate :
   - Vérifie que `rFactor2SharedMemoryMapPlugin64.dll` est dans le dossier `Le Mans Ultimate\Plugins\`. Sinon, télécharge-le depuis [rF2SharedMemoryMapPlugin](https://github.com/TheIronWolfModding/rF2SharedMemoryMapPlugin/releases) et copie-le dans ce dossier.
   - Lance le jeu une fois, quitte-le, puis ouvre `Le Mans Ultimate\UserData\player\CustomPluginVariables.JSON` et mets `" Enabled": 1` dans le bloc `rFactor2SharedMemoryMapPlugin64.dll`.

## Utilisation

- Double-clique **`lancer.bat`** (ou `python run.py`), puis ouvre **http://localhost:8080**.
- Lance une session dans le jeu : le dashboard se remplit tout seul.
- Sur une tablette ou un second écran du même réseau, ouvre l'adresse affichée dans la fenêtre (`http://IP-du-PC:8080`).

L'analyse démarre après **un tour complet** (il devient la référence) **et un deuxième tour** (comparé à la référence). Chaque nouveau meilleur tour remplace automatiquement la référence.

### Mode démo (sans le jeu)

Double-clique **`demo.bat`** (ou `python run.py --demo`) : une télémétrie simulée du circuit du Mans alimente le dashboard. `--speed 4` accélère la simulation.

### Options

| Option | Rôle |
|---|---|
| `--port 8080` | Port HTTP |
| `--hz 50` | Fréquence de lecture de la télémétrie |
| `--host 127.0.0.1` | N'accepter que ce PC (par défaut, tout le réseau local) |
| `?flip=x` ou `?flip=y` dans l'URL | Retourner la carte si elle apparaît en miroir |

## Fonctionnement

```
Le Mans Ultimate ──(mémoire partagée rF2, 50 Hz)──▶ run.py ──(flux SSE, 10 Hz)──▶ navigateur (web/)
                                                    │
                                                    └─ lmu_dashboard/analyzer.py : tours découpés tous les 10 m,
                                                       delta, détection des virages, diagnostic, notes /100
```

- `lmu_dashboard/rf2_structs.py`, `shared_memory.py` : lecture des buffers `$rFactor2SMMP_Telemetry$` et `$rFactor2SMMP_Scoring$`.
- `lmu_dashboard/analyzer.py` : moteur d'analyse, indépendant de la source.
- `lmu_dashboard/demo.py` : simulateur pour le mode démo.
- `lmu_dashboard/server.py` : serveur HTTP local (`/` = dashboard, `/stream` = temps réel, `/api/state` = JSON).
- `web/` : interface (HTML/CSS/JS, sans dépendance).

### Comment l'analyse juge ton pilotage

- **Virages** : repérés sur les zones de freinage de ton meilleur tour et nommés « Virage 1, 2… » dans l'ordre du tour, avec leur kilomètre.
- **Freinage** : point de freinage (en mètres) et pression maximale comparés à la référence, freinage dégressif, blocages de roue.
- **Accélération** : distance de remise des gaz, patinage des roues arrière, coupures de l'antipatinage, temps passé plein gaz.
- **Vitesse en courbe** : vitesse minimale dans chaque virage par rapport à la référence.
- **Pneus** : température, pression et usure de chaque roue. La fenêtre « idéale » va de 70 à 105 °C.
- **Énergie** : carburant restant, consommation moyenne, tours restants, tour d'arrêt conseillé.
- **Régularité** : écart-type de tes 10 derniers tours valides.

### Limites connues

- La mémoire partagée rFactor 2 n'expose pas l'« énergie virtuelle » propre à LMU : le bloc Énergie utilise le carburant.
- Les tours passés en partie aux stands ne servent ni de référence ni de comparaison.

## Tests

```
python -m unittest discover -s tests
```
