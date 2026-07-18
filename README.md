# Seb Metrics

Dashboard running professionnel à partir d'un historique Strava complet.

Thème Apple Fitness, fond clair, single HTML autonome, mobile-friendly.

---

## Installation (première fois)

1. Télécharge / clone le projet dans un dossier sur ton Mac
2. **Double-clique** sur `INSTALL.command`

Le script va :
- Vérifier Python 3
- Créer un venv local (`.venv/`)
- Installer `fitdecode` + `jinja2`
- Créer `~/Documents/SebMetrics/{A_Ajouter, Archives, data}/`
- Te demander l'URL de ton repo GitHub (optionnel)
- Déposer `update_sebmetrics.command` sur ton **Bureau**

> Si Gatekeeper bloque le `.command` : clic droit → Ouvrir → Confirmer.

---

## Premier import (historique Strava)

Pour importer ton historique complet :

```bash
cd /chemin/vers/seb-metrics
source .venv/bin/activate
python3 build.py --strava /chemin/vers/strava_export
```

À la première exécution, les ~935 séances sont parsées et mises en cache.
Les exécutions suivantes ne reparseront que les fichiers nouveaux (cache MD5).

---

## Workflow quotidien

1. **Drop** tes nouveaux `.fit` dans `~/Documents/SebMetrics/A_Ajouter/`
2. **Double-clique** `update_sebmetrics.command` sur ton Bureau
3. Le dashboard se régénère et est pushé sur GitHub Pages

Les `.fit` traités sont renommés `YYYYMMDD_type_<original>.fit` et déplacés dans `~/Documents/SebMetrics/Archives/`.

---

## Duplication pour quelqu'un d'autre

```bash
python3 build.py \
  --name Christophe \
  --birthdate 15/08/1970 \
  --strava /chemin/strava-christophe \
  --z1-max 116 --z2-max 144 --z3-max 158 --z4-max 173 \
  --goal "Marathon de Berlin" \
  --goal-date 2026-09-20
```

---

## Architecture

```
seb-metrics/
├── INSTALL.command              # installation Mac one-click
├── build.py                     # orchestrateur CLI
├── modules/
│   ├── parser_fit.py            # parser FIT + classification séances
│   ├── cache.py                 # cache MD5 → reparse incrémental
│   ├── builder.py               # assemblage HTML via Jinja2
│   ├── git_push.py              # commit + push GitHub auto
│   ├── coaching.py              # [étape 2] analyse charge + sensations
│   └── plan.py                  # [étape 3] plan adaptatif Daniels+Pfitzinger
├── templates/
│   ├── index.html.j2            # template Jinja2
│   ├── styles.css               # thème Apple Fitness clair
│   └── app.js                   # logique frontend + ECharts
└── output/
    └── index.html               # généré (commité sur GitHub Pages)
```

Données utilisateur (hors repo) : `~/Documents/SebMetrics/`

---

## Commandes utiles

```bash
# Régénération HTML uniquement (sans reparser ni push)
python3 build.py --rebuild-html

# Force reparsing complet
python3 build.py --update --rebuild

# Pas de push GitHub
python3 build.py --update --no-push
```

---

## Statut du développement

- [x] **Étape 1** : structure projet, INSTALL.command, parser FIT modulaire, builder HTML, onglet Vue d'ensemble
- [ ] **Étape 2** : onglets Courses & Records, Volume, Charge & Risque, Efficacité aérobie
- [ ] **Étape 3** : Progression VMA, Prédictions, Comparateur, Séances
- [ ] **Étape 4** : Coaching engine (sensations 4D, phases auto, recommandations)
- [ ] **Étape 5** : Plan adaptatif Daniels+Pfitzinger (génération + ajustement hebdo)
- [ ] **Étape 6** : Analyse marathon détaillée (splits Semi1/Semi2, 10K#1-4)
