# Seb Metrics — Setup pipeline autonome

Objectif : séance Strava terminée → dashboard à jour ~2 min après, Mac éteint ou pas,
avec analyse du Coach IA. Durée totale du setup : ~25 min, une seule fois.

Ce dont tu as besoin : ton compte Strava, ton compte GitHub, un compte Cloudflare
(gratuit), un compte Anthropic (console.anthropic.com).

---

## §0 — AVANT TOUT : confidentialité du repo

Le pipeline committe `data/sessions_cache.json` (toutes tes séances : dates, FC,
allures, titres avec noms d'amis) dans le repo `run-lab`.

- **Si le repo est public** : ces données seront visibles par n'importe qui.
- **Si tu le passes en privé** : GitHub Pages nécessite alors un plan payant
  (GitHub Pro, ~4 $/mois) pour continuer à servir le dashboard.
- **Alternative** : héberger le dashboard sur Cloudflare Pages (gratuit, repos privés
  acceptés) au lieu de GitHub Pages. Demande-moi si tu veux cette option.

Vérifie : github.com/seb-run/run-lab → si tu vois "Public" à côté du nom, décide
avant de continuer.

---

## §1 — App API Strava (5 min)

1. Va sur **strava.com/settings/api** (connecté à ton compte).
2. Remplis :
   - Application Name : `Seb Metrics`
   - Category : Data Importer
   - Website : `https://seb-run.github.io`
   - Authorization Callback Domain : `localhost`
3. Valide. Note **Client ID** et **Client Secret** (bouton "Show").

## §2 — Refresh token avec le bon scope (5 min)

Le token affiché sur la page API n'a pas le scope activités. Il faut passer par
le flow OAuth une fois :

1. Dans ton navigateur, ouvre (remplace `TON_CLIENT_ID`) :
   ```
   https://www.strava.com/oauth/authorize?client_id=TON_CLIENT_ID&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all
   ```
2. Clique **Authorize**. Tu atterris sur une page d'erreur `localhost` — c'est normal.
   Copie le paramètre `code=XXXX` dans la barre d'adresse (entre `code=` et `&scope`).
3. Dans le Terminal du Mac (remplace les 3 valeurs) :
   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=TON_CLIENT_ID \
     -d client_secret=TON_CLIENT_SECRET \
     -d code=LE_CODE_COPIE \
     -d grant_type=authorization_code
   ```
4. Dans la réponse JSON, note le **`refresh_token`**. C'est lui qu'on met en secret.

> Rotation : si un jour le workflow affiche "Nouveau refresh_token émis par Strava",
> récupère-le dans les logs du job et mets à jour le secret. En pratique, rare.

## §3 — Secrets GitHub (3 min)

github.com/seb-run/run-lab → **Settings → Secrets and variables → Actions →
New repository secret**, quatre fois :

| Nom | Valeur |
|---|---|
| `STRAVA_CLIENT_ID` | (§1) |
| `STRAVA_CLIENT_SECRET` | (§1) |
| `STRAVA_REFRESH_TOKEN` | (§2) |
| `ANTHROPIC_API_KEY` | (§4) |

## §4 — Clé API Anthropic (3 min)

1. **console.anthropic.com** → Settings → API Keys → Create Key, nom `seb-metrics-coach`.
2. Copie la clé (`sk-ant-...`) dans le secret `ANTHROPIC_API_KEY`.
3. Ajoute ~5 $ de crédit (Billing). Coût réel : ~1 à 3 centimes par analyse,
   soit < 1 €/mois à raison d'un build par séance + le filet quotidien.

## §5 — Premier test du pipeline (2 min)

github.com/seb-run/run-lab → onglet **Actions** → `build-dashboard` →
**Run workflow**. Le job doit dérouler : Sync Strava → Build → Coach IA → Publish.
Si "Coach IA indisponible", vérifie la clé Anthropic — le dashboard se publie
quand même sans analyse.

## §6 — Webhook Strava temps réel (10 min)

Sans cette étape, le dashboard se met à jour une fois par jour (cron 05:45 UTC).
Avec : ~2 min après chaque séance.

### a. PAT GitHub pour le worker
github.com → Settings (ton profil) → Developer settings → **Fine-grained tokens**
→ Generate new token :
- Repository access : Only select repositories → `run-lab`
- Permissions : **Contents → Read and write**
- Expiration : 1 an. Copie le token.

### b. Déployer le Cloudflare Worker
1. **dash.cloudflare.com** → Workers & Pages → Create → Worker,
   nom `strava-relay`, Deploy.
2. Edit code → colle le contenu de `scripts/ci/strava-webhook-worker.js` → Deploy.
3. Settings du worker → Variables and Secrets :
   - `GITHUB_TOKEN` (type Secret) : le PAT du §a
   - `VERIFY_TOKEN` (type Secret) : une chaîne aléatoire de ton choix (garde-la)
   - `GITHUB_REPO` (type Text) : `seb-run/run-lab`
4. Note l'URL du worker : `https://strava-relay.XXX.workers.dev`

### c. Abonner Strava au webhook
Terminal (remplace les 4 valeurs) :
```bash
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -d client_id=TON_CLIENT_ID \
  -d client_secret=TON_CLIENT_SECRET \
  -d callback_url=https://strava-relay.XXX.workers.dev \
  -d verify_token=TON_VERIFY_TOKEN
```
Réponse attendue : `{"id": ...}`. C'est fini : cours, et regarde le dashboard.

## §7 — Installer la PWA sur l'iPhone (1 min)

Safari → ton dashboard → bouton Partager → **Sur l'écran d'accueil**.
Icône, plein écran, consultable hors-ligne (dernière version en cache).

---

## Fonctionnement au quotidien

- **Nouvelle séance** → webhook → build auto → dashboard à jour (+ analyse coach).
- **Ajustements mineurs** (volume ±10 %, consignes) : appliqués automatiquement,
  visibles dans la carte "Coach IA" de l'onglet Plan.
- **Propositions majeures** (déplacer une séance clé, restructurer une semaine) :
  jamais appliquées seules — elles attendent ta validation au briefing du matin.
- **Briefing 6h30** (tâche Claude) : séance du jour, sync de secours, et validation
  des propositions majeures en un mot.
- **Local** : rien ne change sur le Mac (`~/Documents/SebMetrics` intact). En CI,
  les données vivent dans `data/` du repo (`SEB_DATA_DIR`).

## Dépannage

- Job rouge à l'étape Sync : vérifier les 3 secrets Strava (§3).
- "Nouveau refresh_token émis" dans les logs : mettre à jour le secret (§2).
- Webhook muet : dash.cloudflare.com → worker → Logs, puis
  `curl https://www.strava.com/api/v3/push_subscriptions -d client_id=... -d client_secret=... -G` pour vérifier l'abonnement.
- PWA pas à jour : tirer pour rafraîchir (le service worker recharge le réseau d'abord).
