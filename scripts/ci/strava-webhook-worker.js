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
 *
 * Strava enverra :
 *   GET  /?hub.challenge=...&hub.verify_token=...   (validation à la création)
 *   POST /  {object_type:"activity", aspect_type:"create", object_id:..., ...}
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

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
