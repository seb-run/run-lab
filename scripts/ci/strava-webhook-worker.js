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
 *        ANTHROPIC_API_KEY (secret) : requis pour /slot-ocr (lecture de photo).
 *                                   Peut être la même clé que celle utilisée
 *                                   par le coach IA (scripts/ci/ai_coach.py).
 *        ANTHROPIC_MODEL (var, optionnel) : défaut "claude-sonnet-5"
 *
 * Strava enverra :
 *   GET  /?hub.challenge=...&hub.verify_token=...   (validation à la création)
 *   POST /  {object_type:"activity", aspect_type:"create", object_id:..., ...}
 *
 * Le dashboard enverra aussi :
 *   POST /validate  {id:"7e4375e9", action:"accept"|"reject", token:"..."}
 *   POST /slot      {date, title, warmup_km, reps, rep_km, rep_pace,
 *                     recovery, cooldown_km, notes, token:"..."}
 *                    — séance de piste du mercredi, saisie depuis l'app.
 *                    Réutilise VALIDATE_TOKEN (pas de secret séparé).
 *   POST /slot-ocr  {image_base64, media_type, token:"..."}
 *                    — photo de la séance envoyée par le coach du club,
 *                    lue par Claude (vision) et renvoyée en JSON structuré
 *                    pour pré-remplir le formulaire (jamais envoyée seule,
 *                    Seb relit et corrige avant d'appuyer sur Envoyer).
 *                    Nécessite le secret ANTHROPIC_API_KEY côté worker.
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

// Lecture de la photo envoyée par le coach du club. Le vocabulaire de piste
// français ("éch", "récup", "VMA", distances sans unité type "6x800") est
// explicité dans le prompt plutôt que supposé connu du modèle.
const OCR_SYSTEM_PROMPT = `Tu lis une photo ou capture d'écran envoyée par un coach de club d'athlétisme, décrivant une séance de piste. Le texte peut être manuscrit, tapé dans une messagerie, ou un tableau d'entraînement. Français courant, abréviations fréquentes : "éch"/"ech" (échauffement), "récup"/"r" (récupération), "rc" (retour au calme), "VMA", "seuil". Distances souvent sans unité ("6x800" = 6 répétitions de 800m). Allures au format "3'30" ou "3:30" (min'sec par km).

Réponds UNIQUEMENT avec un objet JSON, sans texte autour ni bloc de code, exactement dans ce format :
{
  "title": "titre court, ex: Piste club · 6x800m",
  "warmup_km": nombre (km d'échauffement, 0 si absent),
  "reps": nombre entier (répétitions de l'effort principal),
  "rep_km": nombre (distance d'une répétition en km, ex 0.8 pour 800m),
  "rep_pace": "allure cible telle qu'écrite, ex: 3'30\\"/km, ou chaîne vide",
  "recovery": "récupération entre répétitions telle qu'écrite, ex: 90s trot, ou chaîne vide",
  "cooldown_km": nombre (km de retour au calme, 0 si absent),
  "notes": "précisions utiles non capturées ailleurs (séries multiples, terrain, allure progressive...), chaîne vide sinon",
  "confidence": "haute" ou "moyenne" ou "basse"
}

Si la séance a plusieurs blocs différents (ex: 2 séries de 5x400m avec récup différente entre les séries), garde la structure dominante dans les champs et mets le détail complet dans "notes". Si l'image est illisible ou ne montre pas de séance d'entraînement, renvoie confidence:"basse", title:"Illisible", et les autres champs à leurs valeurs par défaut. Ne réponds qu'avec le JSON.`;

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
    if (request.method === 'OPTIONS' &&
        (url.pathname === '/validate' || url.pathname === '/slot' || url.pathname === '/slot-ocr')) {
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

    // --- Séance de piste du mercredi, saisie depuis le dashboard ---
    if (url.pathname === '/slot') {
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

      // Validation légère ici (bornes larges) : la validation stricte qui
      // compte est côté apply_slot.py, qui ne fait confiance à rien de ce
      // qui vient d'Internet. Ce qui suit n'est qu'un garde-fou de premier
      // niveau pour ne pas envoyer un payload absurde dans le dispatch.
      const date = String(body.date || '');
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        return Response.json({ error: 'Date invalide' }, { status: 400, headers: corsHeaders });
      }
      const num = (v, lo, hi, def) => {
        const n = Number(v);
        return Number.isFinite(n) && n >= lo && n <= hi ? n : def;
      };
      const str = (v, max) => String(v || '').trim().slice(0, max);

      const payload = {
        date,
        title: str(body.title, 80) || 'Piste club',
        warmup_km: num(body.warmup_km, 0, 10, 0),
        reps: Math.round(num(body.reps, 1, 20, 0)),
        rep_km: num(body.rep_km, 0.05, 5, 0),
        rep_pace: str(body.rep_pace, 20),
        recovery: str(body.recovery, 40),
        cooldown_km: num(body.cooldown_km, 0, 10, 0),
        notes: str(body.notes, 300),
      };
      if (!payload.reps || !payload.rep_km) {
        return Response.json({ error: 'Répétitions et distance par répétition requises' },
          { status: 400, headers: corsHeaders });
      }

      const resp = await fetch(
        `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'seb-metrics-slot',
            'X-GitHub-Api-Version': '2022-11-28',
          },
          body: JSON.stringify({
            event_type: 'apply-slot',
            client_payload: payload,
          }),
        }
      );
      console.log(`slot ${date} → ${resp.status}`);

      if (!resp.ok) {
        return Response.json({ error: `GitHub a répondu ${resp.status}` },
          { status: 502, headers: corsHeaders });
      }
      return Response.json({ ok: true, date }, { headers: corsHeaders });
    }

    // --- Lecture d'une photo de séance (coach du club) ---
    if (url.pathname === '/slot-ocr') {
      if (request.method !== 'POST') {
        return new Response('Method Not Allowed', { status: 405, headers: corsHeaders });
      }
      if (!env.VALIDATE_TOKEN) {
        return Response.json({ error: 'VALIDATE_TOKEN non configuré' },
          { status: 503, headers: corsHeaders });
      }
      if (!env.ANTHROPIC_API_KEY) {
        return Response.json({ error: 'ANTHROPIC_API_KEY non configuré côté worker' },
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

      const imageB64 = String(body.image_base64 || '');
      const mediaType = String(body.media_type || 'image/jpeg');
      const ALLOWED_MEDIA = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);
      if (!imageB64) {
        return Response.json({ error: 'Image manquante' }, { status: 400, headers: corsHeaders });
      }
      // ~8M caractères base64 ≈ 6 Mo décodés — largement au-dessus de ce que
      // le redimensionnement côté client produit (photo compressée <1 Mo).
      // Un dépassement signale un client qui a sauté l'étape de resize.
      if (imageB64.length > 8_000_000) {
        return Response.json({ error: 'Image trop volumineuse — réessaie' },
          { status: 400, headers: corsHeaders });
      }
      if (!ALLOWED_MEDIA.has(mediaType)) {
        return Response.json({ error: 'Type d\'image non supporté' }, { status: 400, headers: corsHeaders });
      }

      let aiResp;
      try {
        aiResp = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers: {
            'x-api-key': env.ANTHROPIC_API_KEY,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
          },
          body: JSON.stringify({
            model: env.ANTHROPIC_MODEL || 'claude-sonnet-5',
            max_tokens: 1024,
            system: OCR_SYSTEM_PROMPT,
            messages: [{
              role: 'user',
              content: [
                { type: 'image', source: { type: 'base64', media_type: mediaType, data: imageB64 } },
                { type: 'text', text: 'Lis cette séance et réponds avec le JSON demandé.' },
              ],
            }],
          }),
        });
      } catch (e) {
        return Response.json({ error: 'Appel au modèle de lecture échoué' },
          { status: 502, headers: corsHeaders });
      }

      if (!aiResp.ok) {
        console.log(`slot-ocr anthropic → ${aiResp.status}`);
        return Response.json({ error: `Lecture de l'image échouée (${aiResp.status})` },
          { status: 502, headers: corsHeaders });
      }

      let aiJson;
      try {
        aiJson = await aiResp.json();
      } catch {
        return Response.json({ error: 'Réponse du modèle illisible' }, { status: 502, headers: corsHeaders });
      }

      let text = (aiJson.content || [])
        .filter(b => b.type === 'text')
        .map(b => b.text)
        .join('')
        .trim();
      if (text.startsWith('```')) {
        text = text.replace(/^```[a-z]*\n?/i, '').replace(/```\s*$/, '').trim();
      }

      let fields;
      try {
        fields = JSON.parse(text);
      } catch {
        return Response.json({ error: 'Réponse du modèle non structurée — réessaie ou saisis à la main' },
          { status: 502, headers: corsHeaders });
      }

      // Revalidation légère avant de renvoyer au client : mêmes bornes que
      // /slot, la lecture reste soumise à relecture par Seb dans tous les cas.
      const num = (v, lo, hi, def) => {
        const n = Number(v);
        return Number.isFinite(n) && n >= lo && n <= hi ? n : def;
      };
      const str = (v, max) => String(v || '').trim().slice(0, max);
      const clean = {
        title: str(fields.title, 80) || 'Piste club',
        warmup_km: num(fields.warmup_km, 0, 10, 0),
        reps: Math.round(num(fields.reps, 0, 20, 0)),
        rep_km: num(fields.rep_km, 0, 5, 0),
        rep_pace: str(fields.rep_pace, 20),
        recovery: str(fields.recovery, 40),
        cooldown_km: num(fields.cooldown_km, 0, 10, 0),
        notes: str(fields.notes, 300),
      };
      const confidence = ['haute', 'moyenne', 'basse'].includes(fields.confidence) ? fields.confidence : 'moyenne';

      return Response.json({ ok: true, fields: clean, confidence }, { headers: corsHeaders });
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
