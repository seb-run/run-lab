/* ============================================================================
   seb-metrics — cockpit.js

   La couche « je comprends en un coup d'œil » :
     · Accueil  : état de forme (jauge + 4 indicateurs), séance du jour,
                  recommandations du coach, semaine en un trait.
     · Plan     : semaine navigable, jour par jour, décalage d'une séance,
                  frise des 11 semaines jusqu'à NYC.

   Autonome : lit le même bloc #seb-data que app.js et ne dépend d'aucune de
   ses fonctions. Les anciennes cartes restent dans la page, repliées ou
   reléguées plus bas — rien n'est supprimé du code d'origine.

   Écriture : un décalage part vers le Worker Cloudflare (/move) → GitHub
   Actions (apply_move.py) → plan_nyc.json. En attendant le rebuild (~2 min),
   il est appliqué localement, pour que l'écran réponde tout de suite.
   ============================================================================ */
(function () {
  'use strict';

  const RAW = JSON.parse(document.getElementById('seb-data').textContent);
  const PLAN = RAW.plan || null;
  const COACH = RAW.coach || null;
  const DEB = RAW.debrief || null;
  const FORME = COACH && COACH.forme ? COACH.forme : null;

  // ---------------------------------------------------------------- utilitaires
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (v) => String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  const DOW = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
  const DOW_LONG = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
  const MON = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

  function isoLocal(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
  }
  const parse = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d); };
  const TODAY = isoLocal(new Date());
  const dayDiff = (a, b) => Math.round((parse(a) - parse(b)) / 864e5);
  const fmtDay = (iso) => { const d = parse(iso); return DOW[d.getDay()] + ' ' + d.getDate(); };
  const fmtDayLong = (iso) => { const d = parse(iso); return DOW_LONG[d.getDay()] + ' ' + d.getDate() + ' ' + MON[d.getMonth()]; };
  const fmtKm = (k) => (k == null ? '' : (Math.round(k * 10) / 10).toString().replace('.', ',')) + ' km';

  const ICONS = {
    run: '<path d="M13 4a1.6 1.6 0 110 3.2A1.6 1.6 0 0113 4zM9 21l2.5-5.5L9 13l1.5-4.5 3.5 2 3 .5M9 13l-3 1.5"/>',
    bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/>',
    mount: '<path d="M3 20l6-11 4 6 3-4 5 9H3z"/>',
    gauge: '<path d="M4 16a8 8 0 1116 0"/><path d="M12 16l4-5"/>',
    flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    moon: '<path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
    cross: '<path d="M6 6l12 12M18 6L6 18"/>',
    swap: '<path d="M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7"/>',
    arrowUp: '<path d="M7 17L17 7M9 7h8v8"/>',
    arrowDown: '<path d="M7 7l10 10M17 9v8H9"/>',
    arrowFlat: '<path d="M5 12h14M14 7l5 5-5 5"/>',
    heart: '<path d="M12 20s-7-4.6-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.4-7 10-7 10z"/>',
    leaf: '<path d="M5 19c0-9 5-14 14-14 0 9-5 14-14 14zM5 19l7-7"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/>',
    sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    chevL: '<path d="M15 5l-7 7 7 7"/>',
    chevR: '<path d="M9 5l7 7-7 7"/>',
  };
  const svg = (name, size, cls) =>
    `<svg class="ck-i ${cls || ''}" width="${size || 18}" height="${size || 18}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;

  // Types de séance → libellé, teinte, icône. Les types du plan v2 : easy, long,
  // seuil, intervals, mp, shake, race, rest (+ les anciens du moteur interne).
  const TYPES = {
    rest:      { l: 'Repos',            c: 'var(--ck-grey)',   i: 'moon' },
    easy:      { l: 'Footing',          c: 'var(--ck-green)',  i: 'run' },
    recovery:  { l: 'Récup',            c: 'var(--ck-green)',  i: 'leaf' },
    endurance: { l: 'Endurance',        c: 'var(--ck-green)',  i: 'run' },
    long:      { l: 'Sortie longue',    c: 'var(--ck-blue)',   i: 'mount' },
    long_mp:   { l: 'SL allure marathon', c: 'var(--ck-blue)', i: 'mount' },
    mp:        { l: 'Allure marathon',  c: 'var(--ck-violet)', i: 'gauge' },
    mp_run:    { l: 'Allure marathon',  c: 'var(--ck-violet)', i: 'gauge' },
    seuil:     { l: 'Seuil',            c: 'var(--ck-amber)',  i: 'gauge' },
    tempo:     { l: 'Tempo',            c: 'var(--ck-amber)',  i: 'gauge' },
    intervals: { l: 'Fractionné',       c: 'var(--ck-red)',    i: 'bolt' },
    fartlek:   { l: 'Fartlek',          c: 'var(--ck-red)',    i: 'bolt' },
    shake:     { l: 'Activation',       c: 'var(--ck-lime)',   i: 'bolt' },
    race:      { l: 'Course',           c: 'var(--ck-red)',    i: 'flag' },
  };
  const tmeta = (t) => TYPES[t] || { l: t || 'Séance', c: 'var(--ck-grey)', i: 'run' };
  const PHASES = {
    base:  { l: 'Base',       c: 'var(--ck-blue)' },
    build: { l: 'Développement', c: 'var(--ck-amber)' },
    peak:  { l: 'Pic',        c: 'var(--ck-red)' },
    specific: { l: 'Spécifique', c: 'var(--ck-violet)' },
    taper: { l: 'Affûtage',   c: 'var(--ck-green)' },
    race:  { l: 'Course',     c: 'var(--ck-red)' },
  };

  // ---------------------------------------------------------------- plan en mémoire
  const weeks = PLAN && PLAN.weeks ? PLAN.weeks : [];
  function allDays() { return weeks.flatMap(w => w.days.map(d => d)); }
  function findDay(iso) { for (const w of weeks) for (const d of w.days) if (d.date === iso) return d; return null; }
  function weekOf(iso) { return weeks.find(w => w.days.some(d => d.date === iso)) || null; }
  function currentWeekIdx() {
    let i = weeks.findIndex(w => w.start_date <= TODAY && TODAY <= w.end_date);
    if (i < 0) i = TODAY < (weeks[0] || {}).start_date ? 0 : weeks.length - 1;
    return Math.max(0, i);
  }

  const isDone = (d) => !!d.actual && ['done', 'over', 'under', 'bonus'].includes(d.status);
  const canMove = (d) => d.date >= TODAY && d.type !== 'race' && !isDone(d);

  // Décalages envoyés mais pas encore reflétés par le dernier build : appliqués
  // localement. Un décalage est considéré « absorbé » quand les données le
  // montrent déjà (moved_from), ou après 3 h.
  const MOVES_KEY = 'runlab.moves';
  function loadMoves() { try { return JSON.parse(localStorage.getItem(MOVES_KEY) || '[]'); } catch (e) { return []; } }
  function saveMoves(m) { try { localStorage.setItem(MOVES_KEY, JSON.stringify(m)); } catch (e) {} }
  const SLOT_KEYS = ['date', 'dow', 'status', 'actual', 'score'];
  function swapInMemory(aIso, bIso) {
    const a = findDay(aIso), b = findDay(bIso);
    if (!a || !b) return false;
    const pick = (o, inSlot) => Object.fromEntries(Object.entries(o).filter(([k]) => SLOT_KEYS.includes(k) === inSlot));
    const sa = pick(a, true), ca = pick(a, false), sb = pick(b, true), cb = pick(b, false);
    Object.keys(a).forEach(k => delete a[k]); Object.assign(a, cb, sa, { moved_from: bIso, _local: true });
    Object.keys(b).forEach(k => delete b[k]); Object.assign(b, ca, sb, { moved_from: aIso, _local: true });
    return true;
  }
  (function replayPending() {
    const keep = [];
    loadMoves().forEach(m => {
      const a = findDay(m.from);
      const absorbed = a && a.moved_from === m.to;
      const stale = Date.now() - new Date(m.at).getTime() > 3 * 3600e3;
      if (absorbed || stale) return;
      if (swapInMemory(m.from, m.to)) keep.push(m);
    });
    saveMoves(keep);
  })();

  // ---------------------------------------------------------------- toast
  let toastEl = null, toastT = null;
  function toast(msg, kind) {
    if (!toastEl) { toastEl = document.createElement('div'); toastEl.className = 'ck-toast'; document.body.appendChild(toastEl); }
    toastEl.textContent = msg;
    toastEl.dataset.kind = kind || 'ok';
    toastEl.classList.add('on');
    clearTimeout(toastT);
    toastT = setTimeout(() => toastEl.classList.remove('on'), 4200);
  }

  // ---------------------------------------------------------------- feuille (sheet)
  let sheet = null, closeTimer = null;
  function openSheet(html) {
    // Une fermeture encore en cours (animation) ne doit pas cacher la feuille
    // qu'on ouvre juste après : c'est ce qui faisait disparaître le formulaire.
    clearTimeout(closeTimer);
    if (!sheet) {
      sheet = document.createElement('div');
      sheet.className = 'ck-sheet-bk'; sheet.hidden = true;
      sheet.innerHTML = '<div class="ck-sheet" role="dialog" aria-modal="true"><div class="ck-sheet-grip"></div><button class="ck-sheet-x" type="button" aria-label="Fermer">✕</button><div class="ck-sheet-body"></div></div>';
      document.body.appendChild(sheet);
      sheet.addEventListener('click', (e) => { if (e.target === sheet || e.target.closest('.ck-sheet-x')) closeSheet(); });
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });
    }
    $('.ck-sheet-body', sheet).innerHTML = html;
    sheet.hidden = false;
    requestAnimationFrame(() => sheet.classList.add('on'));
    document.body.classList.add('ck-lock');
    return $('.ck-sheet-body', sheet);
  }
  function closeSheet() {
    if (!sheet || sheet.hidden) return;
    sheet.classList.remove('on');
    document.body.classList.remove('ck-lock');
    clearTimeout(closeTimer);
    closeTimer = setTimeout(() => { sheet.hidden = true; }, 220);
  }

  // ---------------------------------------------------------------- Worker (décalage)
  const URL_KEY = 'runlab.validate.url', TOKEN_KEY = 'runlab.validate.token';
  function cfg() {
    try {
      const base = (localStorage.getItem(URL_KEY) || '').replace(/\/+$/, '');
      const token = localStorage.getItem(TOKEN_KEY) || '';
      return base && token ? { base, token } : null;
    } catch (e) { return null; }
  }
  function askConfig(then) {
    const body = openSheet(`
      <h3 class="ck-sheet-h">Connecter l'app à ton coach</h3>
      <p class="ck-muted">Une seule fois par appareil. Ces deux valeurs restent dans ce navigateur : elles ne sont jamais dans le code public.</p>
      <label class="ck-field"><span>URL du Worker Cloudflare</span><input id="ckCfgUrl" type="url" inputmode="url" placeholder="https://strava-relay.xxx.workers.dev" autocomplete="off"></label>
      <label class="ck-field"><span>Jeton de validation</span><input id="ckCfgTok" type="password" placeholder="VALIDATE_TOKEN" autocomplete="off"></label>
      <div class="ck-actions"><button class="ck-btn ck-btn-primary" id="ckCfgSave" type="button">Enregistrer</button></div>`);
    try { $('#ckCfgUrl', body).value = localStorage.getItem(URL_KEY) || ''; } catch (e) {}
    $('#ckCfgSave', body).onclick = () => {
      const u = $('#ckCfgUrl', body).value.trim(), t = $('#ckCfgTok', body).value.trim();
      if (!/^https:\/\//.test(u) || !t) { toast('URL (https) et jeton requis', 'err'); return; }
      try { localStorage.setItem(URL_KEY, u.replace(/\/+$/, '')); localStorage.setItem(TOKEN_KEY, t); } catch (e) {}
      closeSheet(); if (then) setTimeout(then, 260);
    };
  }
  async function sendMove(from, to) {
    const c = cfg();
    if (!c) { askConfig(() => sendMove(from, to)); return; }
    try {
      const r = await fetch(c.base + '/move', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from, to, token: c.token }),
      });
      if (r.status === 401) { try { localStorage.removeItem(TOKEN_KEY); } catch (e) {} throw new Error('jeton refusé — il te sera redemandé'); }
      if (!r.ok) { let m = 'HTTP ' + r.status; try { const j = await r.json(); if (j.error) m = j.error; } catch (e) {} throw new Error(m); }
      swapInMemory(from, to);
      const m = loadMoves(); m.push({ from, to, at: new Date().toISOString() }); saveMoves(m);
      moveFrom = null; renderAll();
      toast('Séance décalée. Le coach recalcule ton plan (~2 min).');
    } catch (e) {
      toast('Échec : ' + (e && e.message ? e.message : 'réseau'), 'err');
    }
  }

  // ---------------------------------------------------------------- statut d'un jour
  function dayState(d) {
    if (d.type === 'rest' && !(d.km > 0)) return { k: 'rest', label: 'Repos' };
    if (isDone(d)) {
      const v = d.score && d.score.verdict;
      if (v === 'failed') return { k: 'fail', label: 'Ratée', pts: d.score.points };
      if (v === 'partial') return { k: 'partial', label: 'Partielle', pts: d.score.points };
      if (v === 'success') return { k: 'ok', label: 'Réussie', pts: d.score.points };
      return { k: 'ok', label: 'Faite' };
    }
    if (d.status === 'missed' || (d.date < TODAY && d.km > 0)) return { k: 'miss', label: 'Manquée' };
    if (d.date === TODAY) return { k: 'today', label: "Aujourd'hui" };
    return { k: 'todo', label: 'À venir' };
  }
  const stateIcon = (s) => ({ ok: svg('check', 16), partial: svg('check', 16), fail: svg('cross', 16), miss: svg('cross', 16), rest: '', today: svg('target', 16), todo: '' }[s.k] || '');

  function paceOf(d) { return d.target_pace || ''; }
  function metaLine(d) {
    const bits = [];
    if (d.km > 0) bits.push(fmtKm(d.km));
    if (paceOf(d)) bits.push(paceOf(d));
    if (d.scheduled_time) bits.push(d.scheduled_time);
    return bits.join(' · ');
  }

  function weekStats(w) {
    const planned = w.days.reduce((s, d) => s + (d.km || 0), 0);
    const done = w.days.reduce((s, d) => s + (isDone(d) && d.actual ? (d.actual.km || 0) : 0), 0);
    const keys = w.days.filter(d => d.key && d.type !== 'race');
    const keysDone = keys.filter(d => isDone(d) && d.score && d.score.verdict !== 'failed').length;
    return { planned, done, keys: keys.length, keysDone };
  }

  // ====================================================================
  // ACCUEIL
  // ====================================================================
  const TONE = {
    bon:        { c: 'var(--ck-green)', l: 'En forme' },
    surveiller: { c: 'var(--ck-amber)', l: 'À surveiller' },
    alerte:     { c: 'var(--ck-red)',   l: 'Alerte' },
  };
  const ETAT = { ok: 'ok', watch: 'watch', alert: 'alert' };
  const IND = [
    { k: 'fraicheur',  l: 'Fraîcheur',  i: 'leaf' },
    { k: 'compliance', l: 'Plan tenu',  i: 'target' },
    { k: 'achille',    l: 'Achille',    i: 'heart' },
    { k: 'aerobie',    l: 'Aérobie',    i: 'run' },
  ];
  const trendIcon = (t) => t === 'up' ? 'arrowUp' : t === 'down' ? 'arrowDown' : 'arrowFlat';

  function gauge(score, color) {
    const R = 84, C = Math.PI * R, pct = Math.max(0, Math.min(100, score)) / 100;
    return `<svg class="ck-gauge" viewBox="0 0 200 118" role="img" aria-label="Forme ${score} sur 100">
      <path d="M16 106 A84 84 0 0 1 184 106" fill="none" stroke="var(--ck-track)" stroke-width="14" stroke-linecap="round"/>
      <path d="M16 106 A84 84 0 0 1 184 106" fill="none" stroke="${color}" stroke-width="14" stroke-linecap="round"
            stroke-dasharray="${(C * pct).toFixed(1)} ${C.toFixed(1)}"/>
      <text x="100" y="92" text-anchor="middle" class="ck-gauge-n">${score}</text>
      <text x="100" y="112" text-anchor="middle" class="ck-gauge-s">/ 100</text>
    </svg>`;
  }

  function daysToRace() {
    const race = (PLAN && PLAN.meta && PLAN.meta.goal_date) || '2026-11-01';
    return { n: dayDiff(race, TODAY), name: (PLAN && PLAN.meta && PLAN.meta.goal_name) || 'NYC' };
  }

  function nextKey() {
    return allDays().filter(d => d.key && d.date >= TODAY && d.type !== 'race' && !isDone(d))
      .sort((a, b) => a.date.localeCompare(b.date))[0] || null;
  }

  function renderForme() {
    const host = $('#ckForme'); if (!host) return;
    if (!FORME) { host.innerHTML = ''; return; }
    const tone = TONE[FORME.verdict] || TONE.surveiller;
    const race = daysToRace();
    const wi = currentWeekIdx(), w = weeks[wi];
    const nk = nextKey();
    const tiles = IND.map(def => {
      const v = (FORME.indicateurs || {})[def.k];
      if (!v) return '';
      const etat = ETAT[v.etat] || 'watch';
      return `<div class="ck-tile ck-${etat}">
        <div class="ck-tile-h">${svg(def.i, 15)}<span>${def.l}</span><em>${svg(trendIcon(v.trend), 15)}</em></div>
        <div class="ck-tile-v">${esc(v.valeur)}</div>
        <div class="ck-tile-n">${esc(v.note)}</div>
      </div>`;
    }).join('');
    host.innerHTML = `
      <section class="ck-hero" style="--tone:${tone.c}">
        <div class="ck-hero-top">
          <div class="ck-hero-gauge">${gauge(FORME.score || 0, tone.c)}</div>
          <div class="ck-hero-txt">
            <div class="ck-verdict">${tone.l}</div>
            <p class="ck-headline">${esc(FORME.headline || '')}</p>
          </div>
        </div>
        <div class="ck-chips">
          <span class="ck-chip">${svg('flag', 13)} J-${race.n} · ${esc(race.name)}</span>
          ${w ? `<span class="ck-chip">S${w.week_num}/${weeks.length}</span>` : ''}
          ${nk ? `<span class="ck-chip ck-chip-key">${svg('bolt', 13)} Clé ${esc(fmtDay(nk.date))}</span>` : ''}
        </div>
        <div class="ck-tiles">${tiles}</div>
        ${FORME.detail ? `<details class="ck-more"><summary>Lecture détaillée du coach</summary><p>${esc(FORME.detail)}</p></details>` : ''}
      </section>`;
  }

  function sessionCard(d, opts) {
    const t = tmeta(d.type), s = dayState(d);
    const desc = (d.description || '').split('\n').filter(l => !/^Chaussures\s*:/.test(l) && !/^\[.*\]$/.test(l.trim())).join('\n').trim();
    return `<div class="ck-session ck-s-${s.k}" style="--c:${t.c}" data-date="${d.date}">
      <div class="ck-session-ico">${svg(t.i, 22)}</div>
      <div class="ck-session-main">
        <div class="ck-session-k">${esc(opts.kicker)}</div>
        <div class="ck-session-t">${esc(d.title)}</div>
        <div class="ck-session-m">${esc(metaLine(d)) || esc(t.l)}</div>
      </div>
      ${d.key ? '<span class="ck-key">CLÉ</span>' : ''}
    </div>${desc && opts.desc ? `<p class="ck-desc">${esc(desc.split('\n').slice(0, 4).join(' · '))}</p>` : ''}`;
  }

  function renderToday() {
    const host = $('#ckToday'); if (!host) return;
    const d = findDay(TODAY);
    if (!d) { host.innerHTML = ''; return; }
    const s = dayState(d);
    let body;
    if (s.k === 'rest') {
      const nk = nextKey();
      body = `<div class="ck-rest">${svg('moon', 22)}<div><b>Repos aujourd'hui</b><span>${nk ? 'Prochaine séance clé : ' + esc(nk.title) + ' · ' + esc(fmtDayLong(nk.date)) : 'Récupère.'}</span></div></div>`;
    } else if (isDone(d)) {
      const a = d.actual, v = d.score || {};
      body = sessionCard(d, { kicker: 'Aujourd\'hui · faite' }) + `
        <div class="ck-result ck-r-${s.k}">
          <div class="ck-result-badge">${stateIcon(s)}<b>${esc(s.label)}</b>${s.pts != null ? `<i>${s.pts}/100</i>` : ''}</div>
          <div class="ck-result-d">${esc(fmtKm(a.km))}${a.pace_str ? ' · ' + esc(a.pace_str) : ''}${a.fc ? ' · FC ' + a.fc : ''}</div>
          ${(v.reasons || []).length ? `<div class="ck-result-r">${esc(v.reasons.join(' · '))}</div>` : ''}
        </div>`;
    } else {
      body = sessionCard(d, { kicker: 'À faire aujourd\'hui', desc: true });
    }
    host.innerHTML = `<section class="ck-card"><div class="ck-card-h"><h3>Aujourd'hui</h3><span>${esc(fmtDayLong(TODAY))}</span></div>${body}
      <div class="ck-actions">
        <button class="ck-btn" type="button" data-open-day="${d.date}">Détail</button>
        ${canMove(d) && d.type !== 'rest' ? `<button class="ck-btn" type="button" data-move-day="${d.date}">${svg('swap', 16)} Décaler</button>` : ''}
      </div></section>`;
  }

  // Recommandations : ce que le coach a fait seul, ce qu'il propose, ce qu'il surveille.
  const KIND_L = {
    volume_adjust: 'Volume ajusté', add_note: 'Consigne', change_type: 'Séance remplacée',
    change_pace: 'Allure revue', move_session: 'Séance déplacée', restructure_week: 'Semaine restructurée', other: 'Reco',
  };
  function renderRecos() {
    const host = $('#ckRecos'); if (!host) return;
    const items = [];
    if (COACH) {
      (COACH.pending || []).filter(p => p.status !== 'expired' && (!p.date || p.date > TODAY)).slice(0, 3).forEach(p => items.push({
        tone: 'ask', ico: 'sparkle', tag: 'Le coach propose', title: (p.replacement && p.replacement.title) || KIND_L[p.kind] || 'Proposition',
        sub: p.reason, date: p.date, id: p.id,
      }));
      (COACH.applied || []).filter(p => !p.date || p.date >= TODAY).slice(0, 3).forEach(p => items.push({
        tone: 'done', ico: 'check', tag: p.auto_major ? 'Adapté seul' : 'Appliqué',
        title: (p.replacement && p.replacement.title) || KIND_L[p.kind] || 'Ajustement',
        sub: p.kind === 'add_note' ? p.new_value : p.reason, date: p.date,
      }));
    }
    if (DEB && DEB.a_surveiller && !/rien à dire|pas de donn/i.test(DEB.a_surveiller)) {
      items.push({ tone: 'watch', ico: 'info', tag: 'À surveiller', title: DEB.a_surveiller, sub: '' });
    }
    if (!items.length) {
      host.innerHTML = `<section class="ck-card"><div class="ck-card-h"><h3>Recos du coach</h3></div><div class="ck-empty">${svg('check', 20)}<span>Rien à ajuster : le plan tient.</span></div></section>`;
      return;
    }
    host.innerHTML = `<section class="ck-card"><div class="ck-card-h"><h3>Recos du coach</h3><span>${items.length}</span></div>
      <div class="ck-recos">${items.map(it => `
        <div class="ck-reco ck-reco-${it.tone}" ${it.id ? `data-id="${esc(it.id)}"` : ''}>
          <div class="ck-reco-ico">${svg(it.ico, 18)}</div>
          <div class="ck-reco-main">
            <div class="ck-reco-tag">${esc(it.tag)}${it.date ? ' · ' + esc(fmtDay(it.date)) : ''}</div>
            <div class="ck-reco-t">${esc(it.title)}</div>
            ${it.sub ? `<div class="ck-reco-s">${esc(String(it.sub).slice(0, 150))}${String(it.sub).length > 150 ? '…' : ''}</div>` : ''}
            ${it.tone === 'ask' ? `<div class="ck-actions"><button class="ck-btn ck-btn-primary" data-decide="accept" data-id="${esc(it.id)}" type="button">Valider</button><button class="ck-btn" data-decide="reject" data-id="${esc(it.id)}" type="button">Refuser</button></div>` : ''}
          </div>
        </div>`).join('')}</div></section>`;
  }

  function weekStrip(w, withTitle) {
    const st = weekStats(w);
    const pct = st.planned ? Math.min(100, Math.round(st.done / st.planned * 100)) : 0;
    return `<div class="ck-wk">
      ${withTitle ? `<div class="ck-card-h"><h3>Semaine ${w.week_num}</h3><span>${fmtKm(st.done)} / ${fmtKm(st.planned)}</span></div>` : ''}
      <div class="ck-dots">${w.days.map(d => {
        const t = tmeta(d.type), s = dayState(d);
        return `<button type="button" class="ck-dot ck-s-${s.k}${d.date === TODAY ? ' is-today' : ''}${d.key ? ' is-key' : ''}" style="--c:${t.c}" data-open-day="${d.date}" aria-label="${esc(fmtDayLong(d.date) + ' : ' + d.title)}">
          <span class="ck-dot-d">${DOW[parse(d.date).getDay()][0]}</span>
          <span class="ck-dot-c">${s.k === 'ok' || s.k === 'partial' ? svg('check', 14) : s.k === 'fail' || s.k === 'miss' ? svg('cross', 14) : s.k === 'rest' ? '' : svg(t.i, 14)}</span>
          <span class="ck-dot-k">${d.km > 0 ? Math.round(d.km) : ''}</span></button>`;
      }).join('')}</div>
      <div class="ck-bar"><i style="width:${pct}%"></i></div>
    </div>`;
  }
  function renderHomeWeek() {
    const host = $('#ckHomeWeek'); if (!host) return;
    const w = weeks[currentWeekIdx()]; if (!w) { host.innerHTML = ''; return; }
    host.innerHTML = `<section class="ck-card">${weekStrip(w, true)}
      <div class="ck-actions"><button class="ck-btn" type="button" data-goto-plan>Voir tout le plan ${svg('chevR', 14)}</button></div></section>`;
  }

  // ====================================================================
  // PLAN
  // ====================================================================
  let viewIdx = currentWeekIdx();
  let moveFrom = null;

  function renderPlanWeek() {
    const host = $('#ckPlanWeek'); if (!host) return;
    const w = weeks[viewIdx]; if (!w) { host.innerHTML = '<p class="ck-muted">Aucun plan chargé.</p>'; return; }
    const st = weekStats(w), ph = PHASES[w.phase] || { l: w.phase_label, c: 'var(--ck-grey)' };
    const pct = st.planned ? Math.min(100, Math.round(st.done / st.planned * 100)) : 0;
    const src = moveFrom ? findDay(moveFrom) : null;
    const rows = w.days.map(d => {
      const t = tmeta(d.type), s = dayState(d);
      const target = !!src && d.date !== moveFrom && canMove(d) && Math.abs(dayDiff(d.date, moveFrom)) <= 6;
      const isSrc = d.date === moveFrom;
      const cls = ['ck-row', 'ck-s-' + s.k, d.date === TODAY ? 'is-today' : '', d.key ? 'is-key' : '', isSrc ? 'is-src' : '', target ? 'is-target' : '', src && !target && !isSrc ? 'is-dim' : ''].join(' ');
      const right = target
        ? `<button class="ck-btn ck-btn-primary ck-btn-sm" type="button" data-swap-to="${d.date}">Ici</button>`
        : isSrc ? '<span class="ck-badge">déplacer…</span>'
        : (s.k === 'rest' || s.k === 'todo' || s.k === 'today') ? '' : `<span class="ck-state ck-st-${s.k}">${stateIcon(s)}${s.pts != null ? `<b>${s.pts}</b>` : ''}</span>`;
      const mv = !src && canMove(d) && d.type !== 'rest' ? `<button class="ck-mv" type="button" data-move-day="${d.date}" aria-label="Décaler ${esc(d.title)}">${svg('swap', 16)}</button>` : '';
      return `<div class="${cls}" style="--c:${t.c}" data-open-day="${d.date}" role="button" tabindex="0">
        <div class="ck-row-date"><b>${DOW[parse(d.date).getDay()]}</b><span>${parse(d.date).getDate()}</span></div>
        <div class="ck-row-bar"></div>
        <div class="ck-row-main">
          <div class="ck-row-t">${esc(d.title)}${d.key ? ' <span class="ck-key">CLÉ</span>' : ''}</div>
          <div class="ck-row-m">${d.type === 'rest' ? 'Repos' : esc(metaLine(d))}${d.moved_from ? ` · <i class="ck-moved">décalée</i>` : ''}${isDone(d) && d.actual ? ` · <b>fait ${esc(fmtKm(d.actual.km))}${d.actual.pace_str ? ' à ' + esc(d.actual.pace_str) : ''}</b>` : ''}</div>
        </div>
        <div class="ck-row-r">${right}${mv}</div>
      </div>`;
    }).join('');
    host.innerHTML = `
      <div class="ck-weeknav">
        <button class="ck-nav" type="button" data-wk="-1" ${viewIdx <= 0 ? 'disabled' : ''} aria-label="Semaine précédente">${svg('chevL', 20)}</button>
        <div class="ck-weeknav-t"><b>Semaine ${w.week_num} <i>/ ${weeks.length}</i></b>
          <span>${esc(fmtDay(w.start_date))} ${MON[parse(w.start_date).getMonth()]} → ${esc(fmtDay(w.end_date))} ${MON[parse(w.end_date).getMonth()]}</span></div>
        <button class="ck-nav" type="button" data-wk="1" ${viewIdx >= weeks.length - 1 ? 'disabled' : ''} aria-label="Semaine suivante">${svg('chevR', 20)}</button>
      </div>
      <div class="ck-phase" style="--c:${ph.c}"><b>${esc(w.phase_label || ph.l)}</b>
        <span>${fmtKm(st.done)} faits sur ${fmtKm(st.planned)}${st.keys ? ` · clés ${st.keysDone}/${st.keys}` : ''}</span></div>
      <div class="ck-bar ck-bar-lg"><i style="width:${pct}%"></i></div>
      ${src ? `<div class="ck-banner">${svg('swap', 16)}<span>Échange <b>${esc(src.title)}</b> (${esc(fmtDay(src.date))}) avec un autre jour.</span><button type="button" class="ck-btn ck-btn-sm" data-cancel-move>Annuler</button></div>` : ''}
      <div class="ck-rows">${rows}</div>`;
  }

  function renderRibbon() {
    const host = $('#ckRibbon'); if (!host) return;
    if (!weeks.length) { host.innerHTML = ''; return; }
    const max = Math.max.apply(null, weeks.map(w => w.target_km || 0)) || 1;
    const cur = currentWeekIdx();
    host.innerHTML = `<div class="ck-card-h"><h3>La route jusqu'à la course</h3><span>${weeks.length} semaines</span></div>
      <div class="ck-ribbon">${weeks.map((w, i) => {
        const ph = PHASES[w.phase] || { c: 'var(--ck-grey)' };
        const race = w.days.some(d => d.type === 'race');
        const past = w.end_date < TODAY;
        const st = weekStats(w);
        const h = Math.max(8, Math.round((w.target_km || 0) / max * 100));
        const hd = Math.round(Math.min(st.done, w.target_km || st.done) / max * 100);
        return `<button type="button" class="ck-rb${i === viewIdx ? ' is-view' : ''}${i === cur ? ' is-cur' : ''}${past ? ' is-past' : ''}" data-wk-set="${i}" style="--c:${ph.c}" aria-label="Semaine ${w.week_num}, ${Math.round(w.target_km || 0)} km">
          <span class="ck-rb-km">${Math.round(w.target_km || 0)}</span>
          <span class="ck-rb-col"><span class="ck-rb-plan" style="height:${h}%"></span><span class="ck-rb-done" style="height:${hd}%"></span></span>
          <span class="ck-rb-n">${race ? svg('flag', 12) : 'S' + w.week_num}</span></button>`;
      }).join('')}</div>
      <div class="ck-legend">${['base', 'build', 'peak', 'taper'].map(k => `<span><i style="background:${PHASES[k].c}"></i>${PHASES[k].l}</span>`).join('')}<span><i class="ck-lg-done"></i>fait</span></div>`;
  }

  // Les cartes d'origine (calendrier 21 semaines, volume recommandé, répartition…)
  // restent accessibles, repliées : elles doublonnent la vue ci-dessus.
  function foldLegacyPlan() {
    const root = $('#t-plan'); if (!root || $('#ckLegacy')) return;
    const legacy = $$(':scope > article', root);
    if (!legacy.length) return;
    const det = document.createElement('details');
    det.id = 'ckLegacy'; det.className = 'ck-legacy';
    det.innerHTML = '<summary>Plus de détails : allures cibles, volumes, répartition</summary>';
    legacy.forEach(a => det.appendChild(a));
    root.appendChild(det);
    ['planTodayCardWrap'].forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
  }

  // ---------------------------------------------------------------- fiche d'un jour
  function openDay(iso) {
    const d = findDay(iso); if (!d) return;
    const t = tmeta(d.type), s = dayState(d);
    const lines = (d.description || '').split('\n');
    const desc = lines.filter(l => !/^Chaussures\s*:/.test(l) && !/^\[.*\]$/.test(l.trim())).join('\n').trim();
    const a = d.actual, sc = d.score;
    const notes = (d.coach_notes || []).map(n => n.text || (n.kind === 'volume' ? `Volume ${n.from}→${n.to} km. ${n.reason || ''}` : '')).filter(Boolean);
    const body = openSheet(`
      <div class="ck-sheet-head" style="--c:${t.c}">
        <span class="ck-sheet-tag">${svg(t.i, 14)} ${esc(t.l)}${d.key ? ' · CLÉ' : ''}</span>
        <h3 class="ck-sheet-h">${esc(d.title)}</h3>
        <p class="ck-muted">${esc(fmtDayLong(d.date))}${d.moved_from ? ' · décalée depuis ' + esc(fmtDay(d.moved_from)) : ''}</p>
      </div>
      <div class="ck-facts">
        ${d.km > 0 ? `<div><span>Distance</span><b>${esc(fmtKm(d.km))}</b></div>` : ''}
        ${d.duration_min ? `<div><span>Durée</span><b>${d.duration_min >= 60 ? Math.floor(d.duration_min / 60) + 'h' + String(d.duration_min % 60).padStart(2, '0') : d.duration_min + ' min'}</b></div>` : ''}
        ${paceOf(d) ? `<div><span>Allure cible</span><b>${esc(paceOf(d))}</b></div>` : ''}
        ${d.scheduled_time ? `<div><span>Heure</span><b>${esc(d.scheduled_time)}</b></div>` : ''}
      </div>
      ${a ? `<div class="ck-result ck-r-${s.k}"><div class="ck-result-badge">${stateIcon(s)}<b>${esc(s.label)}</b>${sc ? `<i>${sc.points}/100</i>` : ''}</div>
        <div class="ck-result-d">Réalisé : ${esc(fmtKm(a.km))}${a.pace_str ? ' · ' + esc(a.pace_str) : ''}${a.fc ? ' · FC ' + a.fc : ''}</div>
        ${sc && sc.reasons && sc.reasons.length ? `<div class="ck-result-r">${esc(sc.reasons.join(' · '))}</div>` : ''}</div>` : ''}
      ${desc ? `<div class="ck-sheet-sec"><h4>Consigne</h4><p class="ck-pre">${esc(desc)}</p></div>` : ''}
      ${notes.length ? `<div class="ck-sheet-sec"><h4>Le coach</h4>${notes.map(n => `<p class="ck-note">${esc(n)}</p>`).join('')}</div>` : ''}
      ${d.shoe ? `<div class="ck-sheet-sec"><h4>Chaussures</h4><p>${esc(d.shoe)}</p></div>` : ''}
      <div class="ck-actions">
        ${canMove(d) && d.type !== 'rest' ? `<button class="ck-btn ck-btn-primary" type="button" data-move-day="${d.date}">${svg('swap', 16)} Décaler cette séance</button>` : ''}
        ${canMove(d) && d.type === 'rest' ? `<button class="ck-btn" type="button" data-move-day="${d.date}">${svg('swap', 16)} Échanger ce repos</button>` : ''}
      </div>`);
    return body;
  }

  function startMove(iso) {
    const d = findDay(iso); if (!d || !canMove(d)) return;
    closeSheet();
    moveFrom = iso;
    const w = weekOf(iso); if (w) viewIdx = weeks.indexOf(w);
    activate('plan');
    renderAll();
    const host = $('#ckPlanWeek'); if (host) setTimeout(() => host.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
  }
  function confirmSwap(to) {
    const a = findDay(moveFrom), b = findDay(to); if (!a || !b) return;
    const from = moveFrom;
    const body = openSheet(`
      <h3 class="ck-sheet-h">Échanger ces deux jours ?</h3>
      <div class="ck-swap">
        <div class="ck-swap-c"><span>${esc(fmtDay(from))}</span><b>${esc(a.title)}</b><i>→ ${esc(fmtDay(to))}</i></div>
        ${svg('swap', 22, 'ck-swap-i')}
        <div class="ck-swap-c"><span>${esc(fmtDay(to))}</span><b>${esc(b.title)}</b><i>→ ${esc(fmtDay(from))}</i></div>
      </div>
      <p class="ck-muted">Le volume de la semaine ne change pas. Le coach relit ton plan et ajuste la suite tout seul.</p>
      <div class="ck-actions"><button class="ck-btn ck-btn-primary" id="ckSwapGo" type="button">Confirmer</button><button class="ck-btn" id="ckSwapNo" type="button">Annuler</button></div>`);
    $('#ckSwapGo', body).onclick = () => { closeSheet(); sendMove(from, to); };
    $('#ckSwapNo', body).onclick = closeSheet;
  }

  // ---------------------------------------------------------------- validation d'une reco
  async function decide(id, action) {
    const c = cfg();
    if (!c) { askConfig(() => decide(id, action)); return; }
    try {
      const r = await fetch(c.base + '/validate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, action, token: c.token }),
      });
      if (r.status === 401) { try { localStorage.removeItem(TOKEN_KEY); } catch (e) {} throw new Error('jeton refusé — il te sera redemandé'); }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const el = $(`.ck-reco[data-id="${id}"]`);
      if (el) el.classList.add('ck-reco-sent');
      toast(action === 'accept' ? 'Validé. Le plan se met à jour dans ~2 min.' : 'Refusé.');
    } catch (e) { toast('Échec : ' + (e && e.message ? e.message : 'réseau'), 'err'); }
  }

  // ---------------------------------------------------------------- orchestration
  function activate(tab) { const b = $(`.tab[data-tab="${tab}"]`); if (b) b.click(); }
  function renderAll() {
    renderForme(); renderToday(); renderRecos(); renderHomeWeek();
    renderPlanWeek(); renderRibbon();
  }

  function mount() {
    const home = $('#t-home'), plan = $('#t-plan');
    if (!home || !plan) return;
    home.insertAdjacentHTML('afterbegin',
      '<div id="ckForme"></div><div id="ckToday"></div><div id="ckRecos"></div><div id="ckHomeWeek"></div>');
    plan.insertAdjacentHTML('afterbegin',
      '<section class="ck-plan"><div id="ckPlanWeek"></div><div id="ckRibbon" class="ck-card"></div></section>');
    // L'ancien accueil : remplacé, pas supprimé.
    ['etatForme', 'homeAnswers', 'homeWeekCard', 'homeTodayCard'].forEach(id => {
      const el = document.getElementById(id); if (el) el.classList.add('ck-hidden');
    });
    foldLegacyPlan();
    // En-tête allégé : compteurs et allures de forme descendent dans une carte
    // en bas de l'accueil — ils ne répondent à aucune question du quotidien.
    const hdr = $('.hero-inner');
    const stats = document.createElement('section');
    stats.className = 'ck-card'; stats.id = 'ckStats';
    stats.innerHTML = '<div class="ck-card-h"><h3>Mes chiffres</h3><span>depuis 2021</span></div>';
    ['.hero-counters', '.hero-row-2'].forEach(sel => { const el = $(sel, hdr || document); if (el) stats.appendChild(el); });
    home.appendChild(stats);
    renderAll();

    document.addEventListener('click', (e) => {
      const t = e.target;
      const swapTo = t.closest('[data-swap-to]');
      if (swapTo) { e.stopPropagation(); confirmSwap(swapTo.dataset.swapTo); return; }
      const mv = t.closest('[data-move-day]');
      if (mv) { e.stopPropagation(); startMove(mv.dataset.moveDay); return; }
      if (t.closest('[data-cancel-move]')) { moveFrom = null; renderAll(); return; }
      const dec = t.closest('[data-decide]');
      if (dec) { decide(dec.dataset.id, dec.dataset.decide); return; }
      if (t.closest('[data-goto-plan]')) { viewIdx = currentWeekIdx(); activate('plan'); renderAll(); return; }
      const wk = t.closest('[data-wk]');
      if (wk) { viewIdx = Math.max(0, Math.min(weeks.length - 1, viewIdx + Number(wk.dataset.wk))); renderPlanWeek(); renderRibbon(); return; }
      const ws = t.closest('[data-wk-set]');
      if (ws) { viewIdx = Number(ws.dataset.wkSet); renderPlanWeek(); renderRibbon(); const h = $('#ckPlanWeek'); if (h) h.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
      const od = t.closest('[data-open-day]');
      if (od && !t.closest('.ck-sheet')) { if (moveFrom) return; openDay(od.dataset.openDay); }
    });
    document.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('.ck-row')) { e.preventDefault(); e.target.click(); }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
