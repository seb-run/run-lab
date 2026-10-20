/* ============================================================================
   seb-metrics — cockpit4.js : SÉANCE DU CLUB (Harbat, mercredi soir)

   Remplace l'ancien formulaire, limité à « N répétitions × une distance ».
   Une séance de club est une SUITE de blocs : 1600 · 800 · 1200 · 600 · 1000 · 500,
   chacun avec son allure nommée (marathon, seuil, semi, 10 km, 5 km) et sa
   récupération. Trois façons de la saisir :
     · une photo (lue par le Worker, qui rend un bloc par ligne),
     · le texte collé (lu ici même, sans réseau),
     · à la main, bloc par bloc.
   Les allures nommées sont converties avec « mes allures », modifiables.
   Remplace window.openSlotModal : les boutons existants ouvrent cette feuille.
   ============================================================================ */
(function () {
  'use strict';
  const K = window.__ck;
  if (!K) return;
  const { RAW, esc, svg, openSheet, closeSheet, toast, isoLocal, parse, TODAY, fmtDayLong, allDays, cfg, askConfig, findDay } = K;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  // ---------------------------------------------------------------- allures de référence
  // Dérivées de ton 20 km de Paris (1h14'17) par équivalence de course ; ajustables.
  const PACES_KEY = 'runlab.clubpaces';
  const DEFAULT_PACES = { marathon: "4'00\"", seuil: "3'41\"", semi: "3'44\"", '10k': "3'34\"", '5k': "3'25\"", vma: "3'18\"" };
  const LABELS = [['libre', 'Libre'], ['marathon', 'Marathon'], ['semi', 'Semi'], ['seuil', 'Seuil'], ['10k', '10 km'], ['5k', '5 km'], ['vma', 'VMA']];
  const fmtP = (sec) => { const m = Math.floor(sec / 60), r = Math.round(sec % 60); return m + "'" + String(r === 60 ? 0 : r).padStart(2, '0') + '"'; };
  // Allures par défaut recalculées sur ta forme du moment (cockpit2 : tes dernières courses),
  // l'allure « marathon » du club étant celle de ton objectif marathon, pas ton potentiel.
  function modelPaces() {
    try {
      const m = window.__ckFitness && window.__ckFitness(); if (!m) return {};
      const by = {}; m.rows.forEach(r => { by[r.k] = r.pace; });
      return { marathon: fmtP(by.nyc), seuil: fmtP(by.seuil), semi: fmtP(by.semi), '10k': fmtP(by['10k']), '5k': fmtP(by['5k']), vma: fmtP(m.vma) };
    } catch (e) { return {}; }
  }
  function loadPaces() {
    try { return Object.assign({}, DEFAULT_PACES, modelPaces(), JSON.parse(localStorage.getItem(PACES_KEY) || '{}')); } catch (e) { return Object.assign({}, DEFAULT_PACES, modelPaces()); }
  }
  function savePaces(p) { try { localStorage.setItem(PACES_KEY, JSON.stringify(p)); } catch (e) {} }
  const withUnit = (p) => (p ? (/\/km/.test(p) ? p : p + '/km') : '');

  // ---------------------------------------------------------------- lecture d'un texte de coach
  // Format type du club : « 1600M allure MARATHON · 800M allure SEUIL … », puis
  // « RECUP 1'30 PUIS 1'15 PUIS 1' » (une valeur couvre plusieurs blocs).
  const NAMES = { marathon: 'marathon', semi: 'semi', seuil: 'seuil', '10k': '10k', '10 k': '10k', '5k': '5k', '5 k': '5k', vma: 'vma' };
  function parseClubText(raw) {
    if (!raw || !raw.trim()) return null;
    let t = raw.replace(/\r/g, '\n');
    const ex = t.search(/exemple/i);               // les chiffres d'un « exemple » ne sont pas les tiens
    if (ex > 0) t = t.slice(0, ex);
    const segs = t.split(/[·\n+;]+/).map(x => x.trim()).filter(Boolean);
    const blocks = [];
    segs.forEach(sg => {
      const m = sg.match(/(\d{2,4})\s*m?\b[^\d]*?\b(marathon|semi|seuil|10\s?k|5\s?k|vma)\b/i);
      if (m && /allure|à|@|ritme|rythme/i.test(sg)) {
        blocks.push({ dist_m: +m[1], label: NAMES[m[2].toLowerCase().replace(/\s+/g, ' ')] || NAMES[m[2].toLowerCase().replace(/\s+/g, '')] || 'libre', pace: '', rest: '', optional: /option|facultatif/i.test(sg) });
      }
    });
    if (blocks.length < 2) {
      // Repli : « 6x500 r 1'30 @3'20 »
      const m = t.match(/(\d+)\s*[x×]\s*(\d{2,4})\s*m?/i);
      if (m) {
        const pace = (t.match(/[@à]\s*(\d['’:]\d{2})/i) || [])[1] || '';
        const rest = (t.match(/r[ée]cup\w*\s*:?\s*([\d'’":]+\w*)/i) || [])[1] || '';
        for (let i = 0; i < Math.min(+m[1], 30); i++) blocks.push({ dist_m: +m[2], label: 'libre', pace: pace ? pace.replace(':', "'") + '"/km' : '', rest: i < +m[1] - 1 ? rest.replace(/’/g, "'") : '', optional: false });
      }
    } else {
      const rm = t.match(/r[ée]cup\w*\s*:?\s*([^\n·]+)/i);
      if (rm) {
        const vals = rm[1].split(/\bpuis\b|,|\/|;/i).map(x => x.trim().replace(/’/g, "'")).filter(x => /\d/.test(x)).map(x => (x.match(/\d+(?:['’:]\d{2})?'?/) || [''])[0].replace(':', "'"));
        const fixed = blocks.filter(b => !b.optional);
        if (vals.length) {
          fixed.forEach((b, i) => { b.rest = vals[Math.min(Math.floor(i * vals.length / fixed.length), vals.length - 1)]; });
          if (!blocks.some(b => b.optional) && fixed.length) fixed[fixed.length - 1].rest = '';   // rien après le dernier bloc
        }
      }
    }
    if (!blocks.length) return null;
    const warm = (t.match(/(?:[ée]ch\w*|warm\w*)\s*:?\s*(\d+(?:[.,]\d+)?)\s*km/i) || [])[1];
    const cool = (t.match(/(?:retour au calme|rc)\s*:?\s*(\d+(?:[.,]\d+)?)\s*km/i) || [])[1];
    return { title: 'Piste Harbat · ' + blocks.filter(b => !b.optional).map(b => b.dist_m).join('-'),
      warmup_km: warm ? +warm.replace(',', '.') : 0, cooldown_km: cool ? +cool.replace(',', '.') : 0, blocks, notes: '' };
  }

  // ---------------------------------------------------------------- description (miroir du serveur)
  const fmtDist = (m) => (m >= 2000 ? (m / 1000) + 'km' : m + 'm');
  function blockLine(b) {
    let s = fmtDist(b.dist_m); const bits = [];
    if (b.label && b.label !== 'libre') bits.push('allure ' + (LABELS.find(l => l[0] === b.label) || [0, b.label])[1].toLowerCase());
    if (b.pace) bits.push(withUnit(b.pace));
    if (bits.length) s += ' ' + bits.join(' · ');
    if (b.rest) s += ' · récup ' + b.rest;
    if (b.optional) s += ' (en option)';
    return s;
  }
  function describe(st) {
    const lines = [];
    if (st.warmup > 0) lines.push(st.warmup + ' km échauffement');
    let i = 0;
    while (i < st.blocks.length) {
      const b = st.blocks[i]; let j = i;
      while (j + 1 < st.blocks.length && !b.optional && ['dist_m', 'label', 'pace', 'rest', 'optional'].every(k => st.blocks[j + 1][k] === b[k])) j++;
      lines.push((j > i ? (j - i + 1) + '×' : '') + blockLine(b)); i = j + 1;
    }
    if (st.cooldown > 0) lines.push(st.cooldown + ' km retour au calme');
    if (st.notes) lines.push(st.notes);
    return lines;
  }
  const totalKm = (st) => Math.round((st.warmup + st.cooldown + st.blocks.filter(b => !b.optional).reduce((a, b) => a + b.dist_m, 0) / 1000) * 10) / 10;

  // ---------------------------------------------------------------- feuille
  function nextWednesday() {
    const w = allDays().filter(d => parse(d.date).getDay() === 3 && d.date >= TODAY).sort((a, b) => a.date.localeCompare(b.date))[0];
    return w ? w.date : TODAY;
  }
  function resizeToBase64(file) {
    return new Promise((resolve, reject) => {
      const img = new Image(), rd = new FileReader();
      rd.onerror = () => reject(new Error('lecture du fichier impossible'));
      rd.onload = () => {
        img.onerror = () => reject(new Error('image illisible'));
        img.onload = () => {
          const max = 1600; let { width, height } = img;
          if (width > max || height > max) { const r = Math.min(max / width, max / height); width = Math.round(width * r); height = Math.round(height * r); }
          const c = document.createElement('canvas'); c.width = width; c.height = height; c.getContext('2d').drawImage(img, 0, 0, width, height);
          resolve(c.toDataURL('image/jpeg', 0.85).split(',')[1]);
        };
        img.src = rd.result;
      };
      rd.readAsDataURL(file);
    });
  }

  function openClub(isoArg) {
    const iso = (typeof isoArg === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(isoArg)) ? isoArg : nextWednesday();
    const day = findDay(iso);
    const paces = loadPaces();
    const st = { warmup: 2, cooldown: 1.5, title: 'Piste Harbat', notes: '', blocks: [{ dist_m: 1000, label: 'libre', pace: '', rest: "1'30", optional: false }] };
    if (day && day._replaced_by_user && Array.isArray(day.slot_blocks) && day.slot_blocks.length) {
      st.blocks = day.slot_blocks.map(b => Object.assign({}, b)); st.title = day.title || st.title;
    }
    const fillPace = (b) => { if (b.label !== 'libre' && !b.pace) b.pace = withUnit(paces[b.label] || ''); };

    const body = openSheet(`<div class="ck4">
      <span class="ck-sheet-tag" style="--c:var(--ck-red)">${svg('bolt', 14)} Séance du club</span>
      <h3 class="ck-sheet-h">Piste · ${esc(fmtDayLong(iso))}</h3>
      <div class="ck4-in">
        <label class="ck-btn ck4-photo">${svg('sparkle', 16)} Photo<input id="ck4Photo" type="file" accept="image/*" hidden></label>
        <button type="button" class="ck-btn" id="ck4PasteBtn">${svg('layers', 16)} Coller le texte</button>
      </div>
      <div id="ck4Paste" class="ck4-paste" hidden>
        <textarea id="ck4Text" rows="5" placeholder="Colle ici le message du coach (ex. 1600M allure MARATHON · 800M allure SEUIL … RECUP 1'30 PUIS 1'15 PUIS 1')"></textarea>
        <button type="button" class="ck-btn ck-btn-primary ck-btn-sm" id="ck4Read">Lire ce texte</button>
      </div>
      <p class="ck4-fb" id="ck4Fb"></p>
      <label class="ck-field"><span>Titre</span><input id="ck4Title" type="text" maxlength="80"></label>
      <div class="ck4-row2">
        <label class="ck-field"><span>Échauffement (km)</span><input id="ck4Warm" type="number" step="0.1" min="0" inputmode="decimal"></label>
        <label class="ck-field"><span>Retour au calme (km)</span><input id="ck4Cool" type="number" step="0.1" min="0" inputmode="decimal"></label>
      </div>
      <div class="ck4-hint">L'échauffement peut inclure l'aller en footing jusqu'à la piste.</div>
      <div class="ck-sheet-sec"><h4>Les blocs, dans l'ordre</h4><div id="ck4Blocks" class="ck4-blocks"></div>
        <button type="button" class="ck-btn ck-btn-sm" id="ck4Add">+ Ajouter un bloc</button></div>
      <label class="ck-field"><span>Notes (facultatif)</span><input id="ck4Notes" type="text" maxlength="300" placeholder="ex. : au Bois de Boulogne, piste fermée"></label>
      <details class="ck4-paces"><summary>Mes allures de référence</summary>
        <p class="ck-muted">Calculées d'après ta forme du moment (ton dernier 20 km). « Marathon » = l'allure de ton objectif. Modifie-les, elles sont gardées sur cet appareil.</p>
        <div class="ck4-pgrid" id="ck4Pg"></div></details>
      <div id="ck4Prev" class="ck4-prev"></div>
      <div class="ck-actions"><button type="button" class="ck-btn ck-btn-primary" id="ck4Send">Envoyer au plan</button><button type="button" class="ck-btn" id="ck4Cancel">Annuler</button></div>
    </div>`);

    const el = (id) => $('#' + id, body);
    const fb = (msg, kind) => { el('ck4Fb').textContent = msg || ''; el('ck4Fb').dataset.kind = kind || ''; };
    function sync() { st.title = el('ck4Title').value; st.warmup = parseFloat(el('ck4Warm').value) || 0; st.cooldown = parseFloat(el('ck4Cool').value) || 0; st.notes = el('ck4Notes').value.trim(); }
    function renderBlocks() {
      el('ck4Blocks').innerHTML = st.blocks.map((b, i) => `<div class="ck4-blk${b.optional ? ' is-opt' : ''}" data-i="${i}">
        <div class="ck4-blk-n">${i + 1}</div>
        <div class="ck4-blk-f">
          <div class="ck4-l1">
            <label><span>Distance (m)</span><input data-f="dist_m" type="number" min="50" max="6000" step="50" inputmode="numeric" value="${b.dist_m}"></label>
            <label><span>Allure</span><select data-f="label">${LABELS.map(l => `<option value="${l[0]}"${b.label === l[0] ? ' selected' : ''}>${l[1]}</option>`).join('')}</select></label>
          </div>
          <div class="ck4-l2">
            <label><span>Allure chiffrée</span><input data-f="pace" type="text" value="${esc(b.pace)}" placeholder="3'41&quot;/km"></label>
            <label><span>Récup</span><input data-f="rest" type="text" value="${esc(b.rest)}" placeholder="1'30"></label>
            <label class="ck4-chk"><input data-f="optional" type="checkbox"${b.optional ? ' checked' : ''}><span>option</span></label>
          </div>
        </div>
        <button type="button" class="ck4-del" data-del="${i}" aria-label="Supprimer le bloc ${i + 1}">✕</button></div>`).join('');
    }
    function preview() {
      sync();
      const lines = describe(st), tk = totalKm(st);
      el('ck4Prev').innerHTML = `<div class="ck4-prev-h"><b>${tk} km</b><span>${st.blocks.filter(b => !b.optional).length} blocs${st.blocks.some(b => b.optional) ? ' + option' : ''}</span></div>
        <div class="ck4-prev-l">${lines.map(l => `<div>${esc(l)}</div>`).join('') || '<i>Ajoute au moins un bloc.</i>'}</div>`;
    }
    function fillFields() { el('ck4Title').value = st.title; el('ck4Warm').value = st.warmup; el('ck4Cool').value = st.cooldown; el('ck4Notes').value = st.notes; }
    function renderPaces() {
      el('ck4Pg').innerHTML = LABELS.filter(l => l[0] !== 'libre').map(l => `<label><span>${l[1]}</span><input data-pk="${l[0]}" type="text" value="${esc(paces[l[0]] || '')}"></label>`).join('');
    }
    function apply(read) {
      if (!read) return;
      st.title = read.title || st.title; st.warmup = read.warmup_km || st.warmup; st.cooldown = read.cooldown_km || st.cooldown; st.notes = read.notes || '';
      st.blocks = read.blocks.map(b => { const nb = { dist_m: b.dist_m, label: b.label || 'libre', pace: b.pace || '', rest: b.rest || '', optional: !!b.optional }; fillPace(nb); return nb; });
      fillFields(); renderBlocks(); preview();
    }
    st.blocks.forEach(fillPace);
    fillFields(); renderBlocks(); renderPaces(); preview();

    // saisie
    body.addEventListener('input', (e) => {
      const f = e.target.dataset.f, pk = e.target.dataset.pk;
      if (pk) { paces[pk] = e.target.value.trim(); savePaces(paces); return; }
      if (f) {
        const i = +e.target.closest('.ck4-blk').dataset.i, b = st.blocks[i];
        if (f === 'dist_m') b.dist_m = parseInt(e.target.value, 10) || 0;
        else if (f === 'optional') b.optional = e.target.checked;
        else if (f === 'label') { b.label = e.target.value; b.pace = ''; fillPace(b); const pi = e.target.closest('.ck4-blk').querySelector('[data-f="pace"]'); if (pi) pi.value = b.pace; }
        else b[f] = e.target.value;
        e.target.closest('.ck4-blk').classList.toggle('is-opt', !!b.optional);
      }
      preview();
    });
    body.addEventListener('click', (e) => {
      const d = e.target.closest('[data-del]');
      if (d) { st.blocks.splice(+d.dataset.del, 1); renderBlocks(); preview(); }
    });
    el('ck4Add').onclick = () => { sync(); const l = st.blocks[st.blocks.length - 1]; st.blocks.push(l ? Object.assign({}, l, { optional: false }) : { dist_m: 1000, label: 'libre', pace: '', rest: '', optional: false }); renderBlocks(); preview(); };
    el('ck4PasteBtn').onclick = () => { const p = el('ck4Paste'); p.hidden = !p.hidden; if (!p.hidden) el('ck4Text').focus(); };
    el('ck4Read').onclick = () => {
      const r = parseClubText(el('ck4Text').value);
      if (!r) { fb('Je ne reconnais pas la séance dans ce texte : saisis les blocs à la main.', 'err'); return; }
      apply(r); el('ck4Paste').hidden = true; fb(`✓ ${r.blocks.length} blocs lus. Vérifie chaque ligne avant d'envoyer.`, 'ok');
    };
    el('ck4Photo').onchange = async () => {
      const file = el('ck4Photo').files && el('ck4Photo').files[0]; if (!file) return;
      const c = cfg(); if (!c) { askConfig(() => openClub(iso)); return; }
      fb('Lecture de la photo…', 'load');
      try {
        const b64 = await resizeToBase64(file);
        const r = await fetch(c.base + '/slot-ocr', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_base64: b64, media_type: 'image/jpeg', token: c.token }) });
        if (r.status === 401) { try { localStorage.removeItem(K.TOKEN_KEY); } catch (e) {} throw new Error('jeton refusé : il te sera redemandé'); }
        if (!r.ok) { let m = 'HTTP ' + r.status; try { const j = await r.json(); if (j.error) m = j.error; } catch (e) {} throw new Error(m); }
        const data = await r.json(), f = data.fields || {};
        if (!Array.isArray(f.blocks) || !f.blocks.length) throw new Error('aucun bloc lu : colle le texte ou saisis à la main');
        apply({ title: f.title, warmup_km: f.warmup_km, cooldown_km: f.cooldown_km, notes: f.notes, blocks: f.blocks });
        fb(data.confidence === 'basse' ? '⚠ Lecture incertaine : relis chaque bloc avant d\'envoyer.' : `✓ ${f.blocks.length} blocs lus depuis la photo. Vérifie avant d'envoyer.`, data.confidence === 'basse' ? 'warn' : 'ok');
      } catch (e) { fb('✗ ' + (e && e.message ? e.message : 'lecture échouée') + '. Tu peux coller le texte ou saisir à la main.', 'err'); }
      finally { el('ck4Photo').value = ''; }
    };
    el('ck4Cancel').onclick = closeSheet;
    el('ck4Send').onclick = async () => {
      sync();
      const blocks = st.blocks.filter(b => b.dist_m >= 50);
      if (!blocks.length) { fb('Ajoute au moins un bloc.', 'err'); return; }
      const c = cfg(); if (!c) { askConfig(() => openClub(iso)); return; }
      el('ck4Send').disabled = true; fb('envoi…', 'load');
      try {
        const r = await fetch(c.base + '/slot', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ date: iso, title: st.title || 'Piste Harbat', warmup_km: st.warmup, cooldown_km: st.cooldown, blocks, notes: st.notes, token: c.token }) });
        if (r.status === 401) { try { localStorage.removeItem(K.TOKEN_KEY); } catch (e) {} throw new Error('jeton refusé : il te sera redemandé'); }
        if (!r.ok) { let m = 'HTTP ' + r.status; try { const j = await r.json(); if (j.error) m = j.error; } catch (e) {} throw new Error(m); }
        fb('✓ Envoyée : le plan se met à jour dans environ 2 min.', 'ok');
        toast('Séance du club envoyée au plan.');
        setTimeout(closeSheet, 1200);
      } catch (e) { fb('✗ ' + (e && e.message ? e.message : 'échec'), 'err'); el('ck4Send').disabled = false; }
    };
  }

  function mount() { window.openSlotModal = openClub; window.__ck4 = { parseClubText, describe, totalKm }; }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(mount, 60));
  else setTimeout(mount, 60);
})();
