# Seb-Metrics — état du projet

Document de reprise : à donner en début de nouvelle conversation pour repartir
avec le contexte sans rejouer l'historique.

Dernière mise à jour : 5 août 2026.

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

## Chantier en cours : refonte de l'interface

Constat sur captures iPhone : l'app est soignée mais se lit comme un site web.

Corrigé : champ de recherche géant (flex-basis sur un axe colonne), étiquettes
de graphique en bouillie, nuage FC/Allure tassé faute de `scale: true`, tableau
des blocs rogné, allure marathon orpheline.

À faire, dans l'ordre convenu :

1. **Fusion en onglet Séances** — onze vues pour quatre onglets, sept cachées
   derrière un menu « … ». Les vues d'analyse deviennent des pictos au-dessus de
   la liste (dérive cardiaque, équilibre G/D, charge, efficacité, volume,
   progression), chacun recomposant la liste autour de sa métrique.
   Cible : quatre onglets, Aujourd'hui · Plan · Séances · Courses.
2. **Accueil en un écran** — répondre à « quoi aujourd'hui, l'ai-je bien fait,
   que dit le coach » sans défiler. La sparkline « route vers NYC » comme
   colonne vertébrale.
3. **Couche app** — zones sûres, barres translucides, en-tête et barre d'onglets
   fixes avec défilement du seul contenu, `overscroll-behavior: contain`,
   View Transitions, retour au toucher, police système.

Position retenue : la navigation reste conventionnelle, la singularité passe par
la présentation de la donnée. Une navigation « novatrice » produit de la friction.

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
