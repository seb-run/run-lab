/* ============================================================================
   seb-metrics — cockpit2.js

   Trois onglets repensés pour se lire en un regard et donner envie d'y aller :
     · Labo    : un bilan en trois lignes, puis six « angles » cliquables dont
                 chacun annonce déjà sa conclusion.
     · Courses : les prochaines échéances, les records, et l'échelle des
                 objectifs (RP, 2h45, 2h39) rapportée à ce que tu as couru.
     · Renfo   : routines courtes avec démonstration animée.

   Dépend de cockpit.js (window.__ck : outils partagés).
   ============================================================================ */
(function () {
  'use strict';
  const K = window.__ck;
  if (!K) return;
  const { RAW, esc, svg, openSheet, closeSheet, toast, isoLocal, parse, TODAY, fmtDay, fmtDayLong, fmtKm, allDays } = K;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  // Icônes supplémentaires (renfo, labo).
  Object.assign(K.ICONS, {
    dumbbell: '<path d="M6.5 6.5v11M17.5 6.5v11M3 9v6M21 9v6M6.5 12h11"/>',
    pulse: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
    scale: '<path d="M12 4v16M5 8h14M5 8l-2.5 6a3 3 0 005 0L5 8zM19 8l-2.5 6a3 3 0 005 0L19 8z"/>',
    flame: '<path d="M12 3c1 4 5 5 5 10a5 5 0 01-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z"/>',
    timer: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M9 2h6"/>',
    trophy: '<path d="M8 21h8M12 17v4M6 3h12v5a6 6 0 01-12 0V3zM6 5H3v2a4 4 0 004 4M18 5h3v2a4 4 0 01-4 4"/>',
    trend: '<path d="M3 17l5-6 4 3 4-6 5 7"/>',
    play: '<path d="M7 4l13 8-13 8V4z"/>',
    heart2: '<path d="M12 20s-7-4.6-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.4-7 10-7 10z"/>',
    layers: '<path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5"/>',
  });
  const pct1 = (n) => (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(Math.round(n * 10) / 10).toString().replace('.', ',') + ' %';
  const fmtPace = (s) => { if (!s) return '—'; const m = Math.floor(s / 60), r = Math.round(s % 60); return m + "'" + String(r === 60 ? 0 : r).padStart(2, '0') + '"'; };
  const fmtTime = (s) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = Math.round(s % 60); return (h ? h + 'h' + String(m).padStart(2, '0') : m) + "'" + String(r).padStart(2, '0') + (h ? '' : '"'); };
  const dmy = (d) => { const [dd, mm, yy] = d.split('/').map(Number); return new Date(yy, mm - 1, dd); };
  const daysAgo = (n) => new Date(parse(TODAY).getTime() - n * 864e5);

  // ====================================================================
  // LABO
  // ====================================================================
  const SESS = (RAW.sessions || []).map(s => ({ d: dmy(s.d), km: s.km || 0, ps: s.ps || 0, fc: s.fc || 0, tp: s.tp || '', dur: s.dur_s || 0 }))
    .filter(s => !isNaN(s.d));
  function window28(offset) {
    const to = daysAgo(offset), from = daysAgo(offset + 28);
    const r = SESS.filter(s => s.d > from && s.d <= to);
    return {
      n: r.length, km: r.reduce((a, s) => a + s.km, 0), h: r.reduce((a, s) => a + s.dur, 0) / 3600,
      easy: r.filter(s => ['footing', 'endurance', 'sortie_longue'].includes(s.tp) && s.fc > 100 && s.ps > 270 && s.ps < 360),
    };
  }
  const avg = (a) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;

  function laboStories() {
    const days = allDays();
    const withActual = days.filter(d => d.actual && d.date <= TODAY).sort((a, b) => b.date.localeCompare(a.date));
    const w0 = window28(0), w1 = window28(28);
    const out = [];

    // Endurance : dérive cardiaque de la dernière sortie longue
    const longRun = withActual.find(d => d.actual.km >= 14 && !['intervals', 'seuil'].includes(d.type) && !/piste|\d\s*[×x]\s*\d{3,4}\s*m/i.test(d.title || '') && d.score && d.score.hr && d.score.hr.decoupling_pct != null);
    out.push({ lens: 'drift', ico: 'heart2', t: 'Endurance', big: longRun ? pct1(longRun.score.hr.decoupling_pct) : '—',
      line: longRun ? 'dérive cardiaque, ' + fmtDay(longRun.date) + ' (' + fmtKm(longRun.actual.km) + ')' : 'pas de sortie longue récente',
      tone: longRun ? (longRun.score.hr.decoupling_pct <= 5 ? 'ok' : 'watch') : 'na',
      help: 'Plus ton cœur reste stable sur une longue sortie, meilleure est ton endurance.' });

    // Mécanique : contact au sol récent vs précédent (séances continues)
    const cont = withActual.filter(d => d.actual.dyn && d.actual.dyn.stance_ms && !['intervals', 'seuil'].includes(d.type));
    const recent = cont.slice(0, 4).map(d => d.actual.dyn.stance_ms), before = cont.slice(4, 12).map(d => d.actual.dyn.stance_ms);
    const mR = avg(recent), mB = avg(before);
    out.push({ lens: 'balance', ico: 'layers', t: 'Mécanique', big: mR ? Math.round(mR) + ' ms' : '—',
      line: mR && mB ? 'contact au sol (' + pct1((mR - mB) / mB * 100) + ' vs avant)' : 'contact au sol moyen',
      tone: mR && mB ? ((mR - mB) / mB * 100 > 4 ? 'watch' : 'ok') : 'na',
      help: 'Le temps que ton pied reste posé. Plus court = foulée plus économique.' });

    // Charge : 7 derniers jours vs habitude
    const wk = days.filter(d => d.actual && d.date > isoLocal(daysAgo(7)) && d.date <= TODAY).reduce((a, d) => a + (d.actual.dyn && d.actual.dyn.load ? d.actual.dyn.load : 0), 0);
    const prev = days.filter(d => d.actual && d.date > isoLocal(daysAgo(35)) && d.date <= isoLocal(daysAgo(7))).reduce((a, d) => a + (d.actual.dyn && d.actual.dyn.load ? d.actual.dyn.load : 0), 0) / 4;
    out.push({ lens: 'charge', ico: 'flame', t: 'Charge', big: prev ? pct1((wk - prev) / prev * 100) : '—',
      line: prev ? 'cette semaine vs ton habitude' : 'données de charge insuffisantes',
      tone: prev ? ((wk - prev) / prev > 0.25 ? 'watch' : 'ok') : 'na',
      help: 'La fatigue accumulée sur 7 jours, comparée à tes 4 semaines précédentes.' });

    // Efficacité : FC en footing
    const fcNow = avg(w0.easy.map(s => s.fc)), fcPrev = avg(w1.easy.map(s => s.fc));
    const psNow = avg(w0.easy.map(s => s.ps));
    out.push({ lens: 'effic', ico: 'pulse', t: 'Efficacité', big: fcNow ? Math.round(fcNow) + ' bpm' : '—',
      line: fcNow && fcPrev ? 'FC en footing à ' + fmtPace(psNow) + ' (' + (fcNow - fcPrev > 0 ? '+' : '−') + Math.abs(Math.round(fcNow - fcPrev)) + ' vs le mois d\'avant)' : 'FC moyenne en footing',
      tone: fcNow && fcPrev ? (fcNow - fcPrev > 4 ? 'watch' : 'ok') : 'na',
      help: 'À allure facile, une FC qui baisse signifie que ton cœur travaille moins pour la même vitesse.' });

    // Volume
    out.push({ lens: 'vol', ico: 'layers', t: 'Volume', big: Math.round(w0.km) + ' km',
      line: '28 derniers jours' + (w1.km ? ' (' + pct1((w0.km - w1.km) / w1.km * 100) + ' vs les 28 d\'avant)' : ''),
      tone: w1.km ? (w0.km / w1.km > 1.3 ? 'watch' : 'ok') : 'na',
      help: 'Ce que tu as couru sur 4 semaines, par intensité.' });

    // Progression : VMA
    const now = RAW.performance && RAW.performance.now, dl = RAW.performance && RAW.performance.delta;
    out.push({ lens: 'prog', ico: 'trend', t: 'Progression', big: now && now.vma ? now.vma.toFixed(1).replace('.', ',') + ' km/h' : '—',
      line: dl && dl.vma != null && dl.reliable !== false ? 'VMA estimée (' + (dl.vma > 0 ? '+' : '−') + Math.abs(dl.vma).toFixed(1).replace('.', ',') + ' vs il y a 30 j)' : 'VMA estimée par tes séances',
      tone: 'na', help: 'Estimation depuis tes séances : elle sous-évalue ta forme (voir l\'allure marathon en course).' });
    return { out, w0, w1 };
  }

  function renderLabo() {
    const root = $('#t-sess'); if (!root || $('#ckLabo')) return;
    const { out, w0, w1 } = laboStories();
    const dKm = w1.km ? (w0.km - w1.km) / w1.km * 100 : null;
    const html = `
      <section id="ckLabo" class="ck2-labo">
        <div class="ck2-hero">
          <div class="ck2-hero-k">Ton bilan · 28 derniers jours</div>
          <div class="ck2-trio">
            <div><b>${Math.round(w0.km)}</b><span>km${dKm != null ? ' · ' + pct1(dKm) : ''}</span></div>
            <div><b>${w0.n}</b><span>séances</span></div>
            <div><b>${Math.round(w0.h)}h</b><span>de course</span></div>
          </div>
        </div>
        <div class="ck2-sub">Touche un angle pour creuser</div>
        <div class="ck2-grid">${out.map(o => `
          <button type="button" class="ck2-lens ck2-t-${o.tone}" data-lens-go="${o.lens}">
            <div class="ck2-lens-h">${svg(o.ico, 16)}<span>${esc(o.t)}</span></div>
            <div class="ck2-lens-big">${esc(o.big)}</div>
            <div class="ck2-lens-l">${esc(o.line)}</div>
          </button>`).join('')}</div>
        <div class="ck2-sub" id="ckLensAnchor">Les détails</div>
      </section>`;
    root.insertAdjacentHTML('afterbegin', html);
    const intro = $('.labo-intro', root); if (intro) intro.classList.add('ck-hidden');
    root.addEventListener('click', (e) => {
      const b = e.target.closest('[data-lens-go]'); if (!b) return;
      const lens = $(`.lens[data-lens="${b.dataset.lensGo}"]`);
      if (lens) lens.click();
      const a = $('#lensBar') || $('#ckLensAnchor');
      setTimeout(() => { if (a) a.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 120);
    });
  }

  // ====================================================================
  // COURSES
  // ====================================================================
  const DIST = [['5k', '5 km', 5], ['10k', '10 km', 10], ['semi', 'Semi', 21.0975], ['marathon', 'Marathon', 42.195]];
  function bestByDistance() {
    const races = (RAW.races && RAW.races.past_races) || [];
    return DIST.map(([k, l, official]) => {
      const rs = races.filter(r => r.distance_key === k && r.time_s && r.km).map(r => ({ r, pace: r.time_s / r.km, time: r.time_s }));
      // Les distances sous-mesurées (GPS) faussent l'allure : on classe sur le temps officiel.
      rs.sort((a, b) => a.time - b.time);
      return { k, l, official, best: rs[0] || null, count: rs.length };
    });
  }
  const NYC_TARGET_S = (() => { const t = (RAW.plan && RAW.plan.meta && RAW.plan.meta.target_time) || "2h57'00"; const m = t.match(/(\d+)h(\d+)'?(\d+)?/); return m ? (+m[1] * 3600 + +m[2] * 60 + (+m[3] || 0)) : 10620; })();

  function upcoming() {
    const list = [];
    const goals = (RAW.races && RAW.races.countdowns) || [];
    goals.filter(g => g.days_left >= 0).forEach(g => list.push({ name: g.name, date: g.date, days: g.days_left, target: g.target_time, prio: g.priority, type: 'goal' }));
    // Courses-test inscrites dans le plan (ex. 20 km de Paris)
    allDays().filter(d => d.type === 'race' && d.date >= TODAY).forEach(d => {
      const n = d.title.replace(/^[^\wÀ-ÿ]+/u, '');
      if (!list.some(x => x.date === d.date)) list.push({ name: n, date: d.date, days: K.dayDiff(d.date, TODAY), target: null, prio: 'test', type: 'plan' });
    });
    return list.sort((a, b) => a.date.localeCompare(b.date));
  }
  const LADDER = [
    { l: 'NYC · cible plan', s: NYC_TARGET_S, note: '' },
    { l: 'Ton RP actuel', s: 10180, note: 'Amsterdam 2023' },
    { l: '2h45', s: 9900, note: 'objectif crédible' },
    { l: '2h39', s: 9540, note: 'objectif rêve' },
  ];

  function renderCourses() {
    const root = $('#t-race'); if (!root || $('#ckCourses')) return;
    const up = upcoming();
    const prs = bestByDistance();
    const marathons = ((RAW.races && RAW.races.past_races) || []).filter(r => r.distance_key === 'marathon' && r.time_s)
      .sort((a, b) => a.start_time.localeCompare(b.start_time));
    const maxT = Math.max.apply(null, marathons.map(m => m.time_s)), minT = Math.min.apply(null, marathons.map(m => m.time_s));
    const rp = 10180;

    const events = up.map(e => {
      const t = e.name.toLowerCase().includes('milan') ? 'RP · temps à fixer'
        : e.target ? 'Objectif ' + e.target : e.prio === 'test' ? 'Course-test' : 'À définir';
      const key = /new york|nyc/i.test(e.name);
      return `<div class="ck2-ev${key ? ' is-main' : ''}">
        <div class="ck2-ev-j"><b>J-${e.days}</b><span>${esc(fmtDay(e.date))} ${K.MON[parse(e.date).getMonth()]}</span></div>
        <div class="ck2-ev-n"><b>${esc(e.name)}</b><span>${esc(t)}</span></div>
      </div>`;
    }).join('');

    const html = `
      <section id="ckCourses" class="ck2-courses">
        <div class="ck-card-h"><h3>Prochaines échéances</h3><span>${up.length}</span></div>
        <div class="ck2-evs">${events || '<p class="ck-muted">Aucune course à venir.</p>'}</div>

        <div class="ck-card ck2-ladder">
          <div class="ck-card-h"><h3>L'échelle des objectifs</h3><span>marathon</span></div>
          <p class="ck-muted">Ce que chaque temps demande par rapport à ton record. Barre plus longue = temps plus rapide.</p>
          ${LADDER.map(r => {
            const gain = (rp - r.s) / rp * 100;
            const w = Math.max(8, Math.min(100, 100 - (r.s - 9300) / (11000 - 9300) * 100));
            const hard = gain > 5 ? 'is-dream' : gain > 2 ? 'is-hard' : '';
            return `<div class="ck2-rung ${hard}">
              <div class="ck2-rung-h"><b>${esc(r.l)}</b><span>${fmtTime(r.s)} · ${fmtPace(r.s / 42.195)}/km</span></div>
              <div class="ck2-rung-bar"><i style="width:${w}%"></i></div>
              <div class="ck2-rung-n">${r.s === rp ? esc(r.note) : (gain > 0 ? '−' + (Math.round(gain * 10) / 10).toString().replace('.', ',') + ' % vs ton RP' : (Math.abs(Math.round(gain * 10) / 10)).toString().replace('.', ',') + ' % plus lent que ton RP') + (r.note ? ' · ' + esc(r.note) : '')}</div>
            </div>`;
          }).join('')}
          <div class="ck2-gates"><b>Comment décider pour Milan</b>
            <ol><li>20 km de Paris (11/10) : le meilleur capteur de ta forme actuelle.</li>
            <li>NYC (1er nov.) : un temps proche de ton RP sur un parcours dur est un signal fort.</li>
            <li>Après NYC : fixe le temps visé, avec le tendon d'Achille comme feu vert.</li></ol></div>
        </div>

        <div class="ck-card">
          <div class="ck-card-h"><h3>Mes records</h3><span>temps officiels</span></div>
          <div class="ck2-prs">${prs.map(p => p.best ? `<div class="ck2-pr">
            <span>${esc(p.l)}</span><b>${fmtTime(p.best.time)}</b>
            <em>${fmtPace(p.best.time / p.official)}/km · ${esc(p.best.r.start_time.slice(0, 4))}</em></div>` : `<div class="ck2-pr ck2-pr-na"><span>${esc(p.l)}</span><b>—</b><em>pas de course</em></div>`).join('')}</div>
        </div>

        ${marathons.length ? `<div class="ck-card">
          <div class="ck-card-h"><h3>Mes marathons</h3><span>${marathons.length} courses</span></div>
          <div class="ck2-mar">${marathons.map(m => {
            const w = 30 + (maxT - m.time_s) / (maxT - minT || 1) * 70;
            const isRp = m.time_s === minT;
            return `<div class="ck2-mar-r${isRp ? ' is-rp' : ''}"><span>${esc(m.name.replace(/^Marathon (de |d')/, '').replace(/ \d{4}$/, ''))} <i>${esc(m.start_time.slice(0, 4))}</i></span>
              <div class="ck2-mar-b"><i style="width:${w}%"></i></div><b>${fmtTime(m.time_s)}</b></div>`;
          }).join('')}</div>
        </div>` : ''}
      </section>`;

    // Les anciennes cartes ne disparaissent pas : elles passent sous « Plus de détails ».
    const kids = Array.from(root.children);
    root.insertAdjacentHTML('afterbegin', html);
    const det = document.createElement('details');
    det.className = 'ck-legacy'; det.innerHTML = '<summary>Plus de détails : affûtage, projections, courses officielles</summary>';
    kids.forEach(k => det.appendChild(k));
    root.appendChild(det);
  }

  // ====================================================================
  // RENFO
  // ====================================================================
  // Silhouette de profil : points nommés, deux poses, interpolation continue.
  const stand = (ax, ay, tx, ty, o) => {
    o = o || {};
    const hip = [ax, ay - 44], sh = [ax + (o.lean || 0), ay - 72];
    const p = {
      hd: [sh[0] + (o.lean || 0) * 0.3, sh[1] - 14], sh, hip,
      kN: [ax, ay - 22], aN: [ax, ay], tN: [tx, ty],
      eN: [sh[0] + 2, sh[1] + 14], hN: [sh[0] + 6, sh[1] + 28],
      eF: [sh[0] - 2, sh[1] + 14], hF: [sh[0] + 2, sh[1] + 28],
    };
    if (o.bentFar) { p.kF = [ax - 5, ay - 20]; p.aF = [ax - 22, ay - 18]; p.tF = [ax - 29, ay - 18]; }
    else { p.kF = [ax - 6, ay - 22]; p.aF = [ax - 6, ay]; p.tF = [tx - 6, ty]; }
    return p;
  };
  const FLOOR = '<line x1="10" y1="120" x2="190" y2="120" class="ck2-floor"/>';
  const BONES = [['sh', 'hip', 'b'], ['hip', 'kF', 'f'], ['kF', 'aF', 'f'], ['aF', 'tF', 'f'], ['sh', 'eF', 'f'], ['eF', 'hF', 'f'],
    ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['aN', 'tN', 'n'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']];

  const calfUp = (bent) => stand(100, 102, 112, 118, { bentFar: bent }), calfDown = (bent) => stand(100, 114, 112, 118, { bentFar: bent });
  const STEP = '<rect x="86" y="118" width="46" height="14" rx="2" class="ck2-prop"/><line x1="10" y1="132" x2="190" y2="132" class="ck2-floor"/>';

  const EX = {
    iso_calf: {
      name: 'Maintien isométrique du mollet', zone: 'Achille · mollets', dose: '5 × 30 à 45 s', rest: '1 min', level: 'Facile',
      why: "Tenir la position haute charge le tendon sans le faire bouger : c'est ce qui calme la douleur et le renforce, même en phase sensible.",
      steps: ['Debout, les deux pieds sur le sol ou sur une marche (talons dans le vide ou au niveau de la marche).', 'Monte sur la pointe des pieds, et tiens la position la plus haute.', 'Respire, genoux tendus mais non verrouillés. Redescends lentement.'],
      mistakes: ['Laisser les chevilles se plier vers l\'extérieur.', 'Descendre le talon sous le niveau de la marche (voir la précaution).'],
      cue: 'Tiens', mode: 'hold',
      fig: { props: STEP, A: calfUp(false), B: stand(100, 104, 112, 118) },
    },
    calf_raise: {
      name: 'Montée lente sur une jambe', zone: 'Achille · mollets', dose: '3 × 8 à 12 par jambe', rest: '1 min', level: 'Moyen',
      why: "Le geste clé du tendon d'Achille : monter puis descendre très lentement le renforce et améliore sa capacité à encaisser les kilomètres.",
      steps: ['Sur une jambe, les doigts posés sur un mur pour l\'équilibre.', 'Monte sur la pointe en 2 secondes.', 'Redescends en 3 secondes, lentement, jusqu\'à ce que le talon soit au niveau du sol ou de la marche, pas en dessous.'],
      mistakes: ['Aller trop vite : c\'est la descente lente qui travaille.', 'Rebondir en bas.'],
      cue: 'Monte 2 s · descends 3 s', mode: 'loop',
      fig: { props: STEP, A: calfUp(true), B: calfDown(true) },
    },
    bridge: {
      name: 'Pont fessier', zone: 'Fessiers · ischios', dose: '3 × 12', rest: '45 s', level: 'Facile',
      why: "Des fessiers forts stabilisent le bassin et soulagent mollets et tendons : c'est le moteur de ta foulée.",
      steps: ['Allongé sur le dos, genoux pliés, pieds à plat près des fesses.', 'Pousse dans les talons et monte le bassin jusqu\'à aligner épaules-hanches-genoux.', 'Serre les fessiers 1 seconde en haut, puis redescends contrôlé.'],
      mistakes: ['Cambrer le bas du dos pour monter plus haut.', 'Pousser sur les orteils au lieu des talons.'],
      cue: 'Serre en haut', mode: 'loop',
      fig: {
        props: FLOOR,
        bones: [['sh', 'hip', 'b'], ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['aN', 'tN', 'n'], ['hip', 'kF', 'f'], ['kF', 'aF', 'f'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']],
        A: { hd: [34, 112], sh: [50, 113], hip: [100, 113], kN: [124, 88], aN: [144, 118], tN: [154, 119], kF: [127, 88], aF: [147, 118], eN: [70, 116], hN: [90, 116] },
        B: { hd: [34, 112], sh: [50, 113], hip: [100, 90], kN: [128, 84], aN: [144, 118], tN: [154, 119], kF: [131, 84], aF: [147, 118], eN: [70, 116], hN: [90, 116] },
      },
    },
    plank: {
      name: 'Gainage planche', zone: 'Tronc · bassin', dose: '3 × 30 à 40 s', rest: '30 s', level: 'Facile',
      why: "Un tronc solide évite que le bassin s'affaisse quand tu fatigues en fin de course : moins de gaspillage d'énergie.",
      steps: ['Avant-bras au sol sous les épaules, jambes tendues, appui sur la pointe des pieds.', 'Corps aligné de la tête aux talons, ventre et fessiers serrés.', 'Tiens en respirant normalement.'],
      mistakes: ['Hanches qui montent ou qui tombent.', 'Retenir sa respiration.'],
      cue: 'Aligne et tiens', mode: 'hold',
      fig: {
        props: FLOOR,
        bones: [['hd2', 'sh', 'b'], ['sh', 'hip', 'b'], ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['aN', 'tN', 'n'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']],
        A: { hd: [38, 84], hd2: [44, 86], sh: [56, 92], hip: [104, 98], kN: [140, 104], aN: [170, 112], tN: [176, 119], eN: [56, 116], hN: [76, 117] },
        B: { hd: [38, 83], hd2: [44, 85], sh: [56, 91], hip: [104, 95], kN: [140, 102], aN: [170, 111], tN: [176, 119], eN: [56, 116], hN: [76, 117] },
      },
    },
    deadbug: {
      name: 'Dead bug', zone: 'Tronc · coordination', dose: '3 × 8 par côté', rest: '30 s', level: 'Facile',
      why: "Apprend à garder le bas du dos stable pendant que bras et jambes bougent, comme en course.",
      steps: ['Sur le dos, bras tendus vers le plafond, hanches et genoux à 90°.', 'Descends en même temps le bras gauche derrière la tête et la jambe droite vers le sol.', 'Reviens, change de côté. Le bas du dos reste collé au sol.'],
      mistakes: ['Cambrer le dos en descendant.', 'Aller trop vite.'],
      cue: 'Dos collé au sol', mode: 'loop',
      fig: {
        props: FLOOR,
        bones: [['sh', 'hip', 'b'], ['hip', 'kF', 'f'], ['kF', 'aF', 'f'], ['sh', 'eF', 'f'], ['eF', 'hF', 'f'], ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']],
        A: { hd: [34, 112], sh: [50, 113], hip: [100, 113], kN: [104, 84], aN: [136, 84], kF: [108, 84], aF: [140, 84], eN: [52, 90], hN: [52, 66], eF: [56, 90], hF: [56, 66] },
        B: { hd: [34, 112], sh: [50, 113], hip: [100, 113], kN: [104, 84], aN: [136, 84], kF: [132, 108], aF: [170, 112], eN: [34, 100], hN: [18, 106], eF: [56, 90], hF: [56, 66] },
      },
    },
    split: {
      name: 'Fente arrière', zone: 'Cuisses · fessiers', dose: '3 × 8 par jambe', rest: '45 s', level: 'Moyen',
      why: "Renforce une jambe à la fois, comme à chaque appui en course, et corrige les déséquilibres gauche-droite.",
      steps: ['Debout, pieds à largeur de hanches.', 'Fais un grand pas en arrière et descends en gardant le buste droit : le genou avant reste au-dessus de la cheville.', 'Pousse dans le talon avant pour remonter.'],
      mistakes: ['Genou avant qui rentre vers l\'intérieur.', 'Buste penché en avant.'],
      cue: 'Buste droit', mode: 'loop',
      fig: {
        props: FLOOR,
        bones: [['sh', 'hip', 'b'], ['hip', 'kF', 'f'], ['kF', 'aF', 'f'], ['aF', 'tF', 'f'], ['sh', 'eF', 'f'], ['eF', 'hF', 'f'], ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['aN', 'tN', 'n'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']],
        A: { hd: [104, 22], sh: [104, 36], hip: [104, 70], kN: [124, 94], aN: [122, 118], tN: [134, 119], kF: [92, 98], aF: [76, 112], tF: [70, 119], eN: [106, 53], hN: [110, 69], eF: [102, 53], hF: [106, 69] },
        B: { hd: [104, 44], sh: [104, 58], hip: [104, 92], kN: [128, 98], aN: [122, 118], tN: [134, 119], kF: [92, 114], aF: [70, 108], tF: [64, 119], eN: [106, 75], hN: [110, 91], eF: [102, 75], hF: [106, 91] },
      },
    },
    rdl: {
      name: 'Soulevé de terre sur une jambe', zone: 'Ischios · fessiers · équilibre', dose: '3 × 8 par jambe', rest: '45 s', level: 'Moyen',
      why: "Entraîne la chaîne arrière (fessiers, ischios, mollets) et l'équilibre sur un appui : la base d'une foulée stable.",
      steps: ['Debout sur une jambe légèrement fléchie, l\'autre jambe prête à partir en arrière.', 'Penche le buste en avant, dos plat, pendant que la jambe libre monte derrière toi, tout d\'un bloc.', 'Remonte en serrant le fessier de la jambe d\'appui.'],
      mistakes: ['Arrondir le dos.', 'Ouvrir la hanche vers le côté.'],
      cue: 'Dos plat', mode: 'loop',
      fig: {
        props: FLOOR,
        bones: [['sh', 'hip', 'b'], ['hip', 'kF', 'f'], ['kF', 'aF', 'f'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n'], ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['aN', 'tN', 'n']],
        A: { hd: [100, 22], sh: [100, 36], hip: [100, 70], kN: [101, 95], aN: [100, 118], tN: [111, 119], kF: [94, 96], aF: [84, 108], eN: [102, 54], hN: [104, 70] },
        B: { hd: [150, 58], sh: [136, 56], hip: [102, 70], kN: [102, 95], aN: [100, 118], tN: [111, 119], kF: [66, 62], aF: [34, 54], eN: [138, 84], hN: [138, 102] },
      },
    },
    copenhagen: {
      name: 'Planche Copenhague', zone: 'Adducteurs · pubis', dose: '3 × 20 s par côté', rest: '45 s', level: 'Difficile',
      why: "Le meilleur exercice pour les adducteurs : il protège le pubis et l'aine, ta zone fragile de l'hiver 2025.",
      steps: ['Allongé sur le côté, avant-bras au sol, la jambe du dessus posée sur un banc (au genou pour commencer).', 'Monte le bassin pour aligner le corps.', 'Rapproche la jambe du dessous de celle du dessus et tiens. Version facile : genou plié sur le banc.'],
      mistakes: ['Hanche qui s\'affaisse.', 'Se tordre vers l\'avant.'],
      cue: 'Monte le bassin', mode: 'loop',
      fig: {
        props: '<line x1="10" y1="124" x2="190" y2="124" class="ck2-floor"/><rect x="150" y="96" width="36" height="28" rx="3" class="ck2-prop"/>',
        bones: [['hd2', 'sh', 'b'], ['sh', 'hip', 'b'], ['hip', 'kT', 'n'], ['kT', 'aT', 'n'], ['hip', 'kB', 'f'], ['kB', 'aB', 'f'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']],
        A: { hd: [30, 96], hd2: [38, 98], sh: [50, 104], hip: [100, 106], kT: [130, 100], aT: [156, 94], kB: [126, 118], aB: [146, 123], eN: [50, 120], hN: [66, 122] },
        B: { hd: [30, 86], hd2: [38, 88], sh: [50, 98], hip: [100, 94], kT: [130, 96], aT: [156, 94], kB: [128, 98], aB: [152, 98], eN: [50, 120], hN: [66, 122] },
      },
    },
  };

  const ROUTINES = [
    { id: 'tendon', name: 'Tendon & mollets', min: 12, ico: 'heart2', tone: 'var(--ck-amber)', per: '3 fois par semaine',
      blurb: "Le protocole de base pour ton Achille. À faire de préférence en fin de footing ou à la maison.",
      ex: ['iso_calf', 'calf_raise', 'bridge', 'deadbug'] },
    { id: 'hanches', name: 'Hanches & adducteurs', min: 12, ico: 'layers', tone: 'var(--ck-blue)', per: '2 fois par semaine',
      blurb: "Protège le pubis et stabilise le bassin, ce qui compte quand l'allure monte.",
      ex: ['copenhagen', 'bridge', 'split', 'rdl'] },
    { id: 'gainage', name: 'Gainage & foulée', min: 10, ico: 'flame', tone: 'var(--ck-violet)', per: '2 fois par semaine',
      blurb: "Un tronc solide pour garder la foulée propre quand la fatigue arrive.",
      ex: ['plank', 'deadbug', 'rdl', 'split'] },
  ];

  // --- moteur d'animation
  const reduced = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  function figHtml(id, cls) {
    const f = EX[id].fig;
    return `<svg class="ck2-fig ${cls || ''}" viewBox="0 0 200 140" data-fig="${id}" role="img" aria-label="Démonstration : ${esc(EX[id].name)}">${f.props || ''}
      <g class="ck2-bones"></g><circle class="ck2-head" r="9"/></svg>`;
  }
  function startFigs(root) {
    $$('svg[data-fig]', root).forEach(svgEl => {
      if (svgEl.__run) return; svgEl.__run = true;
      const id = svgEl.dataset.fig, ex = EX[id], f = ex.fig;
      const bones = f.bones || BONES, g = $('.ck2-bones', svgEl), head = $('.ck2-head', svgEl);
      const lines = bones.map(b => { const l = document.createElementNS('http://www.w3.org/2000/svg', 'line'); l.setAttribute('class', 'ck2-bone ck2-bone-' + b[2]); g.appendChild(l); return l; });
      const A = f.A, B = f.B;
      const draw = (k) => {
        const pt = (n) => { const a = A[n], b = B[n] || a; return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]; };
        bones.forEach((b, i) => {
          const p = A[b[0]] ? pt(b[0]) : null, q = A[b[1]] ? pt(b[1]) : null;
          if (!p || !q) { lines[i].style.display = 'none'; return; }
          lines[i].setAttribute('x1', p[0]); lines[i].setAttribute('y1', p[1]); lines[i].setAttribute('x2', q[0]); lines[i].setAttribute('y2', q[1]);
        });
        const h = pt('hd'); head.setAttribute('cx', h[0]); head.setAttribute('cy', h[1]);
      };
      if (reduced()) { draw(1); return; }
      const period = ex.mode === 'hold' ? 3600 : 3200;
      let t0 = null;
      const step = (ts) => {
        if (!svgEl.isConnected) return;
        if (t0 === null) t0 = ts;
        const ph = ((ts - t0) % period) / period;                     // 0..1
        const tri = ph < 0.5 ? ph * 2 : 2 - ph * 2;                   // aller-retour
        // plateau en haut et en bas : le mouvement se lit, le temps de tenue aussi
        const k = Math.min(1, Math.max(0, (tri - 0.15) / 0.7));
        draw(k * k * (3 - 2 * k));
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  // --- journal : séances de renfo faites
  const LOG = 'runlab.renfo';
  const readLog = () => { try { return JSON.parse(localStorage.getItem(LOG) || '{}'); } catch (e) { return {}; } };
  const writeLog = (o) => { try { localStorage.setItem(LOG, JSON.stringify(o)); } catch (e) {} };
  function weekKey(d) { const x = new Date(d); const day = (x.getDay() + 6) % 7; x.setDate(x.getDate() - day); return isoLocal(x); }
  function doneThisWeek(rid) {
    const log = readLog(), wk = weekKey(parse(TODAY));
    return Object.keys(log).filter(d => weekKey(parse(d)) === wk && (log[d] || []).includes(rid)).length;
  }
  const TARGET = { tendon: 3, hanches: 2, gainage: 2 };

  function planMuscu() {
    return allDays().filter(d => d.date >= TODAY && (/muscu/i.test(d.title || '') || /muscu/i.test(d.description || '')))
      .sort((a, b) => a.date.localeCompare(b.date)).slice(0, 3);
  }

  function renderRenfo() {
    const root = $('#t-renfo'); if (!root) return;
    const mus = planMuscu();
    root.innerHTML = `
      <section class="ck2-renfo">
        <div class="ck2-hero ck2-hero-renfo">
          <div class="ck2-hero-k">Renfo pour progresser</div>
          <p class="ck2-hero-t">10 à 12 minutes, sans matériel. Chaque exercice a sa démonstration animée.</p>
        </div>
        <div class="ck2-warn">${svg('info', 18)}<span><b>Tendon d'Achille :</b> ne descends jamais le talon sous le niveau de la marche (tendinopathie d'insertion). Si la douleur dépasse 3/10 ou persiste le lendemain, on arrête. Fais valider ce protocole par ton kiné.</span></div>
        ${mus.length ? `<div class="ck2-planmus"><b>Dans ton plan</b>${mus.map(d => `<span>${esc(fmtDay(d.date))} · ${esc(d.title)}</span>`).join('')}</div>` : ''}
        <div class="ck2-routines">${ROUTINES.map(r => {
          const n = doneThisWeek(r.id), t = TARGET[r.id];
          return `<button type="button" class="ck2-routine" data-routine="${r.id}" style="--c:${r.tone}">
            <div class="ck2-routine-ico">${svg(r.ico, 22)}</div>
            <div class="ck2-routine-main"><b>${esc(r.name)}</b><span>${r.min} min · ${esc(r.per)}</span>
              <div class="ck2-routine-dots">${Array.from({ length: t }, (_, i) => `<i class="${i < n ? 'on' : ''}"></i>`).join('')}<em>${n}/${t} cette semaine</em></div></div>
            ${svg('chevR', 18)}
          </button>`;
        }).join('')}</div>
        <div class="ck-card-h ck2-lib-h"><h3>Tous les exercices</h3><span>${Object.keys(EX).length}</span></div>
        <div class="ck2-lib">${Object.keys(EX).map(id => `<button type="button" class="ck2-ex" data-ex="${id}">${figHtml(id, 'ck2-fig-sm')}<b>${esc(EX[id].name)}</b><span>${esc(EX[id].zone)}</span></button>`).join('')}</div>
      </section>`;
    startFigs(root);
  }

  function openExercise(id, fromRoutine) {
    const ex = EX[id]; if (!ex) return;
    const body = openSheet(`
      <span class="ck-sheet-tag" style="--c:var(--ck-green)">${svg('dumbbell', 14)} ${esc(ex.zone)}</span>
      <h3 class="ck-sheet-h">${esc(ex.name)}</h3>
      <div class="ck2-demo">${figHtml(id, 'ck2-fig-lg')}<div class="ck2-cue">${esc(ex.cue || '')}</div></div>
      <div class="ck-facts">
        <div><span>Séries</span><b>${esc(ex.dose)}</b></div>
        <div><span>Repos</span><b>${esc(ex.rest)}</b></div>
        <div><span>Niveau</span><b>${esc(ex.level)}</b></div>
      </div>
      <div class="ck-sheet-sec"><h4>Pourquoi, pour courir</h4><p>${esc(ex.why)}</p></div>
      <div class="ck-sheet-sec"><h4>Comment faire</h4><ol class="ck2-steps">${ex.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol></div>
      <div class="ck-sheet-sec"><h4>À éviter</h4><ul class="ck2-mistakes">${ex.mistakes.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>
      ${id === 'iso_calf' || id === 'calf_raise' ? '<p class="ck2-warn-s">Précaution : talon jamais sous le niveau de la marche. Douleur supérieure à 3/10 : on s\'arrête.</p>' : ''}`);
    startFigs(body);
  }

  function openRoutine(rid) {
    const r = ROUTINES.find(x => x.id === rid); if (!r) return;
    const log = readLog(), doneToday = (log[TODAY] || []).includes(rid);
    const body = openSheet(`
      <span class="ck-sheet-tag" style="--c:${r.tone}">${svg(r.ico, 14)} ${r.min} min</span>
      <h3 class="ck-sheet-h">${esc(r.name)}</h3>
      <p class="ck-muted">${esc(r.blurb)}</p>
      <div class="ck2-rlist">${r.ex.map((id, i) => `<button type="button" class="ck2-rex" data-ex="${id}">
        <span class="ck2-rex-n">${i + 1}</span>${figHtml(id, 'ck2-fig-xs')}
        <div><b>${esc(EX[id].name)}</b><span>${esc(EX[id].dose)}</span></div></button>`).join('')}</div>
      <div class="ck-actions"><button type="button" class="ck-btn ck-btn-primary" data-renfo-done="${r.id}">${doneToday ? 'Déjà fait aujourd\'hui ✓' : 'Séance faite'}</button></div>`);
    startFigs(body);
  }

  function markDone(rid) {
    const log = readLog(); log[TODAY] = log[TODAY] || [];
    if (!log[TODAY].includes(rid)) log[TODAY].push(rid);
    writeLog(log); closeSheet(); renderRenfo();
    toast('Séance de renfo enregistrée. Bien joué.');
  }

  // ---------------------------------------------------------------- montage
  function mount() {
    renderLabo(); renderCourses(); renderRenfo();
    document.addEventListener('click', (e) => {
      const t = e.target;
      const done = t.closest('[data-renfo-done]'); if (done) { markDone(done.dataset.renfoDone); return; }
      const ex = t.closest('[data-ex]'); if (ex) { openExercise(ex.dataset.ex); return; }
      const rt = t.closest('[data-routine]'); if (rt) { openRoutine(rt.dataset.routine); return; }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(mount, 0));
  else setTimeout(mount, 0);
})();
