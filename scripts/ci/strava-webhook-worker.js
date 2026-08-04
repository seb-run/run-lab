/**
 * seb-metrics — Cloudflare Worker : relay webhook Strava → GitHub Actions
 * =======================================================================
 * Strava ne peut pas appeler GitHub Actions directement ; ce worker fait le pont.
 *
 * Déploiement (voir SETUP_AUTONOME.md) :
 *   1. dash.cloudflare.com → Workers & Pages → Create Worker
 *   2. Colle ce fichier, Deploy
 *   3. Settings → Variables and Secrets :
 *        GITHUB_TOKEN   (secret)  : fine-grained PAT, repo run-lab, permission
 *                                   "Contents: read/write" (repository_dispatch)
 *        VERIFY_TOKEN   (secret)  : chaîne aléatoire de ton choix, la même que
 *                                   celle donnée à Strava à la création du webhook
 *        GITHUB_REPO    (var)     : "seb-run/run-lab"
 *        VALIDATE_TOKEN (secret)  : chaîne aléatoire, saisie une fois dans le
 *                                   dashboard — protège la route /validate
 *        ALLOWED_ORIGIN (var)     : "https://seb-run.github.io" (origine du
 *                                   dashboard, pour le CORS)
 *
 * Strava enverra :
 *   GET  /?hub.challenge=...&hub.verify_token=...   (validation à la création)
 *   POST /  {object_type:"activity", aspect_type:"create", object_id:..., ...}
 *
 * Le dashboard enverra :
 *   POST /validate  {id:"7e4375e9", action:"accept"|"reject", token:"..."}
 */

// Comparaison à temps constant : évite qu'un attaquant devine le jeton
// caractère par caractère en mesurant le temps de réponse.
function safeEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const allowedOrigin = env.ALLOWED_ORIGIN || 'https://seb-run.github.io';
    const corsHeaders = {
      'Access-Control-Allow-Origin': allowedOrigin,
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400',
      'Vary': 'Origin',
    };

    // --- Préflight CORS du dashboard ---
    if (request.method === 'OPTIONS' && url.pathname === '/validate') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    // --- Validation d'une proposition du coach depuis le dashboard ---
    if (url.pathname === '/validate') {
      if (request.method !== 'POST') {
        return new Response('Method Not Allowed', { status: 405, headers: corsHeaders });
      }
      if (!env.VALIDATE_TOKEN) {
        return Response.json({ error: 'VALIDATE_TOKEN non configuré' },
          { status: 503, headers: corsHeaders });
      }

      let body;
      try {
        body = await request.json();
      } catch {
        return Response.json({ error: 'JSON invalide' }, { status: 400, headers: corsHeaders });
      }

      if (!safeEqual(String(body.token || ''), env.VALIDATE_TOKEN)) {
        return Response.json({ error: 'Jeton invalide' }, { status: 401, headers: corsHeaders });
      }

      // Validation stricte : ces valeurs finissent dans un job GitHub Actions.
      const id = String(body.id || '').toLowerCase();
      const action = String(body.action || '').toLowerCase();
      if (!/^[0-9a-f]{6,32}$/.test(id)) {
        return Response.json({ error: 'Identifiant invalide' }, { status: 400, headers: corsHeaders });
      }
      if (action !== 'accept' && action !== 'reject') {
        return Response.json({ error: 'Action invalide' }, { status: 400, headers: corsHeaders });
      }

      const resp = await fetch(
        `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'seb-metrics-coach-validate',
            'X-GitHub-Api-Version': '2022-11-28',
          },
          body: JSON.stringify({
            event_type: 'coach-validate',
            client_payload: { id, action },
          }),
        }
      );
      console.log(`validate ${action} ${id} → ${resp.status}`);

      if (!resp.ok) {
        return Response.json({ error: `GitHub a répondu ${resp.status}` },
          { status: 502, headers: corsHeaders });
      }
      return Response.json({ ok: true, id, action }, { headers: corsHeaders });
    }

    // --- Validation d'abonnement Strava (GET avec hub.challenge) ---
    if (request.method === 'GET') {
      const challenge = url.searchParams.get('hub.challenge');
      const verify = url.searchParams.get('hub.verify_token');
      if (challenge && verify === env.VERIFY_TOKEN) {
        return Response.json({ 'hub.challenge': challenge });
      }
      return new Response('Forbidden', { status: 403 });
    }

    // --- Événement Strava ---
    if (request.method === 'POST') {
      let event;
      try {
        event = await request.json();
      } catch {
        return new Response('Bad Request', { status: 400 });
      }

      // On ne déclenche que sur création/màj d'activité
      const relevant =
        event.object_type === 'activity' &&
        (event.aspect_type === 'create' || event.aspect_type === 'update');

      if (relevant) {
        const resp = await fetch(
          `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
              'Accept': 'application/vnd.github+json',
              'User-Agent': 'seb-metrics-strava-relay',
              'X-GitHub-Api-Version': '2022-11-28',
            },
            body: JSON.stringify({
              event_type: 'strava-activity',
              client_payload: {
                object_id: event.object_id,
                aspect_type: event.aspect_type,
                event_time: event.event_time,
              },
            }),
          }
        );
        console.log(`dispatch ${event.aspect_type} ${event.object_id} → ${resp.status}`);
      }

      // Strava exige un 200 rapide, quoi qu'il arrive
      return new Response('EVENT_RECEIVED', { status: 200 });
    }

    return new Response('Method Not Allowed', { status: 405 });
  },
};
