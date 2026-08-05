# Seb-Metrics — état du projet

Document de reprise : à donner en début de nouvelle conversation pour repartir
avec le contexte sans rejouer l'historique.

Dernière mise à jour : 5 août 2026 (refonte d'interface livrée).

## Le contexte en dix lignes

Sébastien, marathon de New York le 1er novembre 2026, objectif sub-3h.
Records : 2h50'03 (avril 2026), 2h54'35 (octobre 2025), semi 1h22'40.
Tendinopathie d'insertion de l'Achille **droit** en cours. Antécédent de
pubalgie/adducteur à l'hiver 2025, résolue, dont la signature était une
asymétrie d'appui qui s'ouvrait avec l'allure.

Le dépôt public `seb-run/run-lab` héberge un pipeline autonome : webhook Strava
via un Worker Cloudflare, cron quotidien à 05:45 UTC, GitHub Actions qui
synchronise, score, analyse et publie un dashboard PWA sur GitHub Pages.

## Chaîne de données

```
montre Garmin (FR970 + ceinture HRM 600)
  ├── Strava ──────────────► strava_api_sync.py ──► sessions_cache.json
  └── intervals.icu ───────► intervals_sync.py ──► fit_inbox/ ──► fit_ingest.py
                                                    (dynamique de course)
```

Strava fournit distance, allure, FC et laps. Le `.fit` d'origine, récupéré via
intervals.icu, apporte ce que Strava jette : temps de contact au sol, longueur
de foulée, oscillation, équilibre gauche/droite, température, puissance, effet
d'entraînement, intervalles R-R, et le RPE saisi sur la montre.

Point de vigilance : intervals.icu sert deux fichiers, l'original Garmin et son
propre ré-encodage. Seul l'original contient la dynamique par lap. L'ordre des
adresses testées dans `intervals_sync.py` est donc significatif.

## Ce qui a été construit (août 2026)

- **Correctif laps** : les laps Strava étaient lus en temps écoulé au lieu du
  temps en mouvement. Une pause montre transformait un footing régulier en
  fractionné. Corrigé à la source + `scripts/repair_stop_laps.py` pour l'historique.
- **Dérive cardiaque** : découplage allure/FC (Friel), laps d'arrêt et laps
  courts exclus. Descriptif, sans pénalité — sans météo, chaleur et fatigue sont
  indiscernables.
- **Dynamique de course** : `parser_fit.py` extrait 24 indicateurs, dont la
  dérive mécanique premier tiers → dernier tiers et l'asymétrie en fonction de
  l'allure (`asym_vs_allure`). Cette dernière retrouve seule l'épisode
  d'adducteur de février-mars 2026 : trois séances, aucune ailleurs sur 112.
- **Canal sensations** : la description de l'activité Strava remonte jusqu'au
  coach. Le RPE et la sensation de la montre aussi.
- **Débrief de séance** : `session_debrief.py` compare chaque séance à la
  référence personnelle de Sébastien — séances des 60 derniers jours à ±25"/km
  de l'allure du jour, jamais à une norme générale. Affiché sur l'accueil.
- **Journal d'état** : `modules/ci_status.py` écrit dans `data/ci_status.json`
  le succès ou l'échec de chaque étape. Les étapes sont non bloquantes par
  conception, ce journal évite qu'une panne reste invisible dans un build vert.

## Contraintes d'environnement

- **Ne jamais lancer de commande git dans le dossier monté** `~/Documents/seb-metrics`
  depuis l'assistant : la suppression y est bloquée, toute écriture git échoue et
  laisse un `.git/index.lock` orphelin qui casse ensuite les commandes de Sébastien.
  Lire les données via un clone éphémère dans `/tmp`.
- Les commits et push sont faits par Sébastien depuis son Mac.
- L'écriture de fichiers dans le dossier monté est en revanche autorisée.

## Refonte de l'interface (livrée)

Constat de départ sur captures iPhone : l'app est soignée mais se lit comme un
site web. Position retenue, inchangée : la navigation reste conventionnelle, la
singularité passe par la présentation de la donnée.

Corrigé avant la refonte : champ de recherche géant (flex-basis sur un axe
colonne), étiquettes de graphique en bouillie, nuage FC/Allure tassé faute de
`scale: true`, tableau des blocs rogné, allure marathon orpheline.

**1. Quatre onglets, sept lentilles.** Accueil · Plan · Séances · Courses. Le
menu « … » a disparu. Dans Séances, une barre de pictos (Liste, Dérive,
Équilibre, Charge, Efficacité, Volume, Progression) recompose la page autour
d'une métrique. Prédictions a rejoint Courses. Vue d'ensemble a été démantelée :
ses quatre indicateurs coiffent la lentille Liste, ses courbes d'allure et de FC
mensuelles sont passées en Efficacité, son volume hebdomadaire faisait doublon
avec la lentille Volume, sa « dernière séance » avec le débrief d'accueil. Le
comparateur est replié sous la liste.

**2. Accueil en un écran.** La route vers NYC en colonne vertébrale, puis trois
tuiles — Aujourd'hui, L'ai-je bien fait, Ce qu'en dit le coach — chacune une
valeur et une ligne. Toucher une tuile descend vers son détail, sous le pli.
Mesuré : sur iPhone SE (375×667), le pli tombe 92 px sous la dernière tuile.

**3. Couche app.** Police système (Inter et JetBrains Mono retirés du CDN),
en-tête collant qui se condense au défilement, barre d'onglets fixe,
`overscroll-behavior: contain`, View Transitions, retour haptique au toucher,
zones sûres. La bascule de thème est sortie de la barre d'onglets : elle s'y
lisait comme une cinquième destination.

Écart assumé : le comparateur se pilote toujours par deux menus déroulants, et
non en cochant deux lignes de la liste.

### Trois pièges CSS qui ont coûté du temps

- `html, body { height: 100% }` figeait la hauteur du document : le défilement
  se produisait dans le body, donc `window.scrollY` restait à zéro et `sticky`
  n'accrochait rien. Remplacé par `min-height`.
- `overflow-x: hidden` fait de l'élément un conteneur de défilement et casse le
  `sticky` de l'en-tête. `overflow-x: clip` coupe le débordement sans créer ce
  conteneur — c'est la bonne primitive, avec `hidden` en repli.
- Un parent doté de `backdrop-filter` devient conteneur de référence pour ses
  enfants en `position: fixed`. La pastille de thème restait collée dans la
  barre d'onglets tant qu'elle en était l'enfant.

### Vérification

`outputs/verif.py` (Playwright) contrôle en 390×844, 375×667 et 1440×900 :
absence d'erreur console, accueil au-dessus du pli, en-tête collant et condensé,
bascule des quatre onglets et des sept lentilles, un seul panneau visible à la
fois, thème hors de la barre. Le bac à sable n'ayant pas de réseau, ECharts y est
remplacé par une doublure.

## Fuseau horaire et doublons (août 2026)

Deux défauts découverts en cherchant pourquoi une séance du matin
n'apparaissait pas — elle était bien là, mais méconnaissable.

**Fuseau des .fit.** `parser_fit.py` convertissait via `astimezone()` sans
argument, donc vers le fuseau de la machine : juste sur le Mac, faux sur le
runner GitHub Actions qui tourne en UTC. Une séance de 10h03 apparaissait à
08h03. Les 979 séances historiques sont correctes parce qu'importées depuis le
Mac ; les séances passées par Strava aussi, puisque l'API livre
`start_date_local` déjà converti. Seule la voie intervals.icu était touchée, et
c'était sa première séance du jour ingérée par le CI. Le fuseau est désormais
explicite : clé `timezone` dans `config.json`, variable `SEB_TZ` en secours,
`Europe/Paris` par défaut. À basculer sur `America/New_York` pour les .fit
rapportés de novembre.

**Doublons .fit / Strava.** Les deux voies ne partagent aucun identifiant : la
déduplication Strava se fait sur `_strava_id`, absent des entrées .fit. Une
séance ingérée d'abord en .fit réapparaissait donc quand Strava la synchronisait.
`modules/dedup.py` rapproche sur date + distance (300 m) + durée (8 %, plancher
3 min — le .fit compte le temps écoulé, Strava le temps en mouvement, l'écart
atteignait 6m37 sur MaxiRace). La fusion garde la dynamique de course du .fit et
prend de Strava le titre, l'heure et l'identifiant. En cas de candidats
multiples, rien n'est fusionné et c'est signalé : perdre une séance coûte plus
cher que garder un doublon visible.

Le build applique la fusion à chaque passage. `scripts/dedupe_cache.py` rattrape
l'historique — simulation par défaut, `--write` pour appliquer, sauvegarde
horodatée déposée à côté du cache.

## Outils du dépôt

Quatre scripts, un rôle chacun. Aucun n'est obligatoire au quotidien : le CI
fait le travail seul.

- `scripts/pousser.sh` — publie le travail : commit, rebase, push, en une
  commande. Refuse de committer ce qui ressemble à un secret.
- `scripts/verif_secrets.py` — le garde-fou ci-dessus, utilisable seul :
  `--tout` balaie l'ensemble des fichiers suivis.
- `scripts/verif_ui.py` — contrôle visuel dans un vrai navigateur (iPhone 17
  Pro, iPhone SE, desktop) : erreurs console, accueil au-dessus du pli,
  en-tête collant, quatre onglets, sept lentilles, débordements horizontaux.
- `scripts/dedupe_cache.py` — fusionne les doublons .fit/Strava de
  l'historique. Simulation par défaut, `--write` pour appliquer.

**Pourquoi un garde-fou à secrets.** `SETUP_AUTONOME.md` invite à remplacer les
placeholders par ses propres identifiants Strava pour lancer les commandes du
§2. Une fois remplis, ils sont dans un fichier suivi par git, sur un dépôt
public : le commit suivant les publierait, et l'historique les garderait même
après correction — seule leur révocation les neutraliserait. Le §2 porte
désormais l'avertissement, et `pousser.sh` bloque avant le commit.

**Validation des propositions du coach.** `apply_proposal.py` journalisait ses
échecs par `sys.exit(1)`, et c'est la seule étape du workflow sans `|| echo` de
secours : un identifiant inconnu faisait rougir tout le build. Les sorties en
erreur passent maintenant par `ci_status.json` sous la clé `coach_validate`,
comme les autres étapes. Cas le plus fréquent : la page consultée date d'un
build antérieur et l'identifiant affiché n'existe plus, le coach ayant
régénéré ses propositions entre-temps.

## Secrets et services

GitHub Actions : `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`,
`STRAVA_REFRESH_TOKEN`, `ANTHROPIC_API_KEY`, `INTERVALS_API_KEY`,
`INTERVALS_ATHLETE_ID`.
Worker Cloudflare `strava-relay` : `GITHUB_TOKEN`, `GITHUB_REPO`,
`VERIFY_TOKEN`, `VALIDATE_TOKEN`.

## Pièges déjà rencontrés

- `max_tokens` couvre aussi les blocs de raisonnement du modèle : trop bas, la
  réponse revient sans bloc texte et le parsing JSON échoue sur une chaîne vide.
- Ne jamais lire `msg.content[0].text` : le premier bloc peut être un bloc de
  raisonnement. Concaténer les blocs de type `text`.
- Strava plafonne à 100 requêtes par quart d'heure : un backfill large fait
  échouer le build suivant. Toutes les étapes de récupération sont désormais
  non bloquantes.
- Le type de séance détecté automatiquement est peu fiable (un footing avec
  lignes droites est classé « fractionné »). Comparer les séances par allure,
  pas par type.
