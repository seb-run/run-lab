# Note de décision — faire entrer les données Garmin (.fit) dans le pipeline

État au 04/08/2026. Objectif : récupérer dans `run-lab` les données produites par la
ceinture HRM 600 que l'API Strava ne transmet pas.

## Ce qui se perd aujourd'hui

Le CI passe par l'API REST Strava (`scripts/ci/strava_api_sync.py`). Elle donne :
distance, temps, FC moyenne et max, cadence moyenne, puissance estimée, et les laps
(distance, temps, FC, cadence, watts).

Elle ne donne pas : oscillation verticale, temps de contact au sol, longueur de
foulée, équilibre gauche/droite, ratio vertical, HRV, ni aucune série temporelle
fine. Ces champs existent dans le `.fit` Garmin et **le parser du repo sait déjà les
lire** (`modules/parser_fit.py`, champs FIT 39/41/77/79/84/85). Le maillon manquant
est uniquement le transport : faire arriver le `.fit` dans le CI.

⚠️ À vérifier avant d'investir : quels champs sont réellement présents dans *tes*
`.fit` avec la HRM 600. Le contenu dépend du couple montre/ceinture et certaines
métriques Garmin (charge, tolérance à la course) sont calculées côté Garmin Connect
et n'existent pas dans le fichier. Inventaire possible en 5 minutes sur un fichier
réel.

## Les quatre routes possibles

### 1. Activity API officielle (Garmin Connect Developer Program)
Livraison push du `.fit` complet quelques secondes après la synchro de la montre —
techniquement la solution idéale, et gratuite.
**Blocage** : nécessite une application OAuth approuvée par Garmin, avec dossier et
critères d'évaluation orientés entreprise. Un usage strictement personnel passe
rarement. Délai incertain, hors de notre contrôle.

### 2. Bibliothèque non officielle (`python-garminconnect` / `garth`)
Login Garmin Connect en headless, tokens persistés en secret GitHub, récupération
automatique du `.fit` à chaque séance.
**Risques réels** : l'authentification MFA en environnement headless est un point de
casse documenté (échecs OAuth1/OAuth2 au refresh, 429 sur les IP datacenter), et la
maintenance de ces libs est mouvante. En pratique : ça marche, puis ça casse sans
prévenir, et ça casse silencieusement le briefing du matin.

### 3. Dépôt manuel des `.fit` (déjà en place)
Le workflow historique existe : `.fit` déposé dans `~/Documents/SebMetrics/A_Ajouter`,
build local, push. Zéro dépendance externe, mais suppose ton Mac allumé et une action
manuelle — exactement ce que l'architecture CI de juillet a supprimé.

### 4. Ne rien changer au transport, exploiter mieux l'existant
Les laps Strava contiennent déjà allure + FC + cadence km par km. La dérive
cardiaque, la stabilité de cadence et la lecture des splits en sortent sans une
seule donnée nouvelle. C'est ce qui a été implémenté le 04/08.

## Recommandation

Séquencer, et ne pas faire de la route Garmin un prérequis :

1. **Fait** — exploiter les laps déjà présents (dérive cardiaque, cadence, splits
   transmis au coach).
2. **Fait** — canal de sensations via la description Strava : la donnée subjective
   vaut plus que l'oscillation verticale pour piloter un plan.
3. **À faire, petit** — inventorier les champs d'un `.fit` HRM 600 réel pour savoir
   ce qu'on gagnerait vraiment. Sans cet inventaire, on optimise à l'aveugle.
4. **Ensuite seulement** — déposer une demande Activity API (route 1, gratuite, sans
   dette technique) et, en attendant, garder la route 3 pour les séances où ça
   compte vraiment (séances clés, sorties longues), plutôt que d'automatiser la
   route 2 et d'hériter d'un point de casse permanent.

Ce qu'apporterait la donnée Garmin complète, une fois branchée : détection de
dégradation mécanique en fin de sortie longue (temps de contact au sol qui monte,
foulée qui raccourcit), suivi d'asymétrie G/D — utile avec l'historique Achille —
et statut HRV comme indicateur de récupération avant les séances clés.

## Sources

- [Garmin Connect Developer Program — Activity API](https://developer.garmin.com/gc-developer-program/activity-api/)
- [Garmin Connect Developer Program — Overview](https://developer.garmin.com/gc-developer-program/overview/)
- [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
- [Issue #312 — échec OAuth sur comptes MFA](https://github.com/cyberjunky/python-garminconnect/issues/312)
- [Issue #337 — 429 Too Many Requests au login](https://github.com/cyberjunky/python-garminconnect/issues/337)
- [matin/garth — discussion sur l'avenir du projet](https://github.com/matin/garth/discussions/222)
- [FIT SDK](https://developer.garmin.com/fit/)
