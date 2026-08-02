/**
 * test_plan_ui.js — Vérifie les fonctions d'interface ajoutées au plan :
 * bandeau d'accueil, célébration de séance validée, ligne chaussure.
 *
 * Exécute app.js dans un DOM minimal (pas de navigateur nécessaire) avec le
 * vrai data/plan_nyc.json en entrée, et contrôle le HTML produit.
 *
 * Usage : node scripts/test_plan_ui.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const plan = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/plan_nyc.json'), 'utf8'));

let fails = 0;
const ok = (cond, label) => {
  console.log((cond ? '  OK   ' : '  ÉCHEC ') + label);
  if (!cond) fails++;
};

// ---------------------------------------------------------------- DOM minimal
function makeEl(id) {
  return {
    id, innerHTML: '', textContent: '', style: { setProperty() {} },
    classList: { _s: new Set(), add(c) { this._s.add(c); }, contains(c) { return this._s.has(c); } },
    querySelector(sel) { return this._q || null; },
    insertAdjacentHTML(pos, html) { this.innerHTML += html; },
  };
}
const els = {};
const store = {};
const sandbox = {
  console,
  document: {
    getElementById: (id) => (els[id] = els[id] || makeEl(id)),
    querySelectorAll: () => [],
    addEventListener() {},
    documentElement: { setAttribute() {}, getAttribute: () => 'light' },
    body: makeEl('body'),
  },
  window: {
    matchMedia: () => ({ matches: false }),
    addEventListener() {},
  },
  localStorage: {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  },
  navigator: { vibrate: () => true },
  location: { hash: '', search: '' },
  setTimeout: (fn) => { try { fn(); } catch (e) {} return 0; },
  Math, Date, JSON, Set, Map, Array, Object, String, Number, isNaN, parseInt, parseFloat,
};
sandbox.window.matchMedia = sandbox.matchMedia = () => ({ matches: false });
sandbox.globalThis = sandbox;

// ------------------------------------------- extraction des fonctions testées
// app.js est une IIFE : on en extrait les fonctions pures pour les tester
// isolément plutôt que de simuler tout l'environnement (ECharts, etc.).
const src = fs.readFileSync(path.join(ROOT, 'templates/app.js'), 'utf8');

function extract(name) {
  const start = src.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`fonction introuvable : ${name}`);
  let i = src.indexOf('{', start), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  throw new Error(`accolade non fermée : ${name}`);
}

const prelude = `
  const VERDICT_META = {
    success: {color:'#22c55e', label:'Réussie',   icon:'✓'},
    partial: {color:'#f59e0b', label:'Partielle', icon:'~'},
    failed:  {color:'#ef4444', label:'Échouée',   icon:'✗'},
    missed:  {color:'#94a3b8', label:'Manquée',   icon:'✗'},
  };
  const CELEB_KEY = 'sebmetrics.celebrated.v1';
  function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function localISODate(){ return TEST_TODAY; }
  function planFindCurrentWeek(){
    const iso = localISODate();
    for (const w of (PLAN.weeks||[])) if (w.start_date<=iso && iso<=w.end_date) return w;
    return null;
  }
`;

const names = ['celebratedSet', 'markCelebrated', 'shouldCelebrate', 'validBanner',
               'burstLayer', 'shoeLine', 'scoreRing', 'homeRenderPlanHero'];
const code = prelude + '\n' + names.map(extract).join('\n\n') + `
  const CELEB_COPY = {
    success: ['Séance validée', 'Exactement ce qui était prévu.'],
    partial: ['Séance en partie tenue', 'Elle compte quand même. On enchaîne.'],
    failed:  ['Séance difficile', "Une séance ne fait pas une préparation."],
  };
`;

sandbox.PLAN = plan;
sandbox.TEST_TODAY = '2026-09-16';   // un mercredi de piste, semaine 15
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

console.log('\n— Bandeau plan sur l\'accueil —');
sandbox.homeRenderPlanHero();
const hero = els.homePlanHero.innerHTML;
ok(hero.includes('plan-hero'), 'le bandeau est rendu');
ok(hero.includes('NYC') || hero.includes('New York'), 'le nom de l\'objectif apparaît');
ok(/J−\d+/.test(hero), 'le compte à rebours est présent');
ok(hero.includes('15') && hero.includes('21'), 'semaine 15 / 21 affichée');
ok(hero.includes('Prochaine séance clé'), 'la prochaine séance clé est annoncée');
ok(hero.includes('PISTE'), 'la séance clé du jour est bien la piste');
ok(!hero.includes('undefined') && !hero.includes('NaN'), 'aucun undefined/NaN');

console.log('\n— Célébration d\'une séance validée —');
const scored = { date: '2026-09-16', score: { points: 88, verdict: 'success', reasons: ['Volume 98%'] } };
ok(sandbox.shouldCelebrate(scored) === true, 'une séance scorée non vue déclenche la célébration');
sandbox.markCelebrated('2026-09-16');
ok(sandbox.shouldCelebrate(scored) === false, 'elle ne se redéclenche pas ensuite');
ok(sandbox.shouldCelebrate({ date: '2026-09-17' }) === false, 'pas de célébration sans score');

const banner = sandbox.validBanner(scored.score);
ok(banner.includes('Séance validée') && banner.includes('88/100'), 'bandeau réussite correct');
ok(sandbox.validBanner({ points: 62, verdict: 'partial' }).includes('en partie'), 'bandeau partiel correct');
ok(sandbox.validBanner({ points: 30, verdict: 'failed' }).includes('difficile'), 'bandeau échec correct');
ok(!/undefined/.test(banner), 'bandeau sans undefined');

const burst = sandbox.burstLayer('#22c55e');
ok((burst.match(/<i /g) || []).length === 16, '16 particules générées');
ok(burst.includes('--dx:') && burst.includes('--rot:'), 'variables d\'animation présentes');

const ring = sandbox.scoreRing(88, 'success', 38, true);
ok(ring.includes('is-drawing'), 'anneau animé quand demandé');
ok(!sandbox.scoreRing(88, 'success', 38, false).includes('is-drawing'), 'anneau statique sinon');

console.log('\n— Ligne chaussure —');
const withShoe = plan.weeks.flatMap(w => w.days || []).find(d => d.shoe);
ok(!!withShoe, 'le plan contient bien des chaussures');
const line = sandbox.shoeLine(withShoe);
ok(line.includes('👟') && line.includes(withShoe.shoe.replace(/&/g, '&amp;')), 'la chaussure est affichée');
ok(sandbox.shoeLine({}) === '', 'pas de ligne si pas de chaussure');

console.log('\n— Couverture du plan —');
const days = plan.weeks.filter(w => w.week_num >= 9).flatMap(w => w.days || []);
const runs = days.filter(d => (d.km || 0) > 0);
ok(runs.every(d => d.shoe), `les ${runs.length} sorties ont une chaussure`);
ok(days.every(d => d.date && d.dow && d.type), 'tous les jours sont complets');

console.log(fails === 0 ? '\n✓ Tous les contrôles passent.\n' : `\n✗ ${fails} contrôle(s) en échec.\n`);
process.exit(fails ? 1 : 0);
