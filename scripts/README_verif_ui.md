# Contrôle visuel de l'interface

`verif_ui.py` rejoue le dashboard dans un navigateur et vérifie ce qu'un build
vert ne dit pas : que la page se comporte comme une app sur un vrai écran.

## Ce qui est contrôlé

- aucune erreur console ni exception au chargement ;
- l'accueil tient au-dessus du pli en 390×844 **et** en 375×667 (iPhone SE) ;
- l'en-tête reste collé en haut et se condense au défilement ;
- les quatre onglets et les sept lentilles s'activent, un seul panneau visible ;
- la bascule de thème n'est pas dans la barre d'onglets, et il y a bien quatre
  onglets et pas cinq.

Les captures partent dans `output/captures/`.

## Lancer

```sh
pip install playwright && playwright install chromium
SEB_DATA_DIR=./data python3 build.py     # produire output/index.html
python3 scripts/verif_ui.py
```

Sortie non nulle s'il y a une anomalie : utilisable tel quel dans un workflow.

## Note

ECharts est chargé depuis un CDN. Dans un environnement sans réseau, le script
le remplace par une doublure : la navigation est testée, pas le tracé des
courbes.
