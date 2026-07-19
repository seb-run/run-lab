/* ============================================================================
   seb-metrics — app.js
   Logique frontend : chargement données inline, charts ECharts, navigation.
   ============================================================================ */

(function() {
  'use strict';

  // ===== 1. DONNÉES =========================================================
  const RAW = JSON.parse(document.getElementById('seb-data').textContent);
  const SESSIONS = RAW.sessions || [];
  const PROFILE  = RAW.profile  || {};
  const OVERVIEW = RAW.overview || {};
  const PERF     = RAW.performance || { now: {}, past: {}, delta: { paces: {} } };
  const RACES    = RAW.races || { distances: [], past_races: [], goals: [], countdowns: [], tapers: [] };
  const PLAN     = RAW.plan || null;

  // Palette thème (lue depuis les variables CSS → suit le mode clair/sombre)
  const CSSV = (name, fallback) =>
    (getComputedStyle(document.documentElement).getPropertyValue(name) || '').trim() || fallback;
  const INK  = CSSV('--text', '#0f172a');
  const INK2 = CSSV('--text-2', '#475569');

  // Conversion des dates en objets Date pour filtrage
  function parseDate(s) {
    const p = s.split('/');
    return new Date(+p[2], +p[1] - 1, +p[0]);
  }
  SESSIONS.forEach(s => { s._date = parseDate(s.d); s._year = s._date.getFullYear(); });

  // Clé canonique pour identifier une séance (stable à travers re-parses)
  // Format : YYYY-MM-DDTHH:MM en local
  function sessionKey(sess) {
    const p = sess.d.split('/');
    return `${p[2]}-${p[1]}-${p[0]}T${sess.h || '00:00'}`;
  }

  // ===== 2. UTILS ===========================================================
  function fmtPace(secPerKm) {
    if (!secPerKm || !isFinite(secPerKm)) return '—';
    const m = Math.floor(secPerKm / 60);
    const s = Math.round(secPerKm % 60);
    return m + "'" + String(s).padStart(2, '0') + '"';
  }

  function fmtDur(sec) {
    if (!sec) return '—';
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return h > 0 ? h + 'h ' + String(m).padStart(2, '0') : m + ' min';
  }

  // Format chrono compact "2h50'13" pour les temps de course
  function fmtChrono(sec) {
    if (!sec || sec <= 0) return '—';
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.round(sec % 60);
    if (h > 0) return `${h}h${String(m).padStart(2, '0')}'${String(s).padStart(2, '0')}"`;
    return `${m}'${String(s).padStart(2, '0')}"`;
  }

  function fmtMonth(moStr) {
    const months = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc'];
    const [y, m] = moStr.split('-');
    return months[+m - 1] + ' ' + y.slice(2);
  }

  function fmtWeek(wkStr) {
    return 'S' + wkStr.split('W')[1];
  }

  // Format "12 avril 2026" depuis "DD/MM/YYYY"
  function fmtDateLong(ddmmyyyy) {
    if (!ddmmyyyy) return '';
    const months = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
    const p = ddmmyyyy.split('/');
    if (p.length !== 3) return ddmmyyyy;
    return `${parseInt(p[0], 10)} ${months[parseInt(p[1], 10) - 1]} ${p[2]}`;
  }

  function computeAge(birthStr) {
    if (!birthStr) return null;
    let b;
    if (birthStr.includes('/')) {
      const parts = birthStr.split('/');
      if (parts.length !== 3) return null;
      const day   = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10) - 1;
      const year  = parseInt(parts[2], 10);
      b = new Date(year, month, day);
    } else {
      b = new Date(birthStr);
    }
    if (isNaN(b.getTime())) return null;
    const now = new Date();
    let age = now.getFullYear() - b.getFullYear();
    if (now < new Date(now.getFullYear(), b.getMonth(), b.getDate())) age--;
    return age;
  }

  // Échappement HTML basique pour les saisies utilisateur
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ===== 3. ÉTAT FILTRES ====================================================
  let currentYear = 'all';
  function getFilteredSessions() {
    if (currentYear === 'all') return SESSIONS;
    return SESSIONS.filter(s => s._year === +currentYear);
  }

  // ===== 4. HERO ============================================================
  function renderHero() {
    const age = computeAge(PROFILE.birthdate);
    document.getElementById('dynAge').textContent = age ? age + ' ans' : '';
    document.getElementById('genDate').textContent =
      new Date(RAW.generated_at).toLocaleString('fr-FR', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      });

    const counters = [
      { v: OVERVIEW.total_sessions, l: 'séances' },
      { v: (OVERVIEW.total_km || 0).toLocaleString('fr-FR'), l: 'km' },
    ];
    document.getElementById('heroCounters').innerHTML = counters.map(c =>
      `<div class="hero-counter"><div class="v">${c.v}</div><div class="l">${c.l}</div></div>`
    ).join('');

    renderHeroPaces();
  }

  function fmtTrend(deltaSec, key) {
    if (deltaSec === null || deltaSec === undefined) {
      return { html: '—', cls: 'none' };
    }
    if (Math.abs(deltaSec) < 1) {
      return {
        html: `<svg viewBox="0 0 12 12" fill="none"><path d="M2 6 L10 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg> stable`,
        cls: 'stable'
      };
    }
    const progressing = deltaSec < 0;
    const arrow = progressing
      ? `<svg viewBox="0 0 12 12" fill="none"><path d="M2 4 L6 8 L10 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`
      : `<svg viewBox="0 0 12 12" fill="none"><path d="M2 8 L6 4 L10 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    const sign = progressing ? '−' : '+';
    const sec = Math.abs(Math.round(deltaSec));
    return {
      html: `${arrow} ${sign}${sec}"`,
      cls: progressing ? 'up' : 'down'
    };
  }

  function fmtTrendVmaKmh(deltaKmh) {
    if (deltaKmh === null || deltaKmh === undefined) {
      return { html: '—', cls: 'none' };
    }
    if (Math.abs(deltaKmh) < 0.05) {
      return {
        html: `<svg viewBox="0 0 12 12" fill="none"><path d="M2 6 L10 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg> stable`,
        cls: 'stable'
      };
    }
    const progressing = deltaKmh > 0;
    const arrow = progressing
      ? `<svg viewBox="0 0 12 12" fill="none"><path d="M2 8 L6 4 L10 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`
      : `<svg viewBox="0 0 12 12" fill="none"><path d="M2 4 L6 8 L10 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    const sign = progressing ? '+' : '−';
    return {
      html: `${arrow} ${sign}${Math.abs(deltaKmh).toFixed(1)}`,
      cls: progressing ? 'up' : 'down'
    };
  }

  function renderHeroPaces() {
    const now = PERF.now || {};
    const paces = now.paces || {};
    const delta = (PERF.delta && PERF.delta.paces) || {};
    const deltaVma = PERF.delta && PERF.delta.vma;
    const reliable = PERF.delta && PERF.delta.reliable !== false;
    const reason = PERF.delta && PERF.delta.reason;

    function unreliableTrend() {
      const tooltipText = reason === 'low_vma_density'
        ? "Comparaison non fiable : peu de seances VMA pures sur la periode precedente (cycle marathon ou affutage)"
        : reason === 'no_data'
        ? "Pas assez de donnees il y a 30 jours pour calculer une tendance"
        : "Comparaison non fiable";
      return { html: `—`, cls: 'none', tip: tooltipText };
    }

    const vmaKmh = now.vma;
    const vmaCard = vmaKmh
      ? {
          c: 'vma', l: 'VMA',
          v: vmaKmh.toFixed(1), u: 'km/h',
          trend: reliable ? fmtTrendVmaKmh(deltaVma) : unreliableTrend(),
        }
      : {
          c: 'vma', l: 'VMA',
          v: '—', u: 'km/h',
          trend: { html: '—', cls: 'none' },
        };

    const buildPace = (key, label, color) => {
      const ps = paces[key];
      const d = delta[key];
      return {
        c: color, l: label,
        v: ps ? fmtPace(ps) : '—',
        u: '/km',
        trend: reliable ? fmtTrend(d, key) : unreliableTrend(),
      };
    };

    const cards = [
      vmaCard,
      buildPace('10k',      '10K',      '10k'),
      buildPace('seuil',    'Seuil',    'seuil'),
      buildPace('semi',     'Semi',     'semi'),
      buildPace('marathon', 'Marathon', 'marathon'),
    ];

    document.getElementById('heroPaces').innerHTML = cards.map(card => {
      const tipAttr = card.trend.tip ? ` title="${card.trend.tip.replace(/"/g, '&quot;')}"` : '';
      return `<div class="pace-card" data-c="${card.c}"${tipAttr}>
        <div class="pl">${card.l}</div>
        <div class="pv">${card.v}</div>
        <div class="pu">${card.u}</div>
        <div class="pt ${card.trend.cls}">${card.trend.html}</div>
      </div>`;
    }).join('');

    const headSubEl = document.querySelector('.hero-paces-sub');
    if (headSubEl) {
      if (!reliable && reason === 'low_vma_density') {
        headSubEl.innerHTML = `Tendance vs 30j · <span style="color:#94a3b8" title="Période précédente sans séance VMA pure (cycle marathon)">⏸ comparaison masquée</span>`;
      } else if (!reliable && reason === 'no_data') {
        headSubEl.innerHTML = 'Tendance vs 30j · données insuffisantes';
      } else {
        headSubEl.textContent = 'Tendance vs 30j';
      }
    }
  }

  // ===== 5. KPIs VUE D'ENSEMBLE ============================================
  //
  // Note duplicabilité : tous les agrégats ci-dessous sont calculés à la
  // volée depuis SESSIONS, sans constante personnelle ni seuil hardcodé.
  // Une nouvelle personne utilisant le dashboard aura les mêmes calculs sur
  // ses propres données, sans modification du code nécessaire.

  // Calcule l'ensemble des agrégats Vue d'ensemble depuis une liste de
  // sessions filtrées. Retourne {total_sessions, total_km, last_session,
  // weekly_volume, monthly_pace, monthly_hr}. Cette fonction reproduit
  // côté JS ce que `modules/builder.compute_overview` fait côté Python,
  // pour permettre un filtrage dynamique sans rebuild.
  function computeOverviewFromSessions(sessions) {
    if (!sessions.length) {
      return {
        total_sessions: 0,
        total_km: 0,
        last_session: null,
        weekly_volume: [],
        monthly_pace: [],
        monthly_hr: [],
      };
    }

    let totalKm = 0;
    const weeklyMap = new Map();   // ISOweek (year-Wxx) → km
    const monthlyPaceMap = new Map(); // YYYY-MM → [{ps, weight}]
    const monthlyHrMap = new Map();   // YYYY-MM → [fc]

    sessions.forEach(s => {
      totalKm += s.km || 0;
      if (!s._date) return;

      // ISO week (lundi début, comme Python isocalendar)
      const isoWk = isoWeekKey(s._date);
      weeklyMap.set(isoWk, (weeklyMap.get(isoWk) || 0) + (s.km || 0));

      const yr = s._date.getFullYear();
      const mo = String(s._date.getMonth() + 1).padStart(2, '0');
      const moKey = `${yr}-${mo}`;

      if (s.ps && s.km) {
        if (!monthlyPaceMap.has(moKey)) monthlyPaceMap.set(moKey, []);
        monthlyPaceMap.get(moKey).push({ ps: s.ps, weight: s.km });
      }
      if (s.fc) {
        if (!monthlyHrMap.has(moKey)) monthlyHrMap.set(moKey, []);
        monthlyHrMap.get(moKey).push(s.fc);
      }
    });

    // weekly_volume : 52 dernières semaines (tri chrono)
    const weekly_volume = Array.from(weeklyMap.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-52)
      .map(([wk, km]) => ({ wk, km: Math.round(km * 10) / 10 }));

    // monthly_pace : 24 derniers mois, allure pondérée par distance
    const monthly_pace = Array.from(monthlyPaceMap.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-24)
      .map(([mo, items]) => {
        const totW = items.reduce((a, x) => a + x.weight, 0);
        const avg = items.reduce((a, x) => a + x.ps * x.weight, 0) / totW;
        return { mo, pace: Math.round(avg) };
      });

    // monthly_hr : 24 derniers mois, FC moyenne simple
    const monthly_hr = Array.from(monthlyHrMap.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-24)
      .map(([mo, items]) => {
        const avg = items.reduce((a, x) => a + x, 0) / items.length;
        return { mo, hr: Math.round(avg) };
      });

    // Dernière séance = la plus récente
    let last = sessions[0];
    sessions.forEach(s => {
      if (s._date > last._date) last = s;
    });

    return {
      total_sessions: sessions.length,
      total_km: Math.round(totalKm * 10) / 10,
      last_session: lastSessionFmt(last),
      weekly_volume,
      monthly_pace,
      monthly_hr,
    };
  }

  // ISO week key équivalent à Python isocalendar : retourne "YYYY-Www"
  // basé sur la semaine ISO 8601 (lundi = début, semaine contenant le 4 jan = W1).
  function isoWeekKey(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7; // dim → 7
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNum = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return `${d.getUTCFullYear()}-W${String(weekNum).padStart(2, '0')}`;
  }

  // Formate une session pour le rendu "Dernière séance" (réplique de la
  // structure last_session attendue par renderLastSession).
  function lastSessionFmt(s) {
    if (!s) return null;
    return {
      d: s.d, h: s.h, tp: s.tp, km: s.km, dur: s.dur,
      a: s.a, fc: s.fc,
    };
  }

  function renderOverviewKPIs() {
    const sess = getFilteredSessions();
    if (!sess.length) {
      document.getElementById('ovKPIs').innerHTML =
        '<div class="card placeholder">Aucune séance pour cette période.</div>';
      return;
    }

    const totalKm = sess.reduce((a, s) => a + s.km, 0);
    const totalSec = sess.reduce((a, s) => a + (s.dur_s || 0), 0);
    const paces = sess.filter(s => s.ps);
    const avgPaceSec = paces.length
      ? paces.reduce((a, s) => a + s.ps * s.km, 0) / paces.reduce((a, s) => a + s.km, 0)
      : 0;
    const hrs = sess.filter(s => s.fc);
    const avgHr = hrs.length ? hrs.reduce((a, s) => a + s.fc, 0) / hrs.length : 0;

    const kpis = [
      { v: sess.length,            l: 'Séances',     c: 'blue'   },
      { v: totalKm.toFixed(0) + ' km', l: 'Distance', c: 'cyan'   },
      { v: fmtDur(totalSec),       l: 'Temps total', c: 'orange' },
      { v: fmtPace(avgPaceSec) + '/km', l: 'Allure moyenne', c: 'purple' },
    ];

    document.getElementById('ovKPIs').innerHTML = kpis.map(k =>
      `<div class="kpi" data-c="${k.c}">
        <div class="label">${k.l}</div>
        <div class="value">${k.v}</div>
        ${avgHr && k.l === 'Allure moyenne' ? `<div class="sub">FC moy. ${Math.round(avgHr)} bpm</div>` : ''}
      </div>`
    ).join('');
  }

  // Met à jour les compteurs du hero (séances / km) en fonction du filtre
  // courant. Les allures de forme restent calées sur la fenêtre 30j et ne
  // changent pas avec le filtre.
  function refreshHeroCounters() {
    const sess = getFilteredSessions();
    const totalKm = sess.reduce((a, s) => a + (s.km || 0), 0);
    const counters = [
      { v: sess.length, l: 'séances' },
      { v: Math.round(totalKm).toLocaleString('fr-FR'), l: 'km' },
    ];
    const el = document.getElementById('heroCounters');
    if (el) {
      el.innerHTML = counters.map(c =>
        `<div class="hero-counter"><div class="v">${c.v}</div><div class="l">${c.l}</div></div>`
      ).join('');
    }
  }

  // ===== 6. CHARTS ECHARTS ==================================================
  const CHART_THEME = {
    color: ['#5b8af5', '#22d3a7', '#f0923e', '#9b6dff'],
    textStyle: { fontFamily: 'Inter, system-ui, sans-serif', color: INK2 },
    grid: { left: 40, right: 16, top: 16, bottom: 32, containLabel: true },
    xAxis: {
      axisLine: { lineStyle: { color: 'rgba(15, 23, 42, 0.12)' } },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(15, 23, 42, 0.06)' } },
    },
    tooltip: {
      backgroundColor: 'rgba(255, 255, 255, 0.96)',
      borderColor: 'rgba(15, 23, 42, 0.08)',
      borderWidth: 1,
      textStyle: { color: INK, fontSize: 12 },
      extraCssText: 'box-shadow: 0 4px 16px rgba(15,23,42,0.08); border-radius: 10px; padding: 8px 12px;',
    },
  };

  const charts = {};

  function chartWeekly(weeklyData) {
    const el = document.getElementById('chartWeekly');
    if (!el) return;
    const data = weeklyData || OVERVIEW.weekly_volume || [];
    // Dispose l'ancienne instance si présente (sinon ECharts plante au re-init)
    if (charts.weekly) {
      charts.weekly.dispose();
      charts.weekly = null;
    }
    if (!data.length) {
      el.innerHTML = '<p style="color:#94a3b8;padding:20px;text-align:center">Aucune donnée pour cette période.</p>';
      return;
    }
    const dom = charts.weekly = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      xAxis: { ...CHART_THEME.xAxis, type: 'category',
               data: data.map(d => fmtWeek(d.wk)),
               axisLabel: { ...CHART_THEME.xAxis.axisLabel,
                            interval: Math.max(0, Math.floor(data.length / 8) - 1) } },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', name: 'km',
               nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
      tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                 formatter: p => `<b>${p[0].axisValue}</b><br/>${p[0].data.toFixed(1)} km` },
      series: [{
        type: 'bar',
        data: data.map(d => d.km),
        itemStyle: {
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                   colorStops: [{ offset: 0, color: '#5b8af5' }, { offset: 1, color: '#22d3a7' }] },
          borderRadius: [4, 4, 0, 0],
        },
        emphasis: { itemStyle: { opacity: 0.85 } },
        animationDuration: 800,
        animationEasing: 'cubicOut',
      }],
    });
  }

  function chartMonthlyPace(monthlyData) {
    const el = document.getElementById('chartMonthlyPace');
    if (!el) return;
    const data = monthlyData || OVERVIEW.monthly_pace || [];
    if (charts.pace) {
      charts.pace.dispose();
      charts.pace = null;
    }
    if (!data.length) {
      el.innerHTML = '<p style="color:#94a3b8;padding:20px;text-align:center">Aucune donnée pour cette période.</p>';
      return;
    }
    const dom = charts.pace = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      xAxis: { ...CHART_THEME.xAxis, type: 'category', data: data.map(d => fmtMonth(d.mo)) },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', inverse: true,
               name: "sec/km", nameTextStyle: { color: '#94a3b8', fontSize: 10 },
               axisLabel: { ...CHART_THEME.yAxis.axisLabel,
                            formatter: v => Math.floor(v/60) + "'" + String(Math.round(v%60)).padStart(2,'0') } },
      tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                 formatter: p => `<b>${p[0].axisValue}</b><br/>${fmtPace(p[0].data)}/km` },
      series: [{
        type: 'line', smooth: true,
        data: data.map(d => d.pace),
        symbol: 'circle', symbolSize: 7,
        lineStyle: { width: 3, color: '#5b8af5' },
        itemStyle: { color: '#5b8af5', borderColor: '#fff', borderWidth: 2 },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                              colorStops: [{ offset: 0, color: 'rgba(91,138,245,0.25)' },
                                           { offset: 1, color: 'rgba(91,138,245,0)' }] } },
        animationDuration: 1000,
      }],
    });
  }

  function chartMonthlyHR(monthlyData) {
    const el = document.getElementById('chartMonthlyHR');
    if (!el) return;
    const data = monthlyData || OVERVIEW.monthly_hr || [];
    if (charts.hr) {
      charts.hr.dispose();
      charts.hr = null;
    }
    if (!data.length) {
      el.innerHTML = '<p style="color:#94a3b8;padding:20px;text-align:center">Aucune donnée pour cette période.</p>';
      return;
    }
    const dom = charts.hr = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      xAxis: { ...CHART_THEME.xAxis, type: 'category', data: data.map(d => fmtMonth(d.mo)) },
      yAxis: { ...CHART_THEME.yAxis, type: 'value',
               name: 'bpm', nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
      tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                 formatter: p => `<b>${p[0].axisValue}</b><br/>${p[0].data} bpm` },
      series: [{
        type: 'line', smooth: true,
        data: data.map(d => d.hr),
        symbol: 'circle', symbolSize: 7,
        lineStyle: { width: 3, color: '#f0923e' },
        itemStyle: { color: '#f0923e', borderColor: '#fff', borderWidth: 2 },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                              colorStops: [{ offset: 0, color: 'rgba(240,146,62,0.22)' },
                                           { offset: 1, color: 'rgba(240,146,62,0)' }] } },
        animationDuration: 1000,
      }],
    });
  }

  // ===== 7. DERNIÈRE SÉANCE =================================================
  function renderLastSession(lastSession) {
    const last = lastSession !== undefined ? lastSession : OVERVIEW.last_session;
    const box = document.getElementById('lastSession');
    if (!last) {
      box.innerHTML = '<p style="color:var(--text-3)">Aucune séance disponible.</p>';
      return;
    }
    const TL = {
      footing: 'Footing', endurance: 'Endurance', tempo: 'Tempo',
      fractionne: 'Fractionné', frac_court: 'Frac. court', frac_long: 'Frac. long',
      sortie_longue: 'Sortie longue', marathon: 'Marathon', semi: 'Semi'
    };
    const rows = [
      ['Date',   last.d + ' à ' + last.h],
      ['Type',   `<span class="tag tag-${last.tp}">${TL[last.tp] || last.tp}</span>`],
      ['Distance', last.km + ' km'],
      ['Durée',  last.dur],
      ['Allure', last.a || '—'],
      ['FC',     last.fc ? last.fc + ' bpm' : '—'],
    ];
    box.innerHTML = rows.map(([l, v]) =>
      `<div class="last-session-row"><span class="l">${l}</span><span class="v">${v}</span></div>`
    ).join('');
  }

  // ===== 8. NAVIGATION ======================================================
  function activateTab(name) {
    const target = document.getElementById('t-' + name);
    if (!target) return;
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('on'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('on'));
    target.classList.add('on');
    const btn = document.querySelector(`.tab[data-tab="${name}"]`);
    if (btn) btn.classList.add('on');
    else document.getElementById('tabMoreBtn')?.classList.add('on');
    resizeAllCharts();
    window.scrollTo({top: 0});
  }

  function resizeAllCharts() {
        // Resize tous les charts maintenant que l'onglet est visible.
        // ECharts a besoin d'un resize quand on passe d'un display:none à
        // un display:block (le chart calcule son layout sur 0×0 sinon).
        setTimeout(() => {
          Object.values(charts).forEach(c => c && c.resize());
          if (typeof volCharts !== 'undefined') {
            Object.values(volCharts).forEach(c => c && c.resize());
          }
          if (typeof aeroCharts !== 'undefined') {
            Object.values(aeroCharts).forEach(c => c && c.resize());
          }
          if (typeof progCharts !== 'undefined') {
            Object.values(progCharts).forEach(c => c && c.resize());
          }
          if (typeof chargeCharts !== 'undefined') {
            Object.values(chargeCharts).forEach(c => c && c.resize());
          }
          if (typeof compCharts !== 'undefined') {
            Object.values(compCharts).forEach(c => c && c.resize());
          }
          if (typeof chartsExtra !== 'undefined') {
            Object.values(chartsExtra).forEach(c => c && c.resize());
          }
        }, 50);
  }

  function setupTabs() {
    document.querySelectorAll('.tab[data-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        closeMoreMenu();
        activateTab(btn.dataset.tab);
      });
    });

    // Menu « Plus »
    const moreBtn = document.getElementById('tabMoreBtn');
    const moreMenu = document.getElementById('moreMenu');
    if (moreBtn && moreMenu) {
      moreBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        moreMenu.hidden = !moreMenu.hidden;
      });
      moreMenu.querySelectorAll('.more-item[data-tab]').forEach(item => {
        item.addEventListener('click', () => {
          closeMoreMenu();
          activateTab(item.dataset.tab);
        });
      });
      document.addEventListener('click', (e) => {
        if (!moreMenu.hidden && !moreMenu.contains(e.target)) closeMoreMenu();
      });
    }

    // Bascule thème clair/sombre
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
      const isDark = () => document.documentElement.dataset.theme === 'dark';
      const syncLabel = () => { themeBtn.textContent = isDark() ? '☀️ Mode clair' : '🌙 Mode sombre'; };
      syncLabel();
      themeBtn.addEventListener('click', () => {
        localStorage.setItem('seb-theme', isDark() ? 'light' : 'dark');
        location.reload();  // recharge pour ré-initialiser les charts avec la bonne palette
      });
    }
  }

  function closeMoreMenu() {
    const m = document.getElementById('moreMenu');
    if (m) m.hidden = true;
  }

  // Rafraîchit l'intégralité de l'onglet Vue d'ensemble et le hero
  // depuis les sessions filtrées par l'année courante.
  function refreshOverviewTab() {
    const filtered = getFilteredSessions();
    const ov = computeOverviewFromSessions(filtered);

    refreshHeroCounters();
    renderOverviewKPIs();
    chartWeekly(ov.weekly_volume);
    chartMonthlyPace(ov.monthly_pace);
    chartMonthlyHR(ov.monthly_hr);
    renderLastSession(ov.last_session);

    // L'onglet Volume dépend aussi du filtre année (sauf le cumul annuel
    // qui compare toujours toutes les années, mais c'est géré dedans).
    if (typeof renderVolumeTab === 'function') renderVolumeTab();
  }

  function setupYearFilter() {
    document.querySelectorAll('.year-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.year-btn').forEach(b => b.classList.remove('on'));
        btn.classList.add('on');
        currentYear = btn.dataset.y;
        refreshOverviewTab();
        // Reset à page 1 et re-rendu de la table séances pour refléter le filtre année
        if (typeof renderSessTable === 'function') {
          sessState.page = 1;
          renderSessTypeFilter();
          renderSessTable();
        }
        // Efficacité aérobie suit aussi le filtre
        if (typeof renderAeroTab === 'function') renderAeroTab();
        // Progression VMA NE suit PAS le filtre (analyse longue durée)
      });
    });
  }

  // ===== 9. RESIZE ==========================================================
  window.addEventListener('resize', () => {
    Object.values(charts).forEach(c => c && c.resize());
    if (typeof volCharts !== 'undefined') {
      Object.values(volCharts).forEach(c => c && c.resize());
    }
    if (typeof aeroCharts !== 'undefined') {
      Object.values(aeroCharts).forEach(c => c && c.resize());
    }
    if (typeof progCharts !== 'undefined') {
      Object.values(progCharts).forEach(c => c && c.resize());
    }
    if (typeof chargeCharts !== 'undefined') {
      Object.values(chargeCharts).forEach(c => c && c.resize());
    }
    if (typeof compCharts !== 'undefined') {
      Object.values(compCharts).forEach(c => c && c.resize());
    }
    if (typeof chartsExtra !== 'undefined') {
      Object.values(chartsExtra).forEach(c => c && c.resize());
    }
  });

  // ============================================================================
  // ===== 10. MODULE COURSES & RECORDS =========================================
  // ============================================================================
  // Architecture :
  //   - Source unique des courses = config.past_races[] (côté Python) UNION
  //     localStorage['seb_metrics_races'] (côté navigateur).
  //   - Déduplication par `start_time` (ISO local minute).
  //   - Records calculés à la volée depuis l'union, filtrés par distance_key
  //     et plages min/max_km issues de RACES.distances.
  //   - Pas de modification de la config Python depuis l'UI : tout ajout côté
  //     dashboard reste local (localStorage). Seb peut promouvoir une course
  //     en config s'il veut la rendre permanente pour tous ses futurs builds.

  const STORAGE_KEY = 'seb_metrics_races';

  function loadLocalRaces() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      console.warn('Impossible de lire seb_metrics_races:', e);
      return [];
    }
  }

  function saveLocalRaces(races) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(races));
    } catch (e) {
      alert('Impossible de sauvegarder (localStorage indisponible ou plein).');
    }
  }

  function findSessionByKey(key) {
    return SESSIONS.find(s => sessionKey(s) === key);
  }

  // Détermine le distance_key d'une course depuis sa distance km
  function classifyDistance(km) {
    for (const d of RACES.distances) {
      if (km >= d.min_km && km <= d.max_km) return d.key;
    }
    return null;
  }

  // Union (past_races config + localStorage), déduplication par start_time
  // Enrichit chaque entrée avec les données de la séance correspondante
  function getAllRaces() {
    const fromConfig = (RACES.past_races || []).map(r => ({ ...r, _source: 'config' }));
    const fromLocal  = loadLocalRaces().map(r => ({ ...r, _source: 'local' }));

    // Local prend la priorité sur config en cas de doublon
    // (l'utilisateur peut renommer une course pré-déclarée en l'éditant).
    const byKey = new Map();
    fromConfig.forEach(r => byKey.set(r.start_time, r));
    fromLocal.forEach(r => byKey.set(r.start_time, r));

    const races = Array.from(byKey.values());

    // Enrichissement depuis la séance correspondante
    races.forEach(r => {
      const sess = findSessionByKey(r.start_time);
      if (sess) {
        r._session = sess;
        if (r.km == null) r.km = sess.km;
        if (r.time_s == null) r.time_s = sess.dur_s;
        if (r.distance_key == null) r.distance_key = classifyDistance(r.km);
        r._date = sess._date;
      } else {
        // Course orpheline (séance pas encore importée)
        const d = new Date(r.start_time);
        r._date = isNaN(d.getTime()) ? new Date(0) : d;
      }
    });

    races.sort((a, b) => b._date - a._date);
    return races;
  }

  // Calcul des records depuis l'union de toutes les courses
  function computeRecords(allRaces) {
    // Une course est candidate pour un record si :
    //   - elle a la bonne distance_key
    //   - elle a un chrono
    //   - ET (sa distance enregistrée est dans la plage standard
    //          OU elle est pré-déclarée en config — bypass GPS approximatif).
    // Le bypass CFG permet d'inclure des courses officielles dont la montre a
    // sous-mesuré (ex : Apple Watch sur un 5K mesuré à 4.76 km).
    const records = {};
    for (const dist of RACES.distances) {
      const candidates = allRaces.filter(r => {
        if (r.distance_key !== dist.key) return false;
        if (!r.time_s || r.time_s <= 0) return false;
        if (!r.km) return false;
        const inRange = r.km >= dist.min_km && r.km <= dist.max_km;
        const isCfg = r._source === 'config';
        return inRange || isCfg;
      });
      if (candidates.length === 0) {
        records[dist.key] = null;
        continue;
      }
      const best = candidates.reduce((a, b) => a.time_s < b.time_s ? a : b);
      records[dist.key] = best;
    }
    return records;
  }

  // ---- RENDU : COUNTDOWNS ----
  function renderRaceCountdowns() {
    const wrap = document.getElementById('raceCountdowns');
    if (!wrap) return;

    const countdowns = RACES.countdowns || [];
    if (countdowns.length === 0) {
      wrap.innerHTML = '<article class="card placeholder"><p>Aucun objectif déclaré dans la config.</p></article>';
      return;
    }

    const phaseLabels = {
      preparation: 'Préparation',
      specific:    'Spécifique',
      taper:       'Affûtage',
      peak:        'Semaine de course',
      past:        'Passé',
    };

    wrap.innerHTML = countdowns.map(c => {
      const isPrimary = c.priority === 'primary';
      const daysDisplay = c.days_left < 0 ? 'Passé' : `J−${c.days_left}`;
      const weeksDisplay = c.days_left > 0 && c.weeks_left > 0 ? `${c.weeks_left} sem.` : '';
      const timeBlock = c.target_time
        ? `<div class="cd-time"><span class="cd-time-label">Cible</span><span class="cd-time-value">${escapeHtml(c.target_time)}</span></div>`
        : '';
      const strategyBlock = c.strategy_time
        ? `<div class="cd-time cd-time-secondary"><span class="cd-time-label">Stratégie</span><span class="cd-time-value">${escapeHtml(c.strategy_time)}</span></div>`
        : '';

      return `<article class="card countdown-card ${isPrimary ? 'is-primary' : ''}">
        <header class="countdown-head">
          <div>
            <div class="countdown-name">${escapeHtml(c.name)}</div>
            <div class="countdown-date">${fmtDateLong(c.date_fr)}</div>
          </div>
          <span class="countdown-phase phase-${c.phase}">${phaseLabels[c.phase] || c.phase}</span>
        </header>
        <div class="countdown-body">
          <div class="cd-days">
            <span class="cd-days-value">${daysDisplay}</span>
            ${weeksDisplay ? `<span class="cd-days-sub">${weeksDisplay}</span>` : ''}
          </div>
          <div class="cd-times">
            ${timeBlock}
            ${strategyBlock}
          </div>
        </div>
      </article>`;
    }).join('');
  }

  // ---- RENDU : TAPER ----
  function renderRaceTaper() {
    const wrap = document.getElementById('raceTaperWrap');
    if (!wrap) return;

    const tapers = RACES.tapers || [];
    if (tapers.length === 0) {
      wrap.innerHTML = '';
      return;
    }

    // S'il y a plusieurs tapers actifs, on affiche celui de l'objectif le plus proche
    const t = tapers[0];

    const weeksHtml = t.weeks.map(w => {
      let cls = 'taper-week';
      if (w.is_current) cls += ' is-current';
      else if (w.is_past) cls += ' is-past';
      return `<div class="${cls}">
        <div class="tw-label">S−${w.week}</div>
        <div class="tw-bar"><div class="tw-bar-fill" style="height:${w.volume_pct}%"></div></div>
        <div class="tw-pct">${w.volume_pct}%</div>
        <div class="tw-note">${escapeHtml(w.note)}</div>
      </div>`;
    }).join('');

    wrap.innerHTML = `<article class="card taper-card">
      <header class="card-head">
        <h3>Affûtage recommandé · ${escapeHtml(t.goal_name)}</h3>
        <span class="card-sub">${t.goal_date_fr} · S−${t.current_week} en cours</span>
      </header>
      <div class="taper-track">${weeksHtml}</div>
      <p class="taper-help">Volume relatif à votre pic de prépa. La semaine de course (S−1) se déroule sur 6 jours avec repos veille.</p>
    </article>`;
  }

  // ---- RENDU : RECORDS ----
  function renderRaceRecords() {
    const wrap = document.getElementById('raceRecords');
    if (!wrap) return;

    const allRaces = getAllRaces();
    const records = computeRecords(allRaces);

    const cards = RACES.distances.map(dist => {
      const rec = records[dist.key];
      if (!rec) {
        return `<div class="record-card record-empty">
          <div class="rec-label">${dist.label}</div>
          <div class="rec-value">—</div>
          <div class="rec-sub">Pas de course</div>
        </div>`;
      }
      const paceSec = rec.time_s / dist.target_km;
      return `<div class="record-card">
        <div class="rec-label">${dist.label}</div>
        <div class="rec-value">${fmtChrono(rec.time_s)}</div>
        <div class="rec-sub">${fmtPace(paceSec)}/km · ${escapeHtml(rec.name || 'Course')}</div>
      </div>`;
    }).join('');

    wrap.innerHTML = cards;
  }

  // ---- RENDU : TABLE DES COURSES ----
  function renderRaceTable() {
    const wrap = document.getElementById('raceTable');
    if (!wrap) return;

    const allRaces = getAllRaces();
    if (allRaces.length === 0) {
      wrap.innerHTML = `<p class="race-table-empty">Aucune course officielle pour le moment.<br>
        Cliquez sur <strong>+ Ajouter une course</strong> pour tagger votre première séance comme course.</p>`;
      return;
    }

    const rows = allRaces.map(r => {
      const dateLabel = r._session ? r._session.d : (r.start_time || '').slice(0, 10).split('-').reverse().join('/');
      const distLabel = RACES.distances.find(d => d.key === r.distance_key);
      const distText = distLabel ? distLabel.label : (r.km ? `${r.km.toFixed(2)} km` : '—');
      // Pour l'allure : sur les courses CFG avec distance_key explicite, on
      // calcule l'allure sur la distance OFFICIELLE (target_km) plutôt que la
      // distance enregistrée — sinon une montre qui sous-mesure (Apple Watch
      // sur 5K à 4.76 km) afficherait une allure faussement lente.
      let paceDenom = r.km;
      if (r._source === 'config' && distLabel) {
        paceDenom = distLabel.target_km;
      }
      const pace = r.time_s && paceDenom ? fmtPace(r.time_s / paceDenom) : '—';
      const sourceTag = r._source === 'config'
        ? '<span class="race-source race-source-config" title="Pré-déclarée en config Python">CFG</span>'
        : '<span class="race-source race-source-local" title="Taguée depuis le dashboard">LOC</span>';
      const canDelete = r._source === 'local';
      const deleteBtn = canDelete
        ? `<button class="race-row-del" data-key="${escapeHtml(r.start_time)}" title="Supprimer le tag">✕</button>`
        : `<span class="race-row-del race-row-del-disabled" title="Cette course est pré-déclarée en config, à modifier dans config.json">—</span>`;

      return `<tr>
        <td>${dateLabel}</td>
        <td><strong>${escapeHtml(r.name || 'Course')}</strong></td>
        <td>${distText}</td>
        <td>${r.km ? r.km.toFixed(2) + ' km' : '—'}</td>
        <td class="mono">${fmtChrono(r.time_s)}</td>
        <td class="mono">${pace}/km</td>
        <td>${sourceTag}</td>
        <td>${deleteBtn}</td>
      </tr>`;
    }).join('');

    wrap.innerHTML = `<div class="race-table-scroll">
      <table class="race-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Nom</th>
            <th>Distance</th>
            <th>Réel</th>
            <th>Chrono</th>
            <th>Allure</th>
            <th>Src</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;

    wrap.querySelectorAll('.race-row-del:not(.race-row-del-disabled)').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.key;
        if (!confirm('Supprimer cette course de votre liste ?')) return;
        const races = loadLocalRaces();
        const next = races.filter(r => r.start_time !== key);
        saveLocalRaces(next);
        rerenderRaceTab();
      });
    });
  }

  // ---- MARATHONS EN DÉTAIL ----------------------------------------------
  // Pour chaque marathon CFG/LOC, on calcule splits + agrégats à partir des
  // blocs km de la séance liée. Le bloc final est souvent un résiduel (~0.43
  // km) qu'on intègre au dernier segment plutôt que de l'ignorer.

  // Agrège une liste de blocs en KPIs (durée totale, distance, allure pondérée,
  // FC moyenne pondérée par durée, cadence moyenne pondérée par durée).
  function aggregateBlocs(blocs) {
    if (!blocs || !blocs.length) return null;
    let totalKm = 0, totalSec = 0, fcWeighted = 0, fcDur = 0, caWeighted = 0, caDur = 0;
    blocs.forEach(b => {
      totalKm += b.km || 0;
      totalSec += b.dur_s || 0;
      if (b.fc && b.dur_s) { fcWeighted += b.fc * b.dur_s; fcDur += b.dur_s; }
      if (b.ca && b.dur_s) { caWeighted += b.ca * b.dur_s; caDur += b.dur_s; }
    });
    return {
      km: totalKm,
      time_s: totalSec,
      pace_s_per_km: totalKm > 0 ? totalSec / totalKm : null,
      speed_kmh: totalSec > 0 ? (totalKm / totalSec) * 3600 : null,
      fc_avg: fcDur > 0 ? fcWeighted / fcDur : null,
      ca_avg: caDur > 0 ? caWeighted / caDur : null,
    };
  }

  // Calcule Semi1/Semi2 et 4×10K depuis les blocs d'une séance marathon.
  // Découpage par DISTANCE CUMULÉE (plus par index de bloc).
  //
  // Pourquoi ? Le dernier bloc d'une séance marathon est généralement un
  // résiduel (~0.43 km pour un marathon mesuré à 42.43 km par la montre).
  // Ses métriques (cadence, FC, allure) sont instables et polluent l'analyse
  // — Sébastien préfère ignorer tout ce qui dépasse les bornes "rondes" :
  //
  //   Semi1 : 0  → 21 km
  //   Semi2 : 21 → 42 km   (PAS 21 → 42.43, on coupe à 42)
  //   Q1    : 0  → 10 km
  //   Q2    : 10 → 20 km
  //   Q3    : 20 → 30 km
  //   Q4    : 30 → 40 km   (PAS 30 → fin, on coupe à 40)
  //
  // En pratique, sur des blocs Garmin de 1.0 km, ça revient à :
  //   Semi1 = blocs 1-21 ; Semi2 = blocs 22-42 (exclut bloc 43)
  //   Q1=1-10 ; Q2=11-20 ; Q3=21-30 ; Q4=31-40 (exclut blocs 41-43)
  // Mais la logique par distance cumulée est plus robuste si un marathon
  // a des blocs non standard (Garmin en miles, ou bloc résiduel ailleurs).

  // Agrège les blocs dans la fenêtre [startKm, endKm] (cumulé depuis le début).
  // Un bloc est inclus s'il est entièrement dans la fenêtre. S'il chevauche
  // une borne, il est inclus dans le segment où se trouve son CENTRE — c'est
  // l'heuristique la plus simple qui colle aux blocs Garmin standards.
  function sliceBlocsByKm(blocs, startKm, endKm) {
    const out = [];
    let cumStart = 0;
    for (const b of blocs) {
      const blocLen = b.km || 0;
      const cumEnd = cumStart + blocLen;
      const blocCenter = (cumStart + cumEnd) / 2;
      if (blocCenter >= startKm && blocCenter < endKm) {
        out.push(b);
      }
      cumStart = cumEnd;
    }
    return out;
  }

  function computeMarathonSplits(sess) {
    const blocs = sess.b || [];
    if (blocs.length < 20) return null;

    // Vérifier que la distance totale est suffisante (au moins 40 km pour
    // que les 4 quarts soient calculables).
    const totalKm = blocs.reduce((a, b) => a + (b.km || 0), 0);
    if (totalKm < 40) return null;

    return {
      semi1:   aggregateBlocs(sliceBlocsByKm(blocs, 0,  21)),
      semi2:   aggregateBlocs(sliceBlocsByKm(blocs, 21, 42)),
      q1:      aggregateBlocs(sliceBlocsByKm(blocs, 0,  10)),
      q2:      aggregateBlocs(sliceBlocsByKm(blocs, 10, 20)),
      q3:      aggregateBlocs(sliceBlocsByKm(blocs, 20, 30)),
      q4:      aggregateBlocs(sliceBlocsByKm(blocs, 30, 40)),
      overall: aggregateBlocs(blocs),
    };
  }

  // Format delta entre deux splits (Semi2 - Semi1 par km, par ex)
  function fmtPaceDelta(refPaceSec, otherPaceSec) {
    if (refPaceSec == null || otherPaceSec == null) return '';
    const d = Math.round(otherPaceSec - refPaceSec);
    if (d === 0) return '±0"';
    return (d > 0 ? '+' : '−') + Math.abs(d) + '"';
  }

  function renderRaceMarathons() {
    const wrap = document.getElementById('raceMarathons');
    if (!wrap) return;

    // On ne prend que les marathons taguées en CFG/LOC avec une séance liée
    // (pas les marathons orphelins, car sans _session.b on n'a pas les blocs).
    const allRaces = getAllRaces();
    const marathons = allRaces.filter(r =>
      r.distance_key === 'marathon' && r._session && r._session.b && r._session.b.length
    );

    if (marathons.length === 0) {
      wrap.innerHTML = '<p class="race-table-empty">Aucun marathon détaillé disponible (pas de blocs km).</p>';
      return;
    }

    // Tri par date desc
    marathons.sort((a, b) => b._date - a._date);

    const rowsHtml = marathons.map((m, idx) => {
      const splits = computeMarathonSplits(m._session);
      const ov = splits.overall;

      const speedTxt = ov.speed_kmh ? ov.speed_kmh.toFixed(2) + ' km/h' : '—';
      const paceTxt  = ov.pace_s_per_km ? fmtPace(ov.pace_s_per_km) + '/km' : '—';
      const fcTxt    = ov.fc_avg ? Math.round(ov.fc_avg) + ' bpm' : '—';
      const caTxt    = ov.ca_avg ? Math.round(ov.ca_avg) + ' ppm' : '—';

      return `<div class="mara-row" data-idx="${idx}">
        <button class="mara-head" data-idx="${idx}" aria-expanded="false">
          <div class="mara-head-main">
            <div class="mara-head-title">
              <span class="mara-chrono">${fmtChrono(m.time_s)}</span>
              <span class="mara-name">${escapeHtml(m.name || 'Marathon')}</span>
            </div>
            <div class="mara-head-date">${m._session.d}</div>
          </div>
          <div class="mara-head-kpis">
            <div class="mara-kpi"><span class="mk-l">Vitesse</span><span class="mk-v">${speedTxt}</span></div>
            <div class="mara-kpi"><span class="mk-l">Allure</span><span class="mk-v">${paceTxt}</span></div>
            <div class="mara-kpi"><span class="mk-l">FC</span><span class="mk-v">${fcTxt}</span></div>
            <div class="mara-kpi"><span class="mk-l">Cadence</span><span class="mk-v">${caTxt}</span></div>
          </div>
          <span class="mara-chevron" aria-hidden="true">▾</span>
        </button>
        <div class="mara-detail" id="maraDetail-${idx}" hidden></div>
      </div>`;
    }).join('');

    wrap.innerHTML = rowsHtml;

    // Stocker les marathons et splits pour rendu lazy au déploiement
    wrap._marathons = marathons;
    wrap._splits = marathons.map(m => computeMarathonSplits(m._session));

    // Bind expand/collapse
    wrap.querySelectorAll('.mara-head').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.idx, 10);
        const detail = document.getElementById('maraDetail-' + idx);
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        if (expanded) {
          detail.hidden = true;
          btn.setAttribute('aria-expanded', 'false');
          btn.classList.remove('is-open');
        } else {
          // Rendu lazy : on construit le détail au premier déploiement
          if (!detail._rendered) {
            renderMarathonDetail(detail, wrap._marathons[idx], wrap._splits[idx]);
            detail._rendered = true;
          }
          detail.hidden = false;
          btn.setAttribute('aria-expanded', 'true');
          btn.classList.add('is-open');
          // Resize ECharts une fois affiché (sinon dimensions 0)
          setTimeout(() => {
            if (detail._charts) detail._charts.forEach(c => c && c.resize());
          }, 60);
        }
      });
    });
  }

  // Rendu du contenu détaillé d'un marathon (splits + 2 graphiques)
  function renderMarathonDetail(container, marathon, splits) {
    const sess = marathon._session;

    // Cartes splits Semi1 vs Semi2
    const semi1 = splits.semi1, semi2 = splits.semi2;
    const semiHtml = `<div class="splits-wrap">
      <div class="splits-title">Première / seconde moitié</div>
      <div class="splits-grid splits-grid-2">
        ${splitCardHtml('Semi 1 (km 0-21)', semi1, null)}
        ${splitCardHtml('Semi 2 (km 21-42)', semi2, semi1)}
      </div>
    </div>`;

    // Cartes 4×10K
    const q1 = splits.q1, q2 = splits.q2, q3 = splits.q3, q4 = splits.q4;
    const quartersHtml = `<div class="splits-wrap">
      <div class="splits-title">Quarts (4×10 km)</div>
      <div class="splits-grid splits-grid-4">
        ${splitCardHtml('Km 0-10', q1, null)}
        ${splitCardHtml('Km 10-20', q2, q1)}
        ${splitCardHtml('Km 20-30', q3, q1)}
        ${splitCardHtml('Km 30-40', q4, q1)}
      </div>
    </div>`;

    // Conteneurs charts
    const chartsHtml = `<div class="mara-charts">
      <div class="mara-chart-card">
        <div class="mara-chart-title">Allure et fréquence cardiaque par km</div>
        <div class="mara-chart" id="maraChartPaceFc-${marathon.start_time.replace(/[^0-9]/g,'')}" style="height:280px;"></div>
      </div>
      <div class="mara-chart-card">
        <div class="mara-chart-title">Cadence par km (pas/min)</div>
        <div class="mara-chart" id="maraChartCadence-${marathon.start_time.replace(/[^0-9]/g,'')}" style="height:220px;"></div>
      </div>
    </div>`;

    container.innerHTML = semiHtml + quartersHtml + chartsHtml;

    // Construction des charts ECharts
    const blocs = sess.b || [];
    const xLabels = blocs.map(b => 'km ' + b.n);
    const paces = blocs.map(b => b.ps || null);
    const fcs   = blocs.map(b => b.fc || null);
    const cads  = blocs.map(b => b.ca || null);

    const idSuffix = marathon.start_time.replace(/[^0-9]/g, '');
    const paceFcEl  = document.getElementById('maraChartPaceFc-' + idSuffix);
    const cadenceEl = document.getElementById('maraChartCadence-' + idSuffix);
    container._charts = [];

    if (paceFcEl) {
      const c = echarts.init(paceFcEl);
      // Y axis allure : on cale min/max sur les données pour rendre les
      // variations lisibles (partir de 0 écraserait tout puisqu'un marathon
      // est entre 200 et 350 s/km, jamais à 0).
      const validPaces = paces.filter(v => v != null);
      const minPace = validPaces.length ? Math.min(...validPaces) : 200;
      const maxPace = validPaces.length ? Math.max(...validPaces) : 300;
      const yPaceMin = Math.floor((minPace - 10) / 5) * 5;
      const yPaceMax = Math.ceil((maxPace + 10) / 5) * 5;
      c.setOption({
        textStyle: CHART_THEME.textStyle,
        grid: { left: 50, right: 50, top: 30, bottom: 32, containLabel: true },
        legend: { data: ['Allure', 'FC'], top: 0, textStyle: { color: INK2, fontSize: 11 } },
        tooltip: {
          ...CHART_THEME.tooltip, trigger: 'axis',
          formatter: (params) => {
            let s = '<b>' + params[0].axisValue + '</b><br/>';
            params.forEach(p => {
              if (p.seriesName === 'Allure' && p.data != null) {
                s += `Allure : ${fmtPace(p.data)}/km<br/>`;
              } else if (p.seriesName === 'FC' && p.data != null) {
                s += `FC : ${p.data} bpm<br/>`;
              }
            });
            return s;
          },
        },
        xAxis: { ...CHART_THEME.xAxis, type: 'category', data: xLabels,
                 axisLabel: { ...CHART_THEME.xAxis.axisLabel,
                              interval: Math.max(0, Math.floor(blocs.length / 8) - 1) } },
        yAxis: [
          {
            ...CHART_THEME.yAxis, type: 'value', name: 'Allure',
            min: yPaceMin, max: yPaceMax,
            nameTextStyle: { color: '#94a3b8', fontSize: 10 },
            axisLabel: { ...CHART_THEME.yAxis.axisLabel,
                         formatter: v => Math.floor(v/60) + "'" + String(Math.round(v%60)).padStart(2,'0') },
          },
          {
            ...CHART_THEME.yAxis, type: 'value', name: 'FC (bpm)',
            position: 'right',
            nameTextStyle: { color: '#94a3b8', fontSize: 10 },
            splitLine: { show: false },
          },
        ],
        series: [
          {
            name: 'Allure', type: 'bar', yAxisIndex: 0, data: paces,
            itemStyle: {
              // Gradient inversé : vert (rapide) en bas, orange (lent) en haut
              color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                       colorStops: [{ offset: 0, color: '#f0923e' }, { offset: 1, color: '#22d3a7' }] },
              borderRadius: [3, 3, 0, 0],
            },
          },
          {
            name: 'FC', type: 'line', yAxisIndex: 1, smooth: true, data: fcs,
            symbol: 'circle', symbolSize: 5,
            lineStyle: { width: 2.4, color: '#ef5b5b' },
            itemStyle: { color: '#ef5b5b' },
          },
        ],
        animationDuration: 600,
      });
      container._charts.push(c);
    }

    if (cadenceEl) {
      const c = echarts.init(cadenceEl);
      // Min/max cadence pour scaler proprement la Y axis (la cadence ne descend
      // jamais à 0, et commencer à 0 écrase la lecture des variations).
      const validCads = cads.filter(v => v != null);
      const minCad = validCads.length ? Math.min(...validCads) : 150;
      const maxCad = validCads.length ? Math.max(...validCads) : 200;
      const yMin = Math.max(140, Math.floor(minCad / 5) * 5 - 5);
      const yMax = Math.ceil(maxCad / 5) * 5 + 5;
      c.setOption({
        textStyle: CHART_THEME.textStyle,
        grid: { left: 40, right: 16, top: 16, bottom: 32, containLabel: true },
        tooltip: {
          ...CHART_THEME.tooltip, trigger: 'axis',
          formatter: p => p[0].data != null
            ? `<b>${p[0].axisValue}</b><br/>Cadence : ${p[0].data} ppm`
            : `<b>${p[0].axisValue}</b><br/>—`,
        },
        xAxis: { ...CHART_THEME.xAxis, type: 'category', data: xLabels,
                 axisLabel: { ...CHART_THEME.xAxis.axisLabel,
                              interval: Math.max(0, Math.floor(blocs.length / 8) - 1) } },
        yAxis: { ...CHART_THEME.yAxis, type: 'value', min: yMin, max: yMax,
                 name: 'ppm', nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
        series: [{
          type: 'bar', data: cads,
          itemStyle: {
            color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                     colorStops: [{ offset: 0, color: '#9b6dff' }, { offset: 1, color: '#5b8af5' }] },
            borderRadius: [3, 3, 0, 0],
          },
        }],
        animationDuration: 600,
      });
      container._charts.push(c);
    }
  }

  function splitCardHtml(label, split, refSplit) {
    if (!split) {
      return `<div class="split-card split-empty"><div class="sc-l">${label}</div><div class="sc-v">—</div></div>`;
    }
    const paceTxt = split.pace_s_per_km ? fmtPace(split.pace_s_per_km) + '/km' : '—';
    const fcTxt   = split.fc_avg ? Math.round(split.fc_avg) + ' bpm' : '—';
    const caTxt   = split.ca_avg ? Math.round(split.ca_avg) + ' ppm' : '—';
    const chrono  = fmtChrono(split.time_s);

    // Delta allure si refSplit fourni
    let deltaHtml = '';
    if (refSplit && refSplit.pace_s_per_km && split.pace_s_per_km) {
      const d = split.pace_s_per_km - refSplit.pace_s_per_km;
      let cls = 'delta-stable';
      if (d > 2) cls = 'delta-slower';
      else if (d < -2) cls = 'delta-faster';
      deltaHtml = `<span class="sc-delta ${cls}">${fmtPaceDelta(refSplit.pace_s_per_km, split.pace_s_per_km)}/km</span>`;
    }

    return `<div class="split-card">
      <div class="sc-l">${label}</div>
      <div class="sc-chrono">${chrono}</div>
      <div class="sc-pace">${paceTxt} ${deltaHtml}</div>
      <div class="sc-sub">${fcTxt} · ${caTxt}</div>
    </div>`;
  }

  // ---- PRÉPA RÉTROSPECTIVE ----------------------------------------------
  // Pour chaque marathon CFG/LOC, on calcule le volume km par semaine
  // calendaire des 10 semaines qui précèdent la course :
  //   S-1   : 6 jours (lundi → samedi avant le dimanche course typique)
  //   S-2 à S-10 : 7 jours (lundi → dimanche)
  // Si le marathon n'est pas un dimanche, on garde le principe : S-1 = veille -6j
  // jusqu'à veille incluse, S-N (N>1) = fenêtres de 7j en remontant.

  function startOfDay(date) {
    const d = new Date(date);
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function addDays(date, days) {
    const d = new Date(date);
    d.setDate(d.getDate() + days);
    return d;
  }

  function computePrepWeeks(marathonDate) {
    // marathonDate = Date JS du jour de la course
    const raceDay = startOfDay(marathonDate);
    const weeks = [];

    // S-1 : du J-6 au J-1 (6 jours)
    const s1End = addDays(raceDay, -1);   // veille incluse
    const s1Start = addDays(raceDay, -6); // 6 jours en arrière
    weeks.push({ week: 1, start: s1Start, end: s1End });

    // S-2 à S-10 : 7 jours chacune, en remontant
    // S-2 = J-13 à J-7
    // S-N = J-(N*7-1) à J-((N-1)*7)... attendu : S-2 termine la veille du début de S-1
    for (let n = 2; n <= 10; n++) {
      const end = addDays(s1Start, -1 - (n - 2) * 7);
      const start = addDays(end, -6);
      weeks.push({ week: n, start: start, end: end });
    }

    return weeks;
  }

  function sumKmInWindow(sessions, startDate, endDate) {
    // Somme des km des séances dont _date est dans [startDate, endDate] inclus
    let total = 0;
    sessions.forEach(s => {
      if (!s._date) return;
      const d = startOfDay(s._date);
      if (d >= startDate && d <= endDate) {
        total += s.km || 0;
      }
    });
    return total;
  }

  function renderRacePrep() {
    const wrap = document.getElementById('racePrep');
    if (!wrap) return;

    const allRaces = getAllRaces();
    const marathons = allRaces.filter(r => r.distance_key === 'marathon' && r._date);
    if (marathons.length === 0) {
      wrap.innerHTML = '<p class="race-table-empty">Aucun marathon à analyser.</p>';
      return;
    }

    // Tri par date desc (plus récent en haut)
    marathons.sort((a, b) => b._date - a._date);

    // Pour chaque marathon : 10 semaines × volume + total + temps
    const rows = marathons.map(m => {
      const weeks = computePrepWeeks(m._date);
      const volumes = weeks.map(w => sumKmInWindow(SESSIONS, w.start, w.end));
      const totalKm = volumes.reduce((a, b) => a + b, 0);

      // Color-coding option B : relatif à CE marathon
      // Vert pour le min, rouge pour le max, bleu sinon.
      // On classe les 10 valeurs et on affecte vert au tiers bas, rouge au tiers haut.
      const sorted = [...volumes].sort((a, b) => a - b);
      const lowThreshold = sorted[Math.floor(sorted.length / 3) - 1] || sorted[0];
      const highThreshold = sorted[Math.ceil(sorted.length * 2 / 3)] || sorted[sorted.length - 1];

      return { marathon: m, weeks, volumes, totalKm, lowThreshold, highThreshold };
    });

    // Construction tableau
    // Colonnes : Course | S-10 | S-9 | ... | S-1 | Total | Chrono
    const headerWeeks = [];
    for (let n = 10; n >= 1; n--) {
      headerWeeks.push(`<th>S−${n}</th>`);
    }

    const headRow = `<tr>
      <th class="prep-name-col">Course</th>
      ${headerWeeks.join('')}
      <th>Total</th>
      <th>Chrono</th>
    </tr>`;

    const bodyRows = rows.map(row => {
      // weeks[] est dans l'ordre S-1, S-2, ..., S-10 (cf. computePrepWeeks)
      // On veut afficher S-10 → S-1, donc on lit à l'envers.
      const cells = [];
      for (let n = 10; n >= 1; n--) {
        const idx = row.weeks.findIndex(w => w.week === n);
        const v = row.volumes[idx] || 0;
        let cls = 'prep-mid';
        if (v <= row.lowThreshold) cls = 'prep-low';
        else if (v >= row.highThreshold) cls = 'prep-high';
        cells.push(`<td class="prep-cell ${cls}">${v.toFixed(0)}</td>`);
      }
      return `<tr>
        <td class="prep-name-col"><strong>${escapeHtml(row.marathon.name)}</strong><br><span class="prep-date">${row.marathon._session ? row.marathon._session.d : ''}</span></td>
        ${cells.join('')}
        <td class="prep-total">${row.totalKm.toFixed(0)} km</td>
        <td class="prep-chrono mono">${fmtChrono(row.marathon.time_s)}</td>
      </tr>`;
    }).join('');

    wrap.innerHTML = `<div class="prep-table-scroll">
      <table class="prep-table">
        <thead>${headRow}</thead>
        <tbody>${bodyRows}</tbody>
      </table>
      <p class="prep-help">Volume hebdomadaire en km. S−1 sur 6 jours (lundi à samedi, hors jour de course). Couleurs relatives à chaque marathon : <span class="prep-legend prep-low">tiers bas</span> <span class="prep-legend prep-mid">tiers médian</span> <span class="prep-legend prep-high">tiers haut</span>.</p>
    </div>`;
  }

  function rerenderRaceTab() {
    renderRaceCountdowns();
    renderRaceTaper();
    renderRaceRecords();
    renderRaceMarathons();
    renderRacePrep();
    renderRaceTable();
  }

  // ---- MODAL : ajout d'une course ----
  function setupRaceModal() {
    const modal     = document.getElementById('raceModal');
    const addBtn    = document.getElementById('raceAddBtn');
    const closeBtn  = document.getElementById('raceModalClose');
    const cancelBtn = document.getElementById('raceCancelBtn');
    const saveBtn   = document.getElementById('raceSaveBtn');
    const filterEl  = document.getElementById('raceFilterMinKm');
    const pickerEl  = document.getElementById('raceSessionPicker');
    const nameEl    = document.getElementById('raceNameInput');
    const previewEl = document.getElementById('raceModalPreview');

    if (!modal || !addBtn) return;

    function openModal() {
      nameEl.value = '';
      filterEl.value = '15';
      populatePicker();
      modal.hidden = false;
      document.body.style.overflow = 'hidden';
      setTimeout(() => nameEl.focus(), 50);
    }

    function closeModal() {
      modal.hidden = true;
      document.body.style.overflow = '';
    }

    function populatePicker() {
      const minKm = parseFloat(filterEl.value) || 5;
      const allRaces = getAllRaces();
      const taggedKeys = new Set(allRaces.map(r => r.start_time));

      const candidates = SESSIONS
        .filter(s => s.km >= minKm && !taggedKeys.has(sessionKey(s)))
        .sort((a, b) => b._date - a._date)
        .slice(0, 200);

      if (candidates.length === 0) {
        pickerEl.innerHTML = '<option value="">Aucune séance disponible pour ce filtre</option>';
        updatePreview();
        return;
      }

      pickerEl.innerHTML = candidates.map(s => {
        const key = sessionKey(s);
        const lbl = `${s.d} · ${s.km.toFixed(2)} km · ${fmtChrono(s.dur_s)}`;
        return `<option value="${escapeHtml(key)}">${escapeHtml(lbl)}</option>`;
      }).join('');
      updatePreview();
    }

    function updatePreview() {
      const key = pickerEl.value;
      if (!key) {
        previewEl.innerHTML = '';
        return;
      }
      const sess = findSessionByKey(key);
      if (!sess) {
        previewEl.innerHTML = '';
        return;
      }
      const distKey = classifyDistance(sess.km);
      const distLabel = distKey ? RACES.distances.find(d => d.key === distKey).label : null;
      const distInfo = distLabel
        ? `<span class="preview-badge preview-badge-ok">Reconnue comme ${distLabel}</span>`
        : `<span class="preview-badge preview-badge-warn">Distance hors plages records standards</span>`;

      previewEl.innerHTML = `<div class="preview-grid">
        <div><span class="preview-label">Distance</span><span class="preview-val">${sess.km.toFixed(2)} km</span></div>
        <div><span class="preview-label">Chrono</span><span class="preview-val">${fmtChrono(sess.dur_s)}</span></div>
        <div><span class="preview-label">Allure</span><span class="preview-val">${sess.ps ? fmtPace(sess.ps) + '/km' : '—'}</span></div>
        <div class="preview-info">${distInfo}</div>
      </div>`;
    }

    function save() {
      const key = pickerEl.value;
      const name = nameEl.value.trim();
      if (!key) {
        alert('Sélectionnez une séance.');
        return;
      }
      if (!name) {
        alert('Donnez un nom à la course.');
        nameEl.focus();
        return;
      }
      const sess = findSessionByKey(key);
      if (!sess) {
        alert('Séance introuvable.');
        return;
      }

      const newRace = {
        name: name,
        start_time: key,
        distance_key: classifyDistance(sess.km),
        km: sess.km,
        time_s: sess.dur_s,
      };

      const races = loadLocalRaces();
      const filtered = races.filter(r => r.start_time !== key);
      filtered.push(newRace);
      saveLocalRaces(filtered);

      closeModal();
      rerenderRaceTab();
    }

    addBtn.addEventListener('click', openModal);
    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    saveBtn.addEventListener('click', save);
    filterEl.addEventListener('change', populatePicker);
    pickerEl.addEventListener('change', updatePreview);

    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modal.hidden) closeModal();
    });
  }

  // ============================================================================
  // ===== 12. MODULE VOLUME ====================================================
  // ============================================================================
  //
  // 5 vues :
  //   - Volume hebdo empilé par type de séance + moyenne mobile 4 sem (sur filtre)
  //   - Volume mensuel total (sur filtre)
  //   - Répartition par type (donut, sur filtre)
  //   - Cumul annuel comparé (toutes années, pas filtré)
  //   - Heatmap calendrier (année sélectionnable indépendamment)
  //
  // Le filtre temporel global s'applique aux 3 premières. Le cumul annuel
  // a sa propre logique (comparer les années entre elles) et la heatmap a son
  // propre sélecteur.

  // Palette par type de séance, partagée entre les vues Volume pour cohérence
  const TYPE_COLORS = {
    footing:       '#22d3a7',  // vert clair
    endurance:     '#10b981',  // vert moyen
    sortie_longue: '#047857',  // vert foncé
    tempo:         '#f0923e',  // orange
    seuil:         '#dc2626',  // rouge
    fractionne:    '#dc2626',  // rouge (alias)
    frac_court:    '#ef4444',  // rouge clair
    frac_long:     '#b91c1c',  // rouge foncé
    marathon:      '#5b8af5',  // bleu (course)
    semi:          '#3b82f6',  // bleu clair (course)
    course:        '#5b8af5',
    other:         '#94a3b8',  // gris
  };

  const TYPE_LABELS = {
    footing: 'Footing', endurance: 'Endurance', sortie_longue: 'Sortie longue',
    tempo: 'Tempo', seuil: 'Seuil',
    fractionne: 'Fractionné', frac_court: 'Frac. court', frac_long: 'Frac. long',
    marathon: 'Marathon', semi: 'Semi', course: 'Course', other: 'Autre',
  };

  // Labels courts pour les légendes contraintes (graph hebdo empilé).
  // Garde des labels lisibles ailleurs (donut, modal, filtres).
  const TYPE_LABELS_SHORT = {
    footing: 'Foot.', endurance: 'End.', sortie_longue: 'SL',
    tempo: 'Tempo', seuil: 'Seuil',
    fractionne: 'Frac.', frac_court: 'F.court', frac_long: 'F.long',
    marathon: 'Mara.', semi: 'Semi', course: 'Course', other: 'Autre',
  };

  function typeColor(tp) { return TYPE_COLORS[tp] || TYPE_COLORS.other; }
  function typeLabel(tp) { return TYPE_LABELS[tp] || tp || 'Autre'; }
  function typeLabelShort(tp) { return TYPE_LABELS_SHORT[tp] || tp || 'Autre'; }

  // Stockage des instances ECharts pour dispose ultérieur
  const volCharts = {};

  function disposeVolChart(key) {
    if (volCharts[key]) {
      volCharts[key].dispose();
      volCharts[key] = null;
    }
  }

  // ---- 1. Volume hebdo empilé par type + moyenne mobile 4 sem ----
  function chartVolWeeklyStacked(filteredSessions) {
    disposeVolChart('weeklyStacked');
    const el = document.getElementById('volWeeklyStacked');
    if (!el) return;

    // Regrouper par semaine ISO et par type
    const wkMap = new Map();  // wk → { type → km }
    filteredSessions.forEach(s => {
      if (!s._date) return;
      const wk = isoWeekKey(s._date);
      if (!wkMap.has(wk)) wkMap.set(wk, {});
      const bucket = wkMap.get(wk);
      const tp = s.tp || 'other';
      bucket[tp] = (bucket[tp] || 0) + (s.km || 0);
    });

    const weeks = Array.from(wkMap.keys()).sort().slice(-52);
    if (weeks.length === 0) {
      el.innerHTML = '<p style="color:#94a3b8;padding:20px;text-align:center">Aucune donnée.</p>';
      return;
    }

    // Tous les types présents
    const allTypes = new Set();
    weeks.forEach(w => Object.keys(wkMap.get(w)).forEach(t => allTypes.add(t)));

    // Ordre d'affichage : du plus "doux" (endurance) au plus "intense" (fractionné),
    // pour que la pile aille naturellement du calme en bas au dur en haut
    const typeOrder = ['footing','endurance','sortie_longue','tempo','seuil',
                       'frac_long','frac_court','fractionne','marathon','semi','course','other'];
    const orderedTypes = typeOrder.filter(t => allTypes.has(t));
    orderedTypes.push(...Array.from(allTypes).filter(t => !typeOrder.includes(t)));

    const series = orderedTypes.map(tp => ({
      name: typeLabelShort(tp),
      type: 'bar',
      stack: 'total',
      data: weeks.map(wk => Math.round((wkMap.get(wk)[tp] || 0) * 10) / 10),
      itemStyle: { color: typeColor(tp), borderRadius: 0 },
      barWidth: '70%',
    }));

    // Moyenne mobile 4 semaines sur le total
    const totals = weeks.map(wk => {
      const b = wkMap.get(wk);
      return Object.values(b).reduce((a, x) => a + x, 0);
    });
    const ma4 = totals.map((_, i) => {
      const window = totals.slice(Math.max(0, i - 3), i + 1);
      return Math.round(window.reduce((a, x) => a + x, 0) / window.length * 10) / 10;
    });
    series.push({
      name: 'Moy. 4 sem.',
      type: 'line',
      data: ma4,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2.5, color: INK, type: 'dashed' },
      z: 10,
    });

    const dom = volCharts.weeklyStacked = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      legend: { top: 0, textStyle: { color: INK2, fontSize: 11 }, type: 'scroll' },
      grid: { left: 40, right: 16, top: 36, bottom: 32, containLabel: true },
      tooltip: {
        ...CHART_THEME.tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (params) => {
          // Filtrer la moyenne mobile à part
          const bars = params.filter(p => p.seriesType === 'bar' && p.data > 0);
          const ma = params.find(p => p.seriesName === 'Moy. 4 sem.');
          let total = bars.reduce((a, p) => a + p.data, 0);
          let s = `<b>${params[0].axisValue}</b><br/>`;
          bars.sort((a, b) => b.data - a.data).forEach(p => {
            s += `<span style="display:inline-block;width:10px;height:10px;background:${p.color};margin-right:6px;border-radius:2px"></span>${p.seriesName} : ${p.data.toFixed(1)} km<br/>`;
          });
          s += `<hr style="margin:4px 0;border:0;border-top:1px solid #e2e8f0"><b>Total : ${total.toFixed(1)} km</b>`;
          if (ma) s += `<br/><span style="color:#64748b">Moy. 4 sem. : ${ma.data.toFixed(1)} km</span>`;
          return s;
        },
      },
      xAxis: { ...CHART_THEME.xAxis, type: 'category',
               data: weeks.map(w => fmtWeek(w)),
               axisLabel: { ...CHART_THEME.xAxis.axisLabel,
                            interval: Math.max(0, Math.floor(weeks.length / 8) - 1) } },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', name: 'km',
               nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
      series,
      animationDuration: 600,
    });
  }

  // ---- 2. Volume mensuel (sur filtre) ----
  function chartVolMonthly(filteredSessions) {
    disposeVolChart('monthly');
    const el = document.getElementById('volMonthly');
    if (!el) return;

    const moMap = new Map();
    filteredSessions.forEach(s => {
      if (!s._date) return;
      const moKey = `${s._date.getFullYear()}-${String(s._date.getMonth() + 1).padStart(2, '0')}`;
      moMap.set(moKey, (moMap.get(moKey) || 0) + (s.km || 0));
    });
    const months = Array.from(moMap.keys()).sort().slice(-24);
    if (months.length === 0) {
      el.innerHTML = '<p style="color:#94a3b8;padding:20px;text-align:center">Aucune donnée.</p>';
      return;
    }

    const dom = volCharts.monthly = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      grid: { left: 40, right: 16, top: 16, bottom: 32, containLabel: true },
      tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                 formatter: p => `<b>${p[0].axisValue}</b><br/>${p[0].data.toFixed(0)} km` },
      xAxis: { ...CHART_THEME.xAxis, type: 'category', data: months.map(m => fmtMonth(m)) },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', name: 'km',
               nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
      series: [{
        type: 'bar',
        data: months.map(m => Math.round(moMap.get(m))),
        itemStyle: {
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                   colorStops: [{ offset: 0, color: '#5b8af5' }, { offset: 1, color: '#22d3a7' }] },
          borderRadius: [4, 4, 0, 0],
        },
        animationDuration: 600,
      }],
    });
  }

  // ---- 3. Répartition par type (donut) ----
  function chartVolTypeDist(filteredSessions) {
    disposeVolChart('typeDist');
    const el = document.getElementById('volTypeDist');
    if (!el) return;

    const dist = new Map();
    filteredSessions.forEach(s => {
      const tp = s.tp || 'other';
      dist.set(tp, (dist.get(tp) || 0) + (s.km || 0));
    });
    if (dist.size === 0) {
      el.innerHTML = '<p style="color:#94a3b8;padding:20px;text-align:center">Aucune donnée.</p>';
      return;
    }

    const data = Array.from(dist.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([tp, km]) => ({
        name: typeLabel(tp),
        value: Math.round(km * 10) / 10,
        itemStyle: { color: typeColor(tp) },
      }));

    const dom = volCharts.typeDist = echarts.init(el);
    dom.setOption({
      textStyle: CHART_THEME.textStyle,
      tooltip: { ...CHART_THEME.tooltip, trigger: 'item',
                 formatter: p => `<b>${p.name}</b><br/>${p.value.toFixed(1)} km (${p.percent.toFixed(1)}%)` },
      legend: { orient: 'vertical', left: 'left', top: 'center', textStyle: { color: INK2, fontSize: 11 } },
      series: [{
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['65%', '50%'],
        data,
        label: { show: true, formatter: '{b}\n{d}%', fontSize: 10, color: INK2 },
        labelLine: { length: 8, length2: 8 },
        animationDuration: 700,
      }],
    });
  }

  // ---- 4. Cumul annuel comparé (toutes années, pas filtré) ----
  function chartVolCumulative() {
    disposeVolChart('cumulative');
    const el = document.getElementById('volCumulative');
    if (!el) return;

    // Pour chaque année, vecteur de 366 valeurs (jour 1 à 366) = cumul jusqu'à ce jour
    const yearData = new Map();  // year → [cumKm at each day-of-year]
    SESSIONS.forEach(s => {
      if (!s._date) return;
      const y = s._date.getFullYear();
      const start = new Date(y, 0, 1);
      const dayOfYear = Math.floor((startOfDay(s._date) - start) / 86400000);
      if (!yearData.has(y)) yearData.set(y, new Array(366).fill(0));
      yearData.get(y)[dayOfYear] += s.km || 0;
    });

    // Cumul
    const years = Array.from(yearData.keys()).sort();
    years.forEach(y => {
      const arr = yearData.get(y);
      for (let i = 1; i < arr.length; i++) arr[i] += arr[i - 1];
    });

    // X axis = jours de l'année, on affiche des labels mois
    const xLabels = [];
    for (let d = 0; d < 366; d++) {
      // Labels uniquement le 1er de chaque mois
      const date = new Date(2024, 0, 1 + d); // 2024 est bissextile, parfait
      xLabels.push(date.getDate() === 1 ? date.toLocaleString('fr-FR', { month: 'short' }) : '');
    }

    const palette = ['#94a3b8', '#cbd5e1', '#94a3b8', '#64748b', '#f0923e', '#5b8af5', '#22d3a7'];
    const series = years.map((y, i) => {
      // Année courante = couleur vive, années précédentes = grisé dégressif
      const isCurrent = i === years.length - 1;
      const isLast = i === years.length - 2;
      let color;
      if (isCurrent) color = '#5b8af5';
      else if (isLast) color = '#22d3a7';
      else color = palette[i % palette.length];
      return {
        name: String(y),
        type: 'line',
        data: yearData.get(y),
        smooth: true,
        symbol: 'none',
        lineStyle: { width: isCurrent ? 3 : 1.8, color },
        itemStyle: { color },
        z: isCurrent ? 10 : 1,
      };
    });

    const dom = volCharts.cumulative = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      legend: { top: 0, textStyle: { color: INK2, fontSize: 11 } },
      grid: { left: 40, right: 16, top: 36, bottom: 32, containLabel: true },
      tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                 formatter: (params) => {
                   const d = parseInt(params[0].axisValue, 10);
                   const date = new Date(2024, 0, 1 + d);
                   const dayLabel = date.toLocaleString('fr-FR', { day: 'numeric', month: 'short' });
                   let s = `<b>${dayLabel}</b><br/>`;
                   params.sort((a, b) => b.data - a.data).forEach(p => {
                     s += `<span style="color:${p.color}">${p.seriesName}</span> : ${Math.round(p.data)} km<br/>`;
                   });
                   return s;
                 } },
      xAxis: { ...CHART_THEME.xAxis, type: 'category', data: xLabels.map((_, i) => i),
               axisLabel: { ...CHART_THEME.xAxis.axisLabel,
                            formatter: i => xLabels[i] || '',
                            interval: 0 } },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', name: 'km cumulés',
               nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
      series,
      animationDuration: 800,
    });
  }

  // ---- 5. Heatmap calendrier ----
  // Le sélecteur d'année est indépendant du filtre global (on veut comparer
  // facilement les années entre elles depuis cette vue).
  let heatmapYear = null; // initialisé dans renderVolumeTab

  function setupHeatmapYearBar() {
    const bar = document.getElementById('volHeatmapYearBar');
    if (!bar) return;
    // Construire la liste des années depuis SESSIONS
    const years = Array.from(new Set(SESSIONS.map(s => s._year))).filter(y => y).sort();
    if (heatmapYear === null) heatmapYear = years[years.length - 1];

    bar.innerHTML = years.map(y =>
      `<button class="heatmap-year-btn ${y === heatmapYear ? 'on' : ''}" data-y="${y}">${y}</button>`
    ).join('');
    bar.querySelectorAll('.heatmap-year-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        heatmapYear = parseInt(btn.dataset.y, 10);
        bar.querySelectorAll('.heatmap-year-btn').forEach(b => b.classList.remove('on'));
        btn.classList.add('on');
        chartVolHeatmap();
      });
    });
  }

  function chartVolHeatmap() {
    disposeVolChart('heatmap');
    const el = document.getElementById('volHeatmap');
    if (!el || heatmapYear === null) return;

    // Construire les données : pour chaque jour de l'année sélectionnée, somme km
    const daily = new Map();
    SESSIONS.forEach(s => {
      if (!s._date || s._date.getFullYear() !== heatmapYear) return;
      const d = startOfDay(s._date);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      daily.set(key, (daily.get(key) || 0) + (s.km || 0));
    });

    // Échelle de couleur dynamique selon le max
    const values = Array.from(daily.values());
    const maxKm = values.length ? Math.max(...values) : 30;

    // Format pour ECharts heatmap calendar
    const data = Array.from(daily.entries()).map(([k, v]) => [k, Math.round(v * 10) / 10]);

    const dom = volCharts.heatmap = echarts.init(el);

    // Échelle quantifiée (piecewise) pour une lecture franche : un jour off
    // est gris foncé, dès 1km on bascule sur un bleu reconnaissable, etc.
    // Les paliers sont adaptés à un coureur à volume modéré-élevé : seuils
    // 5/10/15/20/25/30+ km. Pour des profils différents, l'échelle s'auto-
    // adapte au max observé en pliant les paliers (généric pour duplicabilité).
    const upperBound = Math.max(30, Math.ceil(maxKm));
    // 6 paliers + le zero, calculés en proportion du max
    const paliers = [
      { min: 0.01, max: upperBound * 0.15, color: '#dbeafe', label: '0-' + Math.round(upperBound * 0.15) },
      { min: upperBound * 0.15, max: upperBound * 0.30, color: '#93c5fd', label: '' },
      { min: upperBound * 0.30, max: upperBound * 0.50, color: '#5b8af5', label: '' },
      { min: upperBound * 0.50, max: upperBound * 0.70, color: '#22d3a7', label: '' },
      { min: upperBound * 0.70, max: upperBound * 0.85, color: '#10b981', label: '' },
      { min: upperBound * 0.85, color: '#047857', label: Math.round(upperBound * 0.85) + '+' },
    ];

    dom.setOption({
      textStyle: CHART_THEME.textStyle,
      tooltip: { ...CHART_THEME.tooltip,
                 formatter: p => {
                   const dateLabel = new Date(p.data[0]).toLocaleString('fr-FR',
                     { weekday: 'short', day: 'numeric', month: 'short' });
                   return `<b>${dateLabel}</b><br/>${p.data[1].toFixed(1)} km`;
                 } },
      visualMap: {
        type: 'piecewise',
        orient: 'horizontal',
        left: 'center', bottom: 0,
        textStyle: { color: '#64748b', fontSize: 10 },
        pieces: paliers,
        showLabel: true,
      },
      calendar: {
        top: 30, left: 40, right: 20, bottom: 40,
        range: heatmapYear,
        cellSize: ['auto', 14],
        splitLine: { show: false },
        // Cellule vide bien plus foncée pour la distinguer franchement
        // d'un jour avec ne serait-ce que 1km de footing
        itemStyle: { borderColor: '#fff', borderWidth: 2, color: '#e2e8f0' },
        yearLabel: { show: false },
        monthLabel: { color: '#94a3b8', fontSize: 10, nameMap: 'fr' },
        dayLabel: { color: '#94a3b8', fontSize: 9, firstDay: 1,
                    nameMap: ['D','L','M','M','J','V','S'] },
      },
      series: { type: 'heatmap', coordinateSystem: 'calendar', data },
    });
  }

  function renderVolumeTab() {
    const filtered = getFilteredSessions();
    chartVolWeeklyStacked(filtered);
    chartVolMonthly(filtered);
    chartVolTypeDist(filtered);
    // chartVolCumulative est figé (toutes années) — pas à recalculer sur filtre
    chartVolHeatmap();
  }

  function initVolumeTab() {
    // Initialisation des 5 vues + bar année heatmap
    setupHeatmapYearBar();
    renderVolumeTab();
    chartVolCumulative(); // une seule fois au load
  }

  // ============================================================================
  // ===== 13. MODULE SÉANCES ===================================================
  // ============================================================================
  //
  // Table de toutes les séances avec :
  //   - Filtres : recherche libre, type (multi), km min/max, FC min/max + filtre année global
  //   - Tri par colonne (clic header)
  //   - Pagination 50/page
  //   - Clic ligne → modal détail avec graphiques (allure×FC, cadence) si blocs présents
  //   - Icône piste 🏟 sur le badge type quand sess.track === true

  const SESS_PAGE_SIZE = 50;
  const sessState = {
    page: 1,
    sortKey: 'date',
    sortDir: 'desc',   // 'asc' | 'desc'
    search: '',
    typeFilter: new Set(),   // vide = tous
    kmMin: null,
    kmMax: null,
    fcMin: null,
    fcMax: null,
  };

  function sessApplyFilters() {
    let arr = getFilteredSessions().slice();

    // Search
    if (sessState.search) {
      const q = sessState.search.toLowerCase();
      arr = arr.filter(s => (s.t || '').toLowerCase().includes(q));
    }
    // Type filter
    if (sessState.typeFilter.size > 0) {
      arr = arr.filter(s => sessState.typeFilter.has(s.tp));
    }
    // Range filters
    if (sessState.kmMin != null) arr = arr.filter(s => s.km >= sessState.kmMin);
    if (sessState.kmMax != null) arr = arr.filter(s => s.km <= sessState.kmMax);
    if (sessState.fcMin != null) arr = arr.filter(s => s.fc && s.fc >= sessState.fcMin);
    if (sessState.fcMax != null) arr = arr.filter(s => s.fc && s.fc <= sessState.fcMax);

    // Sort
    const key = sessState.sortKey, dir = sessState.sortDir === 'asc' ? 1 : -1;
    arr.sort((a, b) => {
      let va, vb;
      if (key === 'date') { va = a._date; vb = b._date; }
      else if (key === 'tp') { va = a.tp || ''; vb = b.tp || ''; }
      else { va = a[key] || 0; vb = b[key] || 0; }
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });

    return arr;
  }

  function renderSessTypeFilter() {
    const wrap = document.getElementById('sessTypeFilter');
    if (!wrap) return;
    const counts = new Map();
    SESSIONS.forEach(s => counts.set(s.tp || 'other', (counts.get(s.tp || 'other') || 0) + 1));
    const types = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
    wrap.innerHTML = types.map(([tp, n]) => {
      const active = sessState.typeFilter.has(tp);
      return `<button class="sess-type-btn ${active ? 'on' : ''}" data-tp="${escapeHtml(tp)}" style="--c:${typeColor(tp)}">
        ${escapeHtml(typeLabel(tp))} <span class="sess-type-count">${n}</span>
      </button>`;
    }).join('');
    wrap.querySelectorAll('.sess-type-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tp = btn.dataset.tp;
        if (sessState.typeFilter.has(tp)) sessState.typeFilter.delete(tp);
        else sessState.typeFilter.add(tp);
        sessState.page = 1;
        renderSessTypeFilter();
        renderSessTable();
      });
    });
  }

  function renderSessTable() {
    const tbody = document.getElementById('sessTableBody');
    const summary = document.getElementById('sessSummary');
    const pagination = document.getElementById('sessPagination');
    if (!tbody) return;

    const filtered = sessApplyFilters();
    const totalCount = filtered.length;
    const totalKm = filtered.reduce((a, s) => a + (s.km || 0), 0);

    summary.textContent = `${totalCount} séances · ${Math.round(totalKm).toLocaleString('fr-FR')} km`;

    const totalPages = Math.max(1, Math.ceil(totalCount / SESS_PAGE_SIZE));
    if (sessState.page > totalPages) sessState.page = totalPages;
    const start = (sessState.page - 1) * SESS_PAGE_SIZE;
    const slice = filtered.slice(start, start + SESS_PAGE_SIZE);

    if (slice.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#94a3b8;padding:24px">Aucune séance ne correspond aux filtres.</td></tr>';
    } else {
      tbody.innerHTML = slice.map((s, i) => {
        const trackIcon = s.track ? '<span class="sess-track" title="Séance sur piste">🏟</span>' : '';
        return `<tr class="sess-row" data-idx="${start + i}">
          <td>${s.d}<span class="sess-time">${s.h || ''}</span></td>
          <td><span class="tag tag-${s.tp}" style="--c:${typeColor(s.tp)}">${typeLabel(s.tp)}</span>${trackIcon}</td>
          <td class="mono">${(s.km || 0).toFixed(2)} km</td>
          <td class="mono">${s.dur || fmtDur(s.dur_s)}</td>
          <td class="mono">${s.a || (s.ps ? fmtPace(s.ps) + '/km' : '—')}</td>
          <td class="mono">${s.fc ? s.fc + ' bpm' : '—'}</td>
          <td class="sess-title">${escapeHtml(s.t || '')}</td>
        </tr>`;
      }).join('');

      // Bind clicks
      tbody.querySelectorAll('.sess-row').forEach(tr => {
        tr.addEventListener('click', () => {
          const idx = parseInt(tr.dataset.idx, 10);
          openSessModal(filtered[idx]);
        });
      });
    }

    // Pagination
    if (totalPages <= 1) {
      pagination.innerHTML = '';
    } else {
      const prev = sessState.page > 1
        ? `<button class="sess-page-btn" data-page="${sessState.page - 1}">‹ Préc.</button>`
        : `<button class="sess-page-btn" disabled>‹ Préc.</button>`;
      const next = sessState.page < totalPages
        ? `<button class="sess-page-btn" data-page="${sessState.page + 1}">Suiv. ›</button>`
        : `<button class="sess-page-btn" disabled>Suiv. ›</button>`;
      pagination.innerHTML = `${prev}
        <span class="sess-page-info">Page ${sessState.page} / ${totalPages}</span>
        ${next}`;
      pagination.querySelectorAll('.sess-page-btn[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
          sessState.page = parseInt(btn.dataset.page, 10);
          renderSessTable();
        });
      });
    }

    // Update sort arrows
    document.querySelectorAll('#sessTableHead th[data-sort]').forEach(th => {
      const arrow = th.querySelector('.sort-arrow');
      if (!arrow) return;
      if (th.dataset.sort === sessState.sortKey) {
        arrow.textContent = sessState.sortDir === 'asc' ? '↑' : '↓';
        arrow.style.opacity = 1;
      } else {
        arrow.textContent = '↕';
        arrow.style.opacity = 0.3;
      }
    });
  }

  function setupSessFilters() {
    document.getElementById('sessSearch')?.addEventListener('input', (e) => {
      sessState.search = e.target.value.trim();
      sessState.page = 1;
      renderSessTable();
    });

    const bindNumberInput = (id, key) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', () => {
        const v = el.value === '' ? null : parseFloat(el.value);
        sessState[key] = (v === null || isNaN(v)) ? null : v;
        sessState.page = 1;
        renderSessTable();
      });
    };
    bindNumberInput('sessKmMin', 'kmMin');
    bindNumberInput('sessKmMax', 'kmMax');
    bindNumberInput('sessFcMin', 'fcMin');
    bindNumberInput('sessFcMax', 'fcMax');

    document.getElementById('sessReset')?.addEventListener('click', () => {
      sessState.search = '';
      sessState.typeFilter.clear();
      sessState.kmMin = sessState.kmMax = sessState.fcMin = sessState.fcMax = null;
      sessState.page = 1;
      document.getElementById('sessSearch').value = '';
      document.getElementById('sessKmMin').value = '';
      document.getElementById('sessKmMax').value = '';
      document.getElementById('sessFcMin').value = '';
      document.getElementById('sessFcMax').value = '';
      renderSessTypeFilter();
      renderSessTable();
    });

    // Tri colonnes
    document.querySelectorAll('#sessTableHead th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (sessState.sortKey === key) {
          sessState.sortDir = sessState.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          sessState.sortKey = key;
          sessState.sortDir = key === 'date' ? 'desc' : 'desc';
        }
        renderSessTable();
      });
    });
  }

  // ---- Modal détail séance ----
  let sessModalCharts = [];

  function openSessModal(sess) {
    const modal = document.getElementById('sessModal');
    const body = document.getElementById('sessModalBody');
    if (!modal || !body) return;

    // Disposer les anciens charts éventuels
    sessModalCharts.forEach(c => c && c.dispose());
    sessModalCharts = [];

    const trackBadge = sess.track ? '<span class="sess-track-badge">🏟 Piste</span>' : '';
    const dur = sess.dur || fmtDur(sess.dur_s);
    const allure = sess.a || (sess.ps ? fmtPace(sess.ps) + '/km' : '—');

    let kpisHtml = `<div class="sess-modal-kpis">
      <div class="smk"><span class="smk-l">Distance</span><span class="smk-v">${(sess.km || 0).toFixed(2)} km</span></div>
      <div class="smk"><span class="smk-l">Durée</span><span class="smk-v">${dur}</span></div>
      <div class="smk"><span class="smk-l">Allure</span><span class="smk-v">${allure}</span></div>
      <div class="smk"><span class="smk-l">Vitesse</span><span class="smk-v">${sess.v ? sess.v.toFixed(2) + ' km/h' : '—'}</span></div>
      <div class="smk"><span class="smk-l">FC moy</span><span class="smk-v">${sess.fc ? sess.fc + ' bpm' : '—'}</span></div>
      <div class="smk"><span class="smk-l">Type</span><span class="smk-v">${typeLabel(sess.tp)} ${trackBadge}</span></div>
    </div>`;

    const blocs = sess.b || [];
    const hasBlocs = blocs.length > 0;

    let chartsHtml = '';
    let blocsTableHtml = '';
    if (hasBlocs) {
      chartsHtml = `<div class="sess-modal-charts">
        <div class="sess-modal-chart-card">
          <div class="sess-modal-chart-title">Allure et FC par km</div>
          <div class="sess-modal-chart" id="sessModalPaceFc" style="height:240px"></div>
        </div>
        <div class="sess-modal-chart-card">
          <div class="sess-modal-chart-title">Cadence par km</div>
          <div class="sess-modal-chart" id="sessModalCadence" style="height:200px"></div>
        </div>
      </div>`;

      // Tableau des blocs km par km
      // Colonnes : N° / Distance / Durée / Allure / FC / Cadence / Intent
      // Intent (active/warmup/cooldown/rest) permet de voir d'un coup d'œil
      // les blocs de récup vs travail dans un fractionné.
      const intentLabels = {
        active: 'Actif', warmup: 'Échauf.', cooldown: 'Récup.',
        rest: 'Repos', interval: 'Effort',
      };
      const intentColors = {
        active: '#5b8af5', warmup: '#22d3a7', cooldown: '#94a3b8',
        rest: '#cbd5e1', interval: '#ef5b5b',
      };
      const rows = blocs.map(b => {
        const intentLbl = intentLabels[b.intent] || b.intent || '—';
        const intentClr = intentColors[b.intent] || '#94a3b8';
        return `<tr>
          <td class="mono">${b.n}</td>
          <td class="mono">${(b.km || 0).toFixed(2)}</td>
          <td class="mono">${b.dur || fmtDur(b.dur_s)}</td>
          <td class="mono">${b.a || (b.ps ? fmtPace(b.ps) + '/km' : '—')}</td>
          <td class="mono">${b.fc || '—'}</td>
          <td class="mono">${b.ca || '—'}</td>
          <td><span class="bloc-intent" style="background:${intentClr}">${intentLbl}</span></td>
        </tr>`;
      }).join('');

      blocsTableHtml = `<div class="sess-modal-chart-card sess-blocs-card">
        <div class="sess-modal-chart-title">Détail des ${blocs.length} blocs</div>
        <div class="sess-blocs-scroll">
          <table class="sess-blocs-table">
            <thead>
              <tr>
                <th>#</th><th>Dist.</th><th>Durée</th><th>Allure</th>
                <th>FC</th><th>Cadence</th><th>Intent</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
    } else {
      chartsHtml = '<p class="sess-modal-empty">Pas de blocs km enregistrés pour cette séance.</p>';
    }

    body.innerHTML = `
      <div class="sess-modal-head">
        <div class="sess-modal-date">${sess.d}${sess.h ? ' à ' + sess.h : ''}</div>
        <div class="sess-modal-title">${escapeHtml(sess.t || '')}</div>
      </div>
      ${kpisHtml}
      ${chartsHtml}
      ${blocsTableHtml}
    `;

    document.getElementById('sessModalTitle').textContent =
      `${sess.d} · ${typeLabel(sess.tp)} · ${(sess.km || 0).toFixed(2)} km`;

    modal.hidden = false;
    document.body.style.overflow = 'hidden';

    // Construction charts
    if (hasBlocs) {
      const xLabels = blocs.map(b => 'km ' + b.n);
      const paces = blocs.map(b => b.ps || null);
      const fcs   = blocs.map(b => b.fc || null);
      const cads  = blocs.map(b => b.ca || null);

      setTimeout(() => {
        const paceFcEl = document.getElementById('sessModalPaceFc');
        if (paceFcEl) {
          const validPaces = paces.filter(v => v != null);
          const minPace = validPaces.length ? Math.min(...validPaces) : 200;
          const maxPace = validPaces.length ? Math.max(...validPaces) : 400;
          const yPaceMin = Math.floor((minPace - 10) / 5) * 5;
          const yPaceMax = Math.ceil((maxPace + 10) / 5) * 5;
          const c = echarts.init(paceFcEl);
          c.setOption({
            textStyle: CHART_THEME.textStyle,
            grid: { left: 50, right: 50, top: 30, bottom: 32, containLabel: true },
            legend: { data: ['Allure', 'FC'], top: 0, textStyle: { color: INK2, fontSize: 11 } },
            tooltip: {
              ...CHART_THEME.tooltip, trigger: 'axis',
              formatter: (params) => {
                let s = '<b>' + params[0].axisValue + '</b><br/>';
                params.forEach(p => {
                  if (p.seriesName === 'Allure' && p.data != null) s += `Allure : ${fmtPace(p.data)}/km<br/>`;
                  else if (p.seriesName === 'FC' && p.data != null) s += `FC : ${p.data} bpm<br/>`;
                });
                return s;
              },
            },
            xAxis: { ...CHART_THEME.xAxis, type: 'category', data: xLabels,
                     axisLabel: { ...CHART_THEME.xAxis.axisLabel,
                                  interval: Math.max(0, Math.floor(blocs.length / 10) - 1) } },
            yAxis: [
              { ...CHART_THEME.yAxis, type: 'value', name: 'Allure',
                min: yPaceMin, max: yPaceMax,
                nameTextStyle: { color: '#94a3b8', fontSize: 10 },
                axisLabel: { ...CHART_THEME.yAxis.axisLabel,
                             formatter: v => Math.floor(v/60) + "'" + String(Math.round(v%60)).padStart(2,'0') } },
              { ...CHART_THEME.yAxis, type: 'value', name: 'FC',
                position: 'right',
                nameTextStyle: { color: '#94a3b8', fontSize: 10 },
                splitLine: { show: false } },
            ],
            series: [
              { name: 'Allure', type: 'bar', yAxisIndex: 0, data: paces,
                itemStyle: {
                  color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                           colorStops: [{ offset: 0, color: '#f0923e' }, { offset: 1, color: '#22d3a7' }] },
                  borderRadius: [3, 3, 0, 0],
                } },
              { name: 'FC', type: 'line', yAxisIndex: 1, smooth: true, data: fcs,
                symbol: 'circle', symbolSize: 5,
                lineStyle: { width: 2.4, color: '#ef5b5b' },
                itemStyle: { color: '#ef5b5b' } },
            ],
            animationDuration: 500,
          });
          sessModalCharts.push(c);
        }

        const cadEl = document.getElementById('sessModalCadence');
        if (cadEl) {
          const validCads = cads.filter(v => v != null);
          const minCad = validCads.length ? Math.min(...validCads) : 150;
          const maxCad = validCads.length ? Math.max(...validCads) : 200;
          const yMin = Math.max(140, Math.floor(minCad / 5) * 5 - 5);
          const yMax = Math.ceil(maxCad / 5) * 5 + 5;
          const c = echarts.init(cadEl);
          c.setOption({
            textStyle: CHART_THEME.textStyle,
            grid: { left: 40, right: 16, top: 16, bottom: 32, containLabel: true },
            tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                       formatter: p => p[0].data != null
                         ? `<b>${p[0].axisValue}</b><br/>${p[0].data} ppm` : `<b>${p[0].axisValue}</b><br/>—` },
            xAxis: { ...CHART_THEME.xAxis, type: 'category', data: xLabels,
                     axisLabel: { ...CHART_THEME.xAxis.axisLabel,
                                  interval: Math.max(0, Math.floor(blocs.length / 10) - 1) } },
            yAxis: { ...CHART_THEME.yAxis, type: 'value', min: yMin, max: yMax,
                     name: 'ppm', nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
            series: [{
              type: 'bar', data: cads,
              itemStyle: {
                color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                         colorStops: [{ offset: 0, color: '#9b6dff' }, { offset: 1, color: '#5b8af5' }] },
                borderRadius: [3, 3, 0, 0],
              },
            }],
            animationDuration: 500,
          });
          sessModalCharts.push(c);
        }
      }, 80);
    }
  }

  function setupSessModal() {
    const modal = document.getElementById('sessModal');
    const close1 = document.getElementById('sessModalClose');
    const close2 = document.getElementById('sessModalCloseFoot');
    if (!modal) return;
    const closeFn = () => {
      sessModalCharts.forEach(c => c && c.dispose());
      sessModalCharts = [];
      modal.hidden = true;
      document.body.style.overflow = '';
    };
    close1?.addEventListener('click', closeFn);
    close2?.addEventListener('click', closeFn);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeFn(); });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modal.hidden) closeFn();
    });
  }

  function initSessTab() {
    renderSessTypeFilter();
    setupSessFilters();
    setupSessModal();
    renderSessTable();
  }

  // ============================================================================
  // ===== 14. MODULE EFFICACITÉ AÉROBIE ========================================
  // ============================================================================
  //
  // 4 vues, toutes calculées en JS depuis les blocs des sessions :
  //   - Scatter FC × Allure sur footings/endurance (filtre temporel)
  //   - Dérive cardiaque sur sorties longues (delta FC moitié 2 vs moitié 1)
  //   - Balance L/R sur marathons + sorties longues (moy + écart-type)
  //   - Temps de contact (ct) sur marathons + sorties longues (moy + CV)
  //
  // Note duplicabilité : aucun seuil hardcodé spécifique à un profil. Les
  // filtres "aérobie" se basent sur le `tp` calculé par parser_fit.py.

  const aeroCharts = {};

  function disposeAeroChart(key) {
    if (aeroCharts[key]) { aeroCharts[key].dispose(); aeroCharts[key] = null; }
  }

  // ---- 1. Scatter FC × Allure ----
  // On affiche uniquement footings + endurance (séances aérobies pures)
  // pour éviter que les fractionnés ne polluent le nuage.
  // Couleur : dégradé temporel (anciens = clair, récents = foncés).
  function chartAeroScatter(filteredSessions) {
    disposeAeroChart('scatter');
    const el = document.getElementById('aeroScatter');
    if (!el) return;

    const aerobic = filteredSessions.filter(s =>
      ['footing', 'endurance'].includes(s.tp) && s.ps && s.fc && s.km >= 3
    );
    if (aerobic.length < 5) {
      el.innerHTML = '<p style="color:#94a3b8;padding:20px;text-align:center">Pas assez de séances aérobies pour cette période (minimum 5 nécessaires).</p>';
      return;
    }

    // Tri chrono pour gradient de couleur
    aerobic.sort((a, b) => a._date - b._date);
    const minDate = aerobic[0]._date.getTime();
    const maxDate = aerobic[aerobic.length - 1]._date.getTime();
    const range = maxDate - minDate || 1;

    // Découper en 4 buckets temporels pour lisibilité légende
    const bucketCount = 4;
    const buckets = Array.from({ length: bucketCount }, () => []);
    aerobic.forEach(s => {
      const t = (s._date.getTime() - minDate) / range;
      const idx = Math.min(bucketCount - 1, Math.floor(t * bucketCount));
      buckets[idx].push([s.ps, s.fc, s.d, s.km]);
    });

    // Labels temporels par bucket
    const bucketLabels = buckets.map((bucket, i) => {
      if (!bucket.length) return `Période ${i + 1}`;
      // Première et dernière date du bucket
      const dates = bucket.map(p => p[2]);
      return `${dates[0]} → ${dates[dates.length - 1]}`;
    });

    const colors = ['#cbd5e1', '#94a3b8', '#5b8af5', '#22d3a7'];

    const series = buckets.map((bucket, i) => ({
      name: bucketLabels[i],
      type: 'scatter',
      data: bucket,
      symbolSize: 8,
      itemStyle: { color: colors[i], opacity: 0.7 },
    }));

    const dom = aeroCharts.scatter = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      legend: { top: 0, textStyle: { color: INK2, fontSize: 11 } },
      grid: { left: 50, right: 20, top: 36, bottom: 40, containLabel: true },
      tooltip: {
        ...CHART_THEME.tooltip, trigger: 'item',
        formatter: p => `<b>${p.data[2]}</b><br/>
          ${p.data[3].toFixed(1)} km<br/>
          Allure : ${fmtPace(p.data[0])}/km<br/>
          FC : ${p.data[1]} bpm`,
      },
      xAxis: { ...CHART_THEME.xAxis, type: 'value', name: 'Allure (sec/km)', inverse: true,
               nameLocation: 'middle', nameGap: 28, nameTextStyle: { color: '#94a3b8', fontSize: 10 },
               axisLabel: { ...CHART_THEME.xAxis.axisLabel,
                            formatter: v => Math.floor(v/60) + "'" + String(Math.round(v%60)).padStart(2,'0') } },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', name: 'FC (bpm)',
               nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
      series,
      animationDuration: 600,
    });
  }

  // ---- 2. Dérive cardiaque (sorties longues ≥ 60min) ----
  // Pour chaque sortie longue, on découpe les blocs en 2 moitiés (par index
  // ou par temps cumulé) et on compare la FC moyenne. Une dérive > 5 bpm
  // signale de la fatigue cardiaque sur la durée.
  function renderAeroDriftTable() {
    const wrap = document.getElementById('aeroDriftTable');
    if (!wrap) return;

    const filtered = getFilteredSessions().filter(s =>
      s.dur_s >= 3600 && s.b && s.b.length >= 8 &&
      ['endurance', 'sortie_longue', 'marathon'].includes(s.tp)
    );

    if (filtered.length === 0) {
      wrap.innerHTML = '<p class="race-table-empty">Aucune sortie longue ≥ 60min pour cette période.</p>';
      return;
    }

    filtered.sort((a, b) => b._date - a._date);

    const rows = filtered.slice(0, 30).map(s => {
      const blocs = s.b;
      // Découper par TEMPS cumulé (et non par index) pour mieux gérer les
      // blocs non uniformes (fin de séance avec bloc résiduel).
      const totalSec = blocs.reduce((a, b) => a + (b.dur_s || 0), 0);
      const halfSec = totalSec / 2;

      let cumSec = 0;
      const half1 = [], half2 = [];
      for (const b of blocs) {
        const blocCenter = cumSec + (b.dur_s || 0) / 2;
        if (blocCenter < halfSec) half1.push(b);
        else half2.push(b);
        cumSec += b.dur_s || 0;
      }

      const fcAvg = (arr) => {
        let w = 0, sum = 0;
        arr.forEach(b => {
          if (b.fc && b.dur_s) { sum += b.fc * b.dur_s; w += b.dur_s; }
        });
        return w > 0 ? sum / w : null;
      };
      const fc1 = fcAvg(half1);
      const fc2 = fcAvg(half2);
      if (fc1 == null || fc2 == null) return null;
      const drift = fc2 - fc1;

      const driftCls = drift < 2 ? 'drift-low' : drift < 6 ? 'drift-mid' : 'drift-high';

      return `<tr>
        <td>${s.d}<span class="sess-time">${s.h || ''}</span></td>
        <td><span class="tag" style="--c:${typeColor(s.tp)}">${typeLabel(s.tp)}</span></td>
        <td class="mono">${(s.km || 0).toFixed(1)} km</td>
        <td class="mono">${fmtDur(s.dur_s)}</td>
        <td class="mono">${Math.round(fc1)} bpm</td>
        <td class="mono">${Math.round(fc2)} bpm</td>
        <td class="mono drift-cell ${driftCls}">${drift >= 0 ? '+' : ''}${drift.toFixed(1)} bpm</td>
      </tr>`;
    }).filter(Boolean).join('');

    wrap.innerHTML = `<div class="aero-table-scroll">
      <table class="aero-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Distance</th>
            <th>Durée</th>
            <th>FC moy 1<sup>ère</sup> moitié</th>
            <th>FC moy 2<sup>nde</sup> moitié</th>
            <th>Dérive</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="aero-table-legend">
        <span class="drift-low">&lt; 2 bpm</span> excellent endurance ·
        <span class="drift-mid">2-6 bpm</span> normal ·
        <span class="drift-high">&gt; 6 bpm</span> fatigue ou hydratation
      </p>
    </div>`;
  }

  // ---- 3. Balance L/R ----
  // Marathons + SL récents. Affichage : moyenne pondérée + écart-type
  // intra-séance pour mesurer la stabilité.
  function renderAeroBalanceTable() {
    const wrap = document.getElementById('aeroBalanceTable');
    if (!wrap) return;

    const filtered = getFilteredSessions().filter(s =>
      s.b && s.b.length >= 5 &&
      ['marathon', 'sortie_longue', 'semi'].includes(s.tp) &&
      s.b.some(b => b.bal != null)
    );

    if (filtered.length === 0) {
      wrap.innerHTML = '<p class="race-table-empty">Aucune séance marathon/semi/SL avec balance L/R enregistrée pour cette période.</p>';
      return;
    }

    filtered.sort((a, b) => b._date - a._date);

    const rows = filtered.slice(0, 25).map(s => {
      const balsWithDur = s.b.filter(b => b.bal != null && b.dur_s).map(b => ({ v: b.bal, w: b.dur_s }));
      if (!balsWithDur.length) return null;

      const totW = balsWithDur.reduce((a, x) => a + x.w, 0);
      const wAvg = balsWithDur.reduce((a, x) => a + x.v * x.w, 0) / totW;
      // Écart-type pondéré simple (intra-séance)
      const variance = balsWithDur.reduce((a, x) => a + Math.pow(x.v - wAvg, 2) * x.w, 0) / totW;
      const std = Math.sqrt(variance);

      // Lecture : 50% = parfait équilibre, < 50% = pied gauche dominant, > 50% = pied droit dominant.
      // L'écart-type signale la stabilité : < 0.8 = très stable, > 2 = très variable.
      const deltaFromBalance = wAvg - 50;
      const dominantSide = Math.abs(deltaFromBalance) < 0.3 ? 'équilibré' :
                           deltaFromBalance > 0 ? '→ droit' : '← gauche';
      const stdCls = std < 1.0 ? 'std-low' : std < 1.8 ? 'std-mid' : 'std-high';

      return `<tr>
        <td>${s.d}<span class="sess-time">${s.h || ''}</span></td>
        <td><span class="tag" style="--c:${typeColor(s.tp)}">${typeLabel(s.tp)}</span></td>
        <td class="mono">${(s.km || 0).toFixed(1)} km</td>
        <td class="mono">${wAvg.toFixed(2)}%</td>
        <td class="mono balance-side">${dominantSide}${Math.abs(deltaFromBalance) >= 0.3 ? ' (' + Math.abs(deltaFromBalance).toFixed(2) + ' pts)' : ''}</td>
        <td class="mono ${stdCls}">± ${std.toFixed(2)}</td>
      </tr>`;
    }).filter(Boolean).join('');

    wrap.innerHTML = `<div class="aero-table-scroll">
      <table class="aero-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Distance</th>
            <th>Balance moy</th>
            <th>Dominance</th>
            <th>Stabilité (σ)</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="aero-table-legend">
        Balance moyenne : 50% = équilibre parfait. Dominance affichée à partir de 0,3 point d'écart.
        Stabilité (écart-type intra-séance) : <span class="std-low">&lt; 1,0</span> très stable ·
        <span class="std-mid">1,0-1,8</span> normal ·
        <span class="std-high">&gt; 1,8</span> variable (déséquilibre sur certains blocs).
      </p>
    </div>`;
  }

  // ---- 4. Temps de contact au sol (ct) ----
  function renderAeroContactTable() {
    const wrap = document.getElementById('aeroContactTable');
    if (!wrap) return;

    const filtered = getFilteredSessions().filter(s =>
      s.b && s.b.length >= 5 &&
      ['marathon', 'sortie_longue', 'semi'].includes(s.tp) &&
      s.b.some(b => b.ct != null)
    );

    if (filtered.length === 0) {
      wrap.innerHTML = '<p class="race-table-empty">Aucune séance avec temps de contact enregistré pour cette période.</p>';
      return;
    }

    filtered.sort((a, b) => b._date - a._date);

    const rows = filtered.slice(0, 25).map(s => {
      const ctsWithDur = s.b.filter(b => b.ct != null && b.dur_s).map(b => ({ v: b.ct, w: b.dur_s }));
      if (!ctsWithDur.length) return null;

      const totW = ctsWithDur.reduce((a, x) => a + x.w, 0);
      const wAvg = ctsWithDur.reduce((a, x) => a + x.v * x.w, 0) / totW;
      const variance = ctsWithDur.reduce((a, x) => a + Math.pow(x.v - wAvg, 2) * x.w, 0) / totW;
      const std = Math.sqrt(variance);
      const cv = wAvg > 0 ? (std / wAvg) * 100 : 0;

      // Plages indicatives pour un coureur entraîné :
      //   < 200ms = excellent (foulée dynamique)
      //   200-230ms = normal
      //   > 230ms = pied lourd
      const ctCls = wAvg < 200 ? 'ct-good' : wAvg < 230 ? 'ct-mid' : 'ct-high';
      const cvCls = cv < 3 ? 'std-low' : cv < 6 ? 'std-mid' : 'std-high';

      return `<tr>
        <td>${s.d}<span class="sess-time">${s.h || ''}</span></td>
        <td><span class="tag" style="--c:${typeColor(s.tp)}">${typeLabel(s.tp)}</span></td>
        <td class="mono">${(s.km || 0).toFixed(1)} km</td>
        <td class="mono ${ctCls}">${Math.round(wAvg)} ms</td>
        <td class="mono">± ${Math.round(std)} ms</td>
        <td class="mono ${cvCls}">${cv.toFixed(1)}%</td>
      </tr>`;
    }).filter(Boolean).join('');

    wrap.innerHTML = `<div class="aero-table-scroll">
      <table class="aero-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Distance</th>
            <th>Temps de contact moy</th>
            <th>Écart-type</th>
            <th>Variabilité (CV)</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="aero-table-legend">
        Temps de contact : <span class="ct-good">&lt; 200 ms</span> dynamique ·
        <span class="ct-mid">200-230 ms</span> normal ·
        <span class="ct-high">&gt; 230 ms</span> pied lourd.
        Variabilité (CV) : <span class="std-low">&lt; 3%</span> très stable ·
        <span class="std-high">&gt; 6%</span> instable (fatigue ou allure très variable).
      </p>
    </div>`;
  }

  function renderAeroTab() {
    const filtered = getFilteredSessions();
    chartAeroScatter(filtered);
    renderAeroDriftTable();
    renderAeroBalanceTable();
    renderAeroContactTable();
  }

  function initAeroTab() {
    renderAeroTab();
  }

  // ============================================================================
  // ===== 15. MODULE PROGRESSION VMA ===========================================
  // ============================================================================
  //
  // Le moteur Python performance.compute_history doit produire une série
  // {timestamp, vma, paces, confidence} pour des fenêtres glissantes de 30j
  // tous les 14 jours. Le payload arrive dans RAW.performance_history.
  //
  // Si performance_history est absent (parser non patché), on dégrade
  // gracieusement avec un message d'attente.

  const progCharts = {};

  function disposeProgChart(key) {
    if (progCharts[key]) { progCharts[key].dispose(); progCharts[key] = null; }
  }

  function chartProgVmaHistory() {
    disposeProgChart('vma');
    const el = document.getElementById('progVmaHistory');
    if (!el) return;

    const history = RAW.performance_history;
    if (!history || !Array.isArray(history) || history.length < 2) {
      el.innerHTML = '<p style="color:#94a3b8;padding:40px;text-align:center">' +
        'Historique VMA non disponible. Régénérez le dashboard avec une version récente du moteur de performance.</p>';
      return;
    }

    const data = history.filter(h => h.vma).map(h => [h.date, h.vma]);
    const confidenceData = history.filter(h => h.vma).map(h => h.confidence || 100);

    // Annotations : courses officielles
    const racesAnnotations = (RACES.past_races || [])
      .filter(r => r.distance_key === 'marathon' || r.distance_key === 'semi')
      .map(r => {
        // start_time = ISO "2026-04-12T08:00" → on prend juste la date
        const d = r.start_time.split('T')[0];
        return {
          xAxis: d,
          label: { show: true, formatter: r.name.replace(/Marathon de |Marathon d'/, '').slice(0, 14),
                   fontSize: 9, color: INK2, position: 'insideEndTop' },
          lineStyle: { color: '#5b8af5', width: 1.5, type: 'dashed' },
        };
      });

    const dom = progCharts.vma = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      grid: { left: 40, right: 16, top: 30, bottom: 40, containLabel: true },
      tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                 formatter: (params) => {
                   const p = params[0];
                   const idx = history.findIndex(h => h.date === p.axisValue);
                   const conf = idx >= 0 ? history[idx].confidence : null;
                   return `<b>${p.axisValue}</b><br/>VMA : ${p.data[1].toFixed(2)} km/h${conf != null ? '<br/>Confiance : ' + conf + '%' : ''}`;
                 } },
      xAxis: { ...CHART_THEME.xAxis, type: 'time' },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', name: 'VMA (km/h)',
               nameTextStyle: { color: '#94a3b8', fontSize: 10 },
               scale: true },
      series: [{
        name: 'VMA',
        type: 'line', smooth: true, data,
        symbol: 'circle', symbolSize: 5,
        lineStyle: { width: 2.5, color: '#5b8af5' },
        itemStyle: { color: '#5b8af5' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                              colorStops: [{ offset: 0, color: 'rgba(91,138,245,0.25)' },
                                           { offset: 1, color: 'rgba(91,138,245,0)' }] } },
        markLine: racesAnnotations.length > 0 ? {
          symbol: 'none',
          silent: true,
          data: racesAnnotations,
        } : undefined,
        animationDuration: 800,
      }],
    });
  }

  function chartProgPacesHistory() {
    disposeProgChart('paces');
    const el = document.getElementById('progPacesHistory');
    if (!el) return;

    const history = RAW.performance_history;
    if (!history || !Array.isArray(history) || history.length < 2) {
      el.innerHTML = '<p style="color:#94a3b8;padding:40px;text-align:center">' +
        'Historique des allures non disponible.</p>';
      return;
    }

    // Construction des séries : une par allure cible
    const paceKeys = ['marathon', 'semi', 'seuil', '10k'];
    const paceColors = {
      marathon: '#5b8af5', semi: '#22d3a7', seuil: '#f0923e', '10k': '#9b6dff',
    };
    const paceLabels = {
      marathon: 'Marathon', semi: 'Semi', seuil: 'Seuil', '10k': '10K',
    };

    const series = paceKeys.map(k => ({
      name: paceLabels[k],
      type: 'line', smooth: true,
      data: history.filter(h => h.paces && h.paces[k]).map(h => [h.date, h.paces[k]]),
      symbol: 'circle', symbolSize: 4,
      lineStyle: { width: 2, color: paceColors[k] },
      itemStyle: { color: paceColors[k] },
    }));

    const dom = progCharts.paces = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      legend: { top: 0, textStyle: { color: INK2, fontSize: 11 } },
      grid: { left: 60, right: 16, top: 36, bottom: 40, containLabel: true },
      tooltip: {
        ...CHART_THEME.tooltip, trigger: 'axis',
        formatter: (params) => {
          let s = '<b>' + params[0].axisValue + '</b><br/>';
          params.forEach(p => {
            if (p.data) s += `<span style="color:${p.color}">${p.seriesName}</span> : ${fmtPace(p.data[1])}/km<br/>`;
          });
          return s;
        },
      },
      xAxis: { ...CHART_THEME.xAxis, type: 'time' },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', inverse: true,
               name: 'Allure (sec/km)',
               nameTextStyle: { color: '#94a3b8', fontSize: 10 },
               axisLabel: { ...CHART_THEME.yAxis.axisLabel,
                            formatter: v => Math.floor(v/60) + "'" + String(Math.round(v%60)).padStart(2,'0') } },
      series,
      animationDuration: 800,
    });
  }

  function renderProgTab() {
    chartProgVmaHistory();
    chartProgPacesHistory();
  }

  function initProgTab() {
    renderProgTab();
  }

  // ============================================================================
  // ===== 16. MODULE CHARGE & RISQUE ===========================================
  // ============================================================================
  //
  // Calcul du TSS par séance via TRIMP de Banister (pondération FC exponentielle),
  // puis CTL/ATL/TSB par moyennes exponentielles glissantes.
  //
  // Formule TRIMP de Banister :
  //   hr_ratio = (FC_moy - FC_repos) / (FC_max - FC_repos)
  //   TRIMP = durée_min × hr_ratio × 0.64 × e^(1.92 × hr_ratio)  (homme)
  //   ou × 0.86 × e^(1.67 × hr_ratio) (femme)
  //
  // On reste sur la formule homme par défaut. Le 1.92 fait qu'une séance à
  // 90% FCmax compte ~4× plus qu'une à 60% — fidèle à la physiologie.
  //
  // Note duplicabilité : Les zones FC (z1_max..z4_max) sont déjà dans le profil
  // utilisateur. FCmax = z4_max + 5 (approximation). FC_repos = z1_max - 60
  // (approximation). À raffiner via un champ explicite si l'utilisateur le
  // souhaite (voir AUDIT_DUPLICABILITE.md).

  // Récupère FCmax et FCrepos depuis le profil
  function getHrLimits() {
    const zones = PROFILE.hr_zones || {};
    // FCmax : approximation depuis z4_max (typiquement FCmax ≈ z4_max + 5)
    // Sébastien z4_max=175 → FCmax estimée 180 (cohérent avec son âge ~34)
    const fcMax = (zones.z4_max || 180) + 5;
    // FCrepos : approximation conservatrice
    // (à terme, à exposer en config dédiée)
    const fcRest = Math.max(40, (zones.z1_max || 120) - 60);
    return { fcMax, fcRest };
  }

  // TRIMP de Banister pour une séance unique
  function computeTrimpFromHr(durSec, fcAvg, fcMax, fcRest) {
    if (!durSec || !fcAvg || fcAvg <= fcRest || fcMax <= fcRest) return 0;
    const hrRatio = (fcAvg - fcRest) / (fcMax - fcRest);
    if (hrRatio <= 0) return 0;
    const durMin = durSec / 60;
    // Formule homme (Banister 1991)
    return durMin * hrRatio * 0.64 * Math.exp(1.92 * hrRatio);
  }

  // Fallback rTSS basé sur l'allure : approximation depuis l'intensité relative
  // par rapport à l'allure seuil. IF = pace_seuil / pace_séance.
  function computeRtssFromPace(durSec, paceSec, thresholdPaceSec) {
    if (!durSec || !paceSec || !thresholdPaceSec) return 0;
    const intensity = thresholdPaceSec / paceSec;  // IF (plus rapide = > 1)
    // Cap pour éviter les TSS aberrants sur sprints courts
    const ifCapped = Math.min(1.5, intensity);
    return (durSec * ifCapped * ifCapped) / 36;  // ≈ 100 TSS pour 1h à seuil
  }

  // Pour chaque séance, calculer son TSS et l'attacher à la session
  // Retourne un tableau de {date: Date, tss: float, source: 'hr'|'pace'|'none', session: ref}
  function computeTssTimeline() {
    const { fcMax, fcRest } = getHrLimits();
    const thresholdPaceSec = PERF.now && PERF.now.paces ? PERF.now.paces.seuil : null;

    return SESSIONS
      .filter(s => s._date && s.dur_s)
      .map(s => {
        let tss = 0, source = 'none';
        if (s.fc && s.fc > fcRest) {
          tss = computeTrimpFromHr(s.dur_s, s.fc, fcMax, fcRest);
          source = 'hr';
        } else if (s.ps && thresholdPaceSec) {
          tss = computeRtssFromPace(s.dur_s, s.ps, thresholdPaceSec);
          source = 'pace';
        }
        return { date: s._date, tss: Math.round(tss * 10) / 10, source, session: s };
      })
      .sort((a, b) => a.date - b.date);
  }

  // Calcul CTL/ATL/TSB par moyenne exponentielle glissante
  // Formule : EMA(jour n) = TSS(jour n) × (1 - α) + EMA(jour n-1) × α
  // avec α = e^(-1/τ), τ = 42 pour CTL, τ = 7 pour ATL
  // On agrège d'abord en TSS quotidien, puis on déroule l'EMA jour par jour
  function computeCtlAtlSeries(timeline) {
    if (!timeline.length) return [];

    // Agrégation par jour
    const dayMap = new Map();
    timeline.forEach(t => {
      const key = `${t.date.getFullYear()}-${String(t.date.getMonth() + 1).padStart(2,'0')}-${String(t.date.getDate()).padStart(2,'0')}`;
      dayMap.set(key, (dayMap.get(key) || 0) + t.tss);
    });

    // Génération de la grille jour par jour entre première et dernière séance
    const firstDate = timeline[0].date;
    const lastDate = timeline[timeline.length - 1].date;
    const series = [];
    let ctl = 0, atl = 0;
    const alphaCtl = Math.exp(-1 / 42);
    const alphaAtl = Math.exp(-1 / 7);

    const oneDay = 86400000;
    let cursor = new Date(firstDate.getFullYear(), firstDate.getMonth(), firstDate.getDate());
    const endCursor = new Date(lastDate.getFullYear(), lastDate.getMonth(), lastDate.getDate());

    while (cursor <= endCursor) {
      const key = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2,'0')}-${String(cursor.getDate()).padStart(2,'0')}`;
      const tssToday = dayMap.get(key) || 0;

      ctl = tssToday * (1 - alphaCtl) + ctl * alphaCtl;
      atl = tssToday * (1 - alphaAtl) + atl * alphaAtl;

      series.push({
        date: new Date(cursor),
        tss: tssToday,
        ctl: Math.round(ctl * 10) / 10,
        atl: Math.round(atl * 10) / 10,
        tsb: Math.round((ctl - atl) * 10) / 10,
      });

      cursor = new Date(cursor.getTime() + oneDay);
    }

    return series;
  }

  // Détermine le statut/couleur selon le TSB
  // Seuils standards TrainingPeaks :
  //   TSB > +5         → fraîcheur (idéal course)
  //   -10 < TSB ≤ +5   → neutre / forme
  //   -25 < TSB ≤ -10  → fatigue productive
  //   TSB ≤ -25        → risque surentraînement
  function tsbStatus(tsb) {
    if (tsb > 5)   return { label: 'Fraîcheur', cls: 'tsb-fresh', desc: 'Idéal pour une course' };
    if (tsb > -10) return { label: 'Neutre',    cls: 'tsb-neutral', desc: 'Forme équilibrée' };
    if (tsb > -25) return { label: 'Fatigue',   cls: 'tsb-fatigue', desc: 'Charge soutenue, productive' };
    return                  { label: 'À risque', cls: 'tsb-risk',   desc: 'Risque surentraînement/blessure' };
  }

  const chargeCharts = {};

  function disposeChargeChart(key) {
    if (chargeCharts[key]) { chargeCharts[key].dispose(); chargeCharts[key] = null; }
  }

  function renderChargeKPIs(series) {
    const wrap = document.getElementById('chargeKPIs');
    if (!wrap) return;
    if (!series.length) {
      wrap.innerHTML = '<div class="card placeholder">Aucune donnée de charge disponible.</div>';
      return;
    }
    // KPIs du dernier point disponible
    const last = series[series.length - 1];
    const status = tsbStatus(last.tsb);

    const kpis = [
      { v: Math.round(last.ctl), l: 'CTL (forme)', c: 'blue', sub: 'Moyenne exp. 42j' },
      { v: Math.round(last.atl), l: 'ATL (fatigue)', c: 'orange', sub: 'Moyenne exp. 7j' },
      { v: (last.tsb >= 0 ? '+' : '') + Math.round(last.tsb), l: 'TSB (fraîcheur)', c: 'purple', sub: 'CTL − ATL' },
      { v: status.label, l: 'Statut', c: 'cyan', sub: status.desc, isText: true, statusCls: status.cls },
    ];

    wrap.innerHTML = kpis.map(k =>
      `<div class="kpi ${k.statusCls || ''}" data-c="${k.c}">
        <div class="label">${k.l}</div>
        <div class="value ${k.isText ? 'value-text' : ''}">${k.v}</div>
        <div class="sub">${k.sub}</div>
      </div>`
    ).join('');
  }

  function chartCharge(series) {
    disposeChargeChart('main');
    const el = document.getElementById('chargeChart');
    if (!el) return;
    if (!series.length) {
      el.innerHTML = '<p style="color:#94a3b8;padding:40px;text-align:center">Aucune donnée disponible.</p>';
      return;
    }

    // Lisibilité : 12 mois par défaut (et non 24) pour éviter la surcharge
    // visuelle. Les 12 mois sont largement suffisants pour visualiser des
    // cycles d'entraînement complets.
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - 12);
    const recent = series.filter(p => p.date >= cutoff);
    const data = recent.length > 30 ? recent : series;

    const dom = chargeCharts.main = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      legend: {
        top: 0,
        textStyle: { color: INK2, fontSize: 12 },
        data: ['CTL (forme)', 'ATL (fatigue)', 'TSB (fraîcheur)'],
        itemGap: 24,
      },
      grid: { left: 60, right: 60, top: 40, bottom: 50, containLabel: true },
      tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                 formatter: (params) => {
                   const dateStr = new Date(params[0].axisValue).toLocaleString('fr-FR',
                     { day: 'numeric', month: 'short', year: 'numeric' });
                   let s = `<b>${dateStr}</b><br/>`;
                   params.forEach(p => {
                     if (p.data) s += `<span style="color:${p.color}">${p.seriesName}</span> : ${p.data[1].toFixed(1)}<br/>`;
                   });
                   return s;
                 } },
      xAxis: { ...CHART_THEME.xAxis, type: 'time' },
      yAxis: [
        { ...CHART_THEME.yAxis, type: 'value', name: 'CTL / ATL',
          nameTextStyle: { color: '#94a3b8', fontSize: 11 },
          axisLabel: { ...CHART_THEME.yAxis.axisLabel, fontSize: 11 } },
        { ...CHART_THEME.yAxis, type: 'value', name: 'TSB',
          position: 'right',
          nameTextStyle: { color: '#94a3b8', fontSize: 11 },
          axisLabel: { ...CHART_THEME.yAxis.axisLabel, fontSize: 11 },
          splitLine: { show: false } },
      ],
      series: [
        // CTL : trait épais + aire = "forme de fond", l'info principale
        { name: 'CTL (forme)', type: 'line', yAxisIndex: 0,
          data: data.map(p => [p.date, p.ctl]),
          smooth: true, symbol: 'none',
          lineStyle: { width: 3, color: '#5b8af5' },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                                colorStops: [{ offset: 0, color: 'rgba(91,138,245,0.22)' },
                                             { offset: 1, color: 'rgba(91,138,245,0)' }] } },
          z: 3,
        },
        // ATL : trait pointillé fin = "fatigue récente", info secondaire
        { name: 'ATL (fatigue)', type: 'line', yAxisIndex: 0,
          data: data.map(p => [p.date, p.atl]),
          smooth: true, symbol: 'none',
          lineStyle: { width: 1.3, color: 'rgba(240, 146, 62, 0.65)', type: 'dashed' },
          z: 2,
        },
        // TSB : trait simple discret, mais avec les zones colorées en arrière-plan
        { name: 'TSB (fraîcheur)', type: 'line', yAxisIndex: 1,
          data: data.map(p => [p.date, p.tsb]),
          smooth: true, symbol: 'none',
          lineStyle: { width: 2, color: '#0f766e' },
          z: 4,
          // Zones colorées d'arrière-plan sur l'axe TSB pour repérage visuel
          markArea: {
            silent: true,
            itemStyle: { color: 'transparent' },
            data: [
              [{ yAxis: 5,   itemStyle: { color: 'rgba(34, 211, 167, 0.08)' } },
               { yAxis: 100 }],
              [{ yAxis: -25, itemStyle: { color: 'rgba(239, 91, 91, 0.08)' } },
               { yAxis: -100 }],
            ],
          },
          // Lignes guides : 0, +5 (fraîcheur), -10 (fatigue), -25 (risque)
          markLine: {
            symbol: 'none', silent: true,
            lineStyle: { color: '#94a3b8', type: 'dotted', width: 1 },
            data: [
              { yAxis: 0,   label: { formatter: '0', fontSize: 10, color: '#94a3b8', position: 'insideEndTop' } },
              { yAxis: 5,   lineStyle: { color: 'rgba(34, 211, 167, 0.6)' },
                            label: { formatter: 'Fraîcheur', fontSize: 10, color: '#047857', position: 'insideEndTop' } },
              { yAxis: -10, lineStyle: { color: 'rgba(240, 146, 62, 0.6)' },
                            label: { formatter: 'Fatigue', fontSize: 10, color: '#b45309', position: 'insideEndBottom' } },
              { yAxis: -25, lineStyle: { color: 'rgba(239, 91, 91, 0.6)' },
                            label: { formatter: 'Risque', fontSize: 10, color: '#b91c1c', position: 'insideEndBottom' } },
            ],
          },
        },
      ],
      animationDuration: 600,
    });
  }

  function renderChargeSessionsTable(timeline) {
    const wrap = document.getElementById('chargeSessionsTable');
    if (!wrap) return;
    if (!timeline.length) {
      wrap.innerHTML = '<p class="race-table-empty">Aucune séance disponible.</p>';
      return;
    }

    // 30 dernières séances triées date desc
    const recent = timeline.slice().sort((a, b) => b.date - a.date).slice(0, 30);

    const rows = recent.map(t => {
      const s = t.session;
      const sourceTag = t.source === 'hr'
        ? '<span class="tss-src tss-src-hr" title="Calculé depuis la FC (TRIMP)">FC</span>'
        : t.source === 'pace'
          ? '<span class="tss-src tss-src-pace" title="Calculé depuis l\'allure (rTSS)">All.</span>'
          : '<span class="tss-src tss-src-none">—</span>';
      const tssCls = t.tss < 50 ? 'tss-low' : t.tss < 100 ? 'tss-mid' : t.tss < 150 ? 'tss-high' : 'tss-vhigh';
      return `<tr>
        <td>${s.d}<span class="sess-time">${s.h || ''}</span></td>
        <td><span class="tag" style="--c:${typeColor(s.tp)}">${typeLabel(s.tp)}</span></td>
        <td class="mono">${(s.km || 0).toFixed(1)} km</td>
        <td class="mono">${s.dur || fmtDur(s.dur_s)}</td>
        <td class="mono">${s.fc ? s.fc + ' bpm' : '—'}</td>
        <td class="mono tss-cell ${tssCls}">${Math.round(t.tss)}</td>
        <td>${sourceTag}</td>
      </tr>`;
    }).join('');

    wrap.innerHTML = `<div class="aero-table-scroll">
      <table class="aero-table">
        <thead>
          <tr><th>Date</th><th>Type</th><th>Distance</th><th>Durée</th><th>FC moy</th><th>TSS</th><th>Source</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="aero-table-legend">
        Source <span class="tss-src tss-src-hr">FC</span> = calcul TRIMP depuis la fréquence cardiaque (préféré).
        Source <span class="tss-src tss-src-pace">All.</span> = rTSS fallback depuis l'allure (quand pas de FC).
        TSS &lt; 50 = léger · 50-100 = modéré · 100-150 = soutenu · &gt; 150 = très exigeant.
      </p>
    </div>`;
  }

  let cachedChargeData = null;

  // Analyse contextuelle pour générer une recommandation actionnable.
  // Combine TSB actuel + tendance ATL récente + proximité objectif.
  // Retourne { title, icon, message, action, cls } — affiché en bandeau.
  function buildChargeRecommendation(series) {
    if (!series.length) return null;
    const last = series[series.length - 1];

    // Tendance ATL sur 7 derniers jours
    const atl7d = series.slice(-8, -1).map(p => p.atl);
    const atlTrend = atl7d.length >= 2 ? last.atl - atl7d[0] : 0;

    // Proximité d'un objectif (countdown)
    const countdowns = (RACES && RACES.countdowns) ? RACES.countdowns : [];
    const closestRace = countdowns
      .filter(c => c.days_left > 0 && c.days_left <= 90)
      .sort((a, b) => a.days_left - b.days_left)[0];

    // Logique de reco — par priorité
    if (last.tsb < -25) {
      return {
        title: 'Surcharge à risque',
        icon: '⚠',
        message: `Votre TSB est de ${Math.round(last.tsb)}, en dessous du seuil de risque (−25). Cumul de fatigue important.`,
        action: 'Repos complet ou footing très léger recommandé sur 2-3 jours. La récupération est aussi importante que l\'entraînement.',
        cls: 'reco-risk',
      };
    }

    if (last.tsb < -10 && atlTrend > 5) {
      return {
        title: 'Fatigue qui s\'accumule',
        icon: '◐',
        message: `TSB à ${Math.round(last.tsb)} avec ATL en hausse récente (+${Math.round(atlTrend)} sur 7j). Charge productive mais à surveiller.`,
        action: 'Privilégiez 1-2 séances faciles (footing en endurance fondamentale) avant de relancer du qualitatif.',
        cls: 'reco-warn',
      };
    }

    if (last.tsb > 10 && closestRace && closestRace.days_left <= 7) {
      return {
        title: 'Fraîcheur idéale pour la course',
        icon: '✓',
        message: `TSB à +${Math.round(last.tsb)} et ${closestRace.name} dans ${closestRace.days_left}j. Vous êtes en pleine forme.`,
        action: 'Maintenez quelques sorties courtes en allure spécifique. Évitez tout effort prolongé d\'ici la course.',
        cls: 'reco-fresh',
      };
    }

    if (last.tsb > 15 && (!closestRace || closestRace.days_left > 14)) {
      return {
        title: 'Trop frais — perte de forme',
        icon: '↘',
        message: `TSB à +${Math.round(last.tsb)} sans course imminente. Risque de stagnation ou détraînement.`,
        action: 'Relancez une séance qualitative (fractionné ou sortie longue) cette semaine pour maintenir la CTL.',
        cls: 'reco-detrain',
      };
    }

    if (last.tsb >= -10 && last.tsb <= 10) {
      const ctlTrend = series.slice(-30).reduce((a, p, i, arr) => i === 0 ? 0 : a + (p.ctl - arr[i-1].ctl), 0);
      if (ctlTrend > 3) {
        return {
          title: 'Bonne dynamique',
          icon: '↗',
          message: `Équilibre forme/fatigue maîtrisé (TSB ${last.tsb >= 0 ? '+' : ''}${Math.round(last.tsb)}), CTL en progression (+${Math.round(ctlTrend)} sur 30j).`,
          action: 'Continuez sur cette tendance. C\'est exactement ce qu\'on cherche : monter la charge sans surcharger.',
          cls: 'reco-good',
        };
      } else {
        return {
          title: 'Forme stable',
          icon: '·',
          message: `TSB à ${last.tsb >= 0 ? '+' : ''}${Math.round(last.tsb)}, équilibre maintenu.`,
          action: 'Vous pouvez programmer du qualitatif (intervalles, allure spécifique) ou enchaîner une grosse semaine selon votre plan.',
          cls: 'reco-neutral',
        };
      }
    }

    // Fallback générique
    return {
      title: 'Charge équilibrée',
      icon: '·',
      message: `TSB à ${Math.round(last.tsb)}, CTL à ${Math.round(last.ctl)}.`,
      action: 'Pas d\'alerte particulière sur votre charge actuelle.',
      cls: 'reco-neutral',
    };
  }

  function renderChargeRecommendation(series) {
    const wrap = document.getElementById('chargeRecommendation');
    if (!wrap) return;
    const reco = buildChargeRecommendation(series);
    if (!reco) {
      wrap.innerHTML = '';
      return;
    }
    wrap.innerHTML = `<div class="reco-card ${reco.cls}">
      <div class="reco-icon">${reco.icon}</div>
      <div class="reco-content">
        <div class="reco-title">${reco.title}</div>
        <div class="reco-message">${reco.message}</div>
        <div class="reco-action">${reco.action}</div>
      </div>
    </div>`;
  }

  function renderChargeTab() {
    if (!cachedChargeData) {
      const timeline = computeTssTimeline();
      const series = computeCtlAtlSeries(timeline);
      cachedChargeData = { timeline, series };
    }
    renderChargeKPIs(cachedChargeData.series);
    renderChargeRecommendation(cachedChargeData.series);
    chartCharge(cachedChargeData.series);
    renderChargeSessionsTable(cachedChargeData.timeline);
  }

  function initChargeTab() {
    renderChargeTab();
  }

  // ============================================================================
  // ===== 17. MODULE PRÉDICTIONS ===============================================
  // ============================================================================
  //
  // Prédictions basées sur la VMA actuelle (PERF.now.vma) via table Daniels
  // calibrée Sébastien (voir performance.py _PCT_VMA).
  //
  // Trois blocs :
  //   1. Chronos prédits vs records actuels
  //   2. Allure à viser pour battre les records
  //   3. Projection NYC Marathon spécifique

  // Conversion vitesse (km/h) → chrono (sec) sur une distance donnée
  function predictChronoSec(speedKmh, distanceKm) {
    if (!speedKmh || speedKmh <= 0) return null;
    return (distanceKm / speedKmh) * 3600;
  }

  // Récupère le meilleur chrono officiel sur une distance (depuis RACES)
  function getBestChronoForDistance(distKey) {
    const allRaces = getAllRaces();
    const dist = RACES.distances.find(d => d.key === distKey);
    if (!dist) return null;
    const candidates = allRaces.filter(r => {
      if (r.distance_key !== distKey) return false;
      if (!r.time_s || r.time_s <= 0 || !r.km) return false;
      const inRange = r.km >= dist.min_km && r.km <= dist.max_km;
      return inRange || r._source === 'config';
    });
    if (!candidates.length) return null;
    return candidates.reduce((a, b) => a.time_s < b.time_s ? a : b);
  }

  function renderPredChronos() {
    const wrap = document.getElementById('predChronos');
    if (!wrap) return;
    const vma = PERF.now && PERF.now.vma;
    if (!vma) {
      wrap.innerHTML = '<p class="race-table-empty">VMA non estimable. Ajoutez des séances de fractionné récentes pour activer les prédictions.</p>';
      return;
    }
    const paces = PERF.now.paces || {};

    // Table : distance | prédit | record actuel | delta
    const distances = [
      { key: '5k',       label: '5 km',     km: 5.0,     paceKey: 'vma' },
      { key: '10k',      label: '10 km',    km: 10.0,    paceKey: '10k' },
      { key: 'semi',     label: 'Semi',     km: 21.0975, paceKey: 'semi' },
      { key: 'marathon', label: 'Marathon', km: 42.195,  paceKey: 'marathon' },
    ];

    const rows = distances.map(d => {
      // Chrono prédit = distance × pace dérivée de la VMA
      const paceSec = paces[d.paceKey];
      const predictedSec = paceSec ? paceSec * d.km : null;

      const record = getBestChronoForDistance(d.key);
      const recordSec = record ? record.time_s : null;
      const recordName = record ? record.name : null;

      let deltaHtml = '<span class="pred-delta-none">—</span>';
      if (predictedSec && recordSec) {
        const delta = predictedSec - recordSec;
        if (Math.abs(delta) < 5) {
          deltaHtml = `<span class="pred-delta-eq">~ identique</span>`;
        } else if (delta < 0) {
          // Prédiction plus rapide que le record actuel → PB possible
          deltaHtml = `<span class="pred-delta-pb">PB possible (−${fmtChrono(Math.abs(delta))})</span>`;
        } else {
          deltaHtml = `<span class="pred-delta-no">+${fmtChrono(delta)} vs PB</span>`;
        }
      }

      return `<tr>
        <td><strong>${d.label}</strong></td>
        <td class="mono pred-predicted">${predictedSec ? fmtChrono(predictedSec) : '—'}</td>
        <td class="mono pred-pace">${paceSec ? fmtPace(paceSec) + '/km' : '—'}</td>
        <td class="mono">${recordSec ? fmtChrono(recordSec) : '—'}</td>
        <td>${deltaHtml}</td>
      </tr>`;
    }).join('');

    wrap.innerHTML = `<div class="aero-table-scroll">
      <table class="aero-table pred-table">
        <thead>
          <tr><th>Distance</th><th>Chrono prédit</th><th>Allure prédite</th><th>Votre PB</th><th>Comparaison</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="aero-table-legend">
        Chrono prédit calculé depuis votre VMA actuelle estimée (${vma.toFixed(2)} km/h)
        via table Daniels calibrée. La comparaison montre si vous êtes en capacité de battre votre record.
      </p>
    </div>`;
  }

  function renderPredTargetPaces() {
    const wrap = document.getElementById('predTargetPaces');
    if (!wrap) return;
    const distances = [
      { key: '5k',       label: '5 km',     km: 5.0      },
      { key: '10k',      label: '10 km',    km: 10.0     },
      { key: 'semi',     label: 'Semi',     km: 21.0975  },
      { key: 'marathon', label: 'Marathon', km: 42.195   },
    ];

    const rows = distances.map(d => {
      const record = getBestChronoForDistance(d.key);
      if (!record) {
        return `<tr>
          <td><strong>${d.label}</strong></td>
          <td colspan="3" class="pred-no-record">Aucun record officiel — taguez une course pour activer</td>
        </tr>`;
      }
      // Pour PB, on doit battre le chrono record. On vise -10 sec (objectif "battre"), -30 (significatif), -60 (gros PB).
      const baseChrono = record.time_s;
      const basePace = baseChrono / d.km;

      const targets = [
        { label: 'Améliorer', delta_s: -10 },
        { label: 'Belle perf', delta_s: -30 },
        { label: 'Gros PB',    delta_s: -60 },
      ];

      const cells = targets.map(t => {
        const targetChrono = baseChrono + t.delta_s;
        const targetPace = targetChrono / d.km;
        return `<div class="target-cell">
          <div class="target-label">${t.label}</div>
          <div class="target-chrono">${fmtChrono(targetChrono)}</div>
          <div class="target-pace">${fmtPace(targetPace)}/km</div>
        </div>`;
      }).join('');

      return `<tr>
        <td><strong>${d.label}</strong><br><span class="pred-pb-ref">PB ${fmtChrono(baseChrono)} (${escapeHtml(record.name)})</span></td>
        <td colspan="3">
          <div class="targets-grid">${cells}</div>
        </td>
      </tr>`;
    }).join('');

    wrap.innerHTML = `<table class="aero-table pred-target-table">
      <thead>
        <tr><th>Distance</th><th colspan="3">Allures à viser</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="aero-table-legend">
      Allures cibles pour différents niveaux d'amélioration sur chaque distance.
      Sur marathon, une amélioration de 30 secondes représente déjà un effort significatif.
    </p>`;
  }

  function renderPredNyc() {
    const wrap = document.getElementById('predNyc');
    if (!wrap) return;

    // Trouver NYC dans goals
    const goals = RACES.goals || [];
    const nyc = goals.find(g => g.name && g.name.toLowerCase().includes('nyc'));
    if (!nyc) {
      wrap.innerHTML = '<p class="race-table-empty">NYC Marathon non trouvé dans vos objectifs.</p>';
      return;
    }

    const vma = PERF.now && PERF.now.vma;
    const paces = (PERF.now && PERF.now.paces) || {};
    const marathonPaceSec = paces.marathon;
    if (!vma || !marathonPaceSec) {
      wrap.innerHTML = '<p class="race-table-empty">VMA non estimable pour projection NYC.</p>';
      return;
    }

    // Chrono prédit aujourd'hui
    const predToday = marathonPaceSec * 42.195;

    // Projection optimiste : on suppose une légère amélioration de la VMA
    // sur le reste de la prépa (jusqu'à NYC). Hypothèse conservatrice :
    // amélioration ≈ +0.2 km/h sur 16 semaines de prépa restante (correspond
    // à un cycle complet productif), prorata au temps restant.
    const countdowns = RACES.countdowns || [];
    const nycCountdown = countdowns.find(c => c.name && c.name.toLowerCase().includes('nyc'));
    const daysLeft = nycCountdown ? nycCountdown.days_left : null;

    let predProjected = null;
    if (daysLeft && daysLeft > 0) {
      // Si plus de 16 semaines (112j), max amélioration. Sinon proportionnel.
      const improvementFactor = Math.min(1, daysLeft / 112);
      const vmaProjected = vma + (0.2 * improvementFactor);
      const marathonPaceProjected = (3600 / vmaProjected) / 0.81;  // _PCT_VMA marathon = 0.81
      predProjected = marathonPaceProjected * 42.195;
    }

    // Cible et stratégie NYC
    const targetTime = nyc.target_time;
    const strategyTime = nyc.strategy_time;

    function parseChrono(str) {
      // Parse "2h44'00\"" → secondes
      if (!str) return null;
      const m = str.match(/(\d+)h(\d+)'?(\d+)?/);
      if (!m) return null;
      return parseInt(m[1]) * 3600 + parseInt(m[2]) * 60 + (parseInt(m[3]) || 0);
    }
    const targetSec = parseChrono(targetTime);
    const strategySec = parseChrono(strategyTime);

    const cards = [
      {
        label: 'Aujourd\'hui',
        chrono: predToday,
        sub: `Forme actuelle (VMA ${vma.toFixed(2)} km/h)`,
        c: 'blue',
      },
    ];
    if (predProjected) {
      cards.push({
        label: 'Projection jour J',
        chrono: predProjected,
        sub: `Avec ${daysLeft}j de prépa restante`,
        c: 'cyan',
      });
    }
    if (targetSec) {
      cards.push({
        label: 'Cible fitness',
        chrono: targetSec,
        sub: 'Allure de prépa visée',
        c: 'purple',
      });
    }
    if (strategySec) {
      cards.push({
        label: 'Stratégie jour J',
        chrono: strategySec,
        sub: 'Sécurisé pour parcours dur',
        c: 'orange',
      });
    }

    // Analyse : projection vs cible
    let analysis = '';
    if (predProjected && targetSec) {
      const delta = predProjected - targetSec;
      if (Math.abs(delta) < 30) {
        analysis = `<p class="pred-nyc-analysis ok">Projection alignée avec votre cible fitness (écart de ${Math.abs(Math.round(delta))} secondes). La prépa actuelle vous met sur les rails.</p>`;
      } else if (delta > 0) {
        analysis = `<p class="pred-nyc-analysis warn">Projection plus lente que la cible de ${fmtChrono(delta)}. Il faudra accélérer la prépa pour atteindre l'objectif fitness.</p>`;
      } else {
        analysis = `<p class="pred-nyc-analysis good">Projection plus rapide que la cible de ${fmtChrono(Math.abs(delta))}. Vous êtes potentiellement en avance sur la prépa.</p>`;
      }
    }

    wrap.innerHTML = `<div class="pred-nyc-cards">${cards.map(c =>
      `<div class="pred-nyc-card" data-c="${c.c}">
        <div class="pnc-label">${c.label}</div>
        <div class="pnc-chrono">${fmtChrono(c.chrono)}</div>
        <div class="pnc-pace">${fmtPace(c.chrono / 42.195)}/km</div>
        <div class="pnc-sub">${c.sub}</div>
      </div>`
    ).join('')}</div>
    ${analysis}
    <p class="aero-table-legend">
      La projection jour J intègre une hypothèse d'amélioration progressive de la VMA proportionnelle au temps de prépa restant (max +0,2 km/h sur 16 semaines pleines).
    </p>`;
  }

  function renderPredTab() {
    renderPredChronos();
    renderPredTargetPaces();
    renderPredNyc();
  }

  function initPredTab() {
    renderPredTab();
  }

  // ============================================================================
  // ===== 18. MODULE COMPARATEUR ===============================================
  // ============================================================================
  //
  // Permet de comparer 2 séances côte à côte avec KPIs, graphs allure et FC
  // superposés, et delta par métrique.
  //
  // 2 modes :
  //   - Manuel : 2 sélecteurs date+type
  //   - Auto-suggest : "Suggérer B similaire à A" → moteur de similarité

  const compCharts = {};
  function disposeCompChart(key) {
    if (compCharts[key]) { compCharts[key].dispose(); compCharts[key] = null; }
  }

  // État du comparateur
  let compState = {
    sessA: null,  // session de référence
    sessB: null,  // session de comparaison
  };

  // Liste les sessions formatées pour le sélecteur, triées date desc.
  // On filtre les séances trop courtes (< 3 km) qui n'ont pas grand intérêt
  // analytique pour la comparaison.
  function compEligibleSessions() {
    return SESSIONS
      .filter(s => s.km >= 3 && s.dur_s >= 600)
      .slice()
      .sort((a, b) => b._date - a._date);
  }

  // Calcule un score de similarité entre 2 séances pour l'auto-suggest.
  // Plus le score est BAS, plus les séances sont similaires.
  // Critères pondérés :
  //   - Même type      : score -100 si match, 0 sinon (très fort)
  //   - Distance       : diff km × 5
  //   - Mois calendaire: 0 si même mois, 10 si ±1 mois, 25 sinon
  //   - Année          : préfère années antérieures
  function compSimilarityScore(refSess, candidate) {
    if (candidate._date >= refSess._date) return Infinity;
    let score = 0;
    score += refSess.tp === candidate.tp ? -100 : 30;
    score += Math.abs((refSess.km || 0) - (candidate.km || 0)) * 5;
    const dMonth = Math.abs(refSess._date.getMonth() - candidate._date.getMonth());
    if (dMonth === 0) score += 0;
    else if (dMonth === 1 || dMonth === 11) score += 10;
    else score += 25;
    // Préfère 1 an d'écart, puis 2, etc.
    const yearDiff = refSess._date.getFullYear() - candidate._date.getFullYear();
    if (yearDiff >= 1) score -= 5;
    return score;
  }

  function compFindBestMatch(refSess) {
    const candidates = compEligibleSessions().filter(s => s !== refSess);
    if (!candidates.length) return null;
    let bestScore = Infinity, best = null;
    candidates.forEach(c => {
      const score = compSimilarityScore(refSess, c);
      if (score < bestScore) { bestScore = score; best = c; }
    });
    return best;
  }

  function compPopulateSelectors() {
    const elA = document.getElementById('compSelectorA');
    const elB = document.getElementById('compSelectorB');
    if (!elA || !elB) return;

    const sessions = compEligibleSessions();
    // Limite à 500 pour éviter de polluer la liste, c'est largement assez
    const slice = sessions.slice(0, 500);

    const options = slice.map((s, i) => {
      const lbl = `${s.d} · ${typeLabel(s.tp)} · ${(s.km || 0).toFixed(1)}km · ${fmtChrono(s.dur_s)}`;
      return `<option value="${i}">${escapeHtml(lbl)}</option>`;
    }).join('');

    elA.innerHTML = options;
    elB.innerHTML = options;

    // Stocker la slice pour récupération par index
    elA._sessions = slice;
    elB._sessions = slice;

    // Sélections initiales : A = plus récente, B = précédente
    elA.selectedIndex = 0;
    elB.selectedIndex = 1;
    compState.sessA = slice[0];
    compState.sessB = slice[1];
  }

  function compRender() {
    const wrap = document.getElementById('compResult');
    if (!wrap || !compState.sessA || !compState.sessB) return;

    const a = compState.sessA, b = compState.sessB;

    // KPIs côte à côte
    const kpisA = compExtractKpis(a);
    const kpisB = compExtractKpis(b);

    const kpiRows = [
      { label: 'Date', va: a.d, vb: b.d, delta: null },
      { label: 'Type', va: typeLabel(a.tp), vb: typeLabel(b.tp), delta: null },
      { label: 'Distance', va: kpisA.km, vb: kpisB.km, delta: kpisA.kmRaw - kpisB.kmRaw, unit: 'km', invert: false },
      { label: 'Durée', va: kpisA.dur, vb: kpisB.dur, delta: kpisA.durRaw - kpisB.durRaw, unit: 'sec', invert: false, isDuration: true },
      { label: 'Allure moy', va: kpisA.pace, vb: kpisB.pace, delta: kpisA.paceRaw - kpisB.paceRaw, unit: 'sec/km', invert: true },
      { label: 'FC moy', va: kpisA.fc, vb: kpisB.fc, delta: kpisA.fcRaw && kpisB.fcRaw ? kpisA.fcRaw - kpisB.fcRaw : null, unit: 'bpm', invert: true },
      { label: 'Cadence moy', va: kpisA.cad, vb: kpisB.cad, delta: kpisA.cadRaw && kpisB.cadRaw ? kpisA.cadRaw - kpisB.cadRaw : null, unit: 'ppm', invert: false },
      { label: 'Balance L/R', va: kpisA.bal, vb: kpisB.bal, delta: null },
    ];

    const tableHtml = `<table class="comp-table">
      <thead>
        <tr>
          <th>Métrique</th>
          <th>Séance A</th>
          <th>Séance B</th>
          <th>Δ (A − B)</th>
        </tr>
      </thead>
      <tbody>
        ${kpiRows.map(r => {
          let deltaHtml = '<span class="comp-delta-none">—</span>';
          if (r.delta !== null && r.delta !== undefined && !isNaN(r.delta)) {
            let cls = 'comp-delta-neutral';
            let display;
            if (r.isDuration) {
              display = (r.delta >= 0 ? '+' : '−') + fmtChrono(Math.abs(r.delta));
            } else if (r.unit === 'sec/km') {
              display = (r.delta >= 0 ? '+' : '−') + Math.abs(Math.round(r.delta)) + '"';
            } else {
              display = (r.delta >= 0 ? '+' : '') + (Math.abs(r.delta) < 10 ? r.delta.toFixed(2) : Math.round(r.delta));
            }
            // Coloration : pour allure et FC, moins = mieux (invert=true)
            if (Math.abs(r.delta) > 0.01) {
              if (r.invert) {
                cls = r.delta < 0 ? 'comp-delta-better' : 'comp-delta-worse';
              } else {
                cls = r.delta > 0 ? 'comp-delta-better' : 'comp-delta-worse';
              }
            }
            deltaHtml = `<span class="${cls}">${display}</span>`;
          }
          return `<tr>
            <td class="comp-label-cell">${r.label}</td>
            <td class="comp-val-a mono">${r.va}</td>
            <td class="comp-val-b mono">${r.vb}</td>
            <td>${deltaHtml}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;

    // Graphs comparatifs (si les 2 séances ont des blocs)
    let chartsHtml = '';
    if (a.b && a.b.length && b.b && b.b.length) {
      chartsHtml = `<div class="comp-charts">
        <div class="comp-chart-card">
          <div class="comp-chart-title">Allure par km</div>
          <div id="compChartPace" style="height:280px"></div>
        </div>
        <div class="comp-chart-card">
          <div class="comp-chart-title">FC par km</div>
          <div id="compChartFc" style="height:280px"></div>
        </div>
      </div>`;
    } else {
      chartsHtml = `<p class="comp-no-blocs">Au moins une des deux séances n'a pas de blocs km enregistrés ; les graphiques superposés ne peuvent pas être affichés.</p>`;
    }

    wrap.innerHTML = `<div class="comp-summary">
      <div class="comp-summary-a"><strong>Séance A</strong> ${escapeHtml(a.d)} · ${escapeHtml(a.t || typeLabel(a.tp))}</div>
      <div class="comp-summary-b"><strong>Séance B</strong> ${escapeHtml(b.d)} · ${escapeHtml(b.t || typeLabel(b.tp))}</div>
    </div>
    ${tableHtml}
    ${chartsHtml}`;

    // Construction charts ECharts si applicable
    if (a.b && a.b.length && b.b && b.b.length) {
      setTimeout(() => {
        compChartPace(a, b);
        compChartFc(a, b);
      }, 60);
    }
  }

  function compExtractKpis(s) {
    const km = (s.km || 0).toFixed(2) + ' km';
    const kmRaw = s.km || 0;
    const dur = s.dur || fmtDur(s.dur_s);
    const durRaw = s.dur_s || 0;
    const pace = s.ps ? fmtPace(s.ps) + '/km' : '—';
    const paceRaw = s.ps;
    const fc = s.fc ? s.fc + ' bpm' : '—';
    const fcRaw = s.fc;
    // Cadence et balance pondérées
    const blocs = s.b || [];
    const wAvg = (arr, key) => {
      let w = 0, sum = 0;
      arr.forEach(b => {
        if (b[key] != null && b.dur_s) { sum += b[key] * b.dur_s; w += b.dur_s; }
      });
      return w > 0 ? sum / w : null;
    };
    const cadRaw = wAvg(blocs, 'ca');
    const balRaw = wAvg(blocs, 'bal');
    const cad = cadRaw ? Math.round(cadRaw) + ' ppm' : '—';
    const bal = balRaw ? balRaw.toFixed(2) + '%' : '—';

    return { km, kmRaw, dur, durRaw, pace, paceRaw, fc, fcRaw, cad, cadRaw, bal };
  }

  function compChartPace(a, b) {
    disposeCompChart('pace');
    const el = document.getElementById('compChartPace');
    if (!el) return;

    const xLabels = [];
    const maxLen = Math.max(a.b.length, b.b.length);
    for (let i = 0; i < maxLen; i++) xLabels.push('km ' + (i + 1));

    const allPaces = [...a.b, ...b.b].map(bk => bk.ps).filter(v => v != null);
    const minPace = allPaces.length ? Math.min(...allPaces) : 200;
    const maxPace = allPaces.length ? Math.max(...allPaces) : 400;
    const yMin = Math.floor((minPace - 10) / 5) * 5;
    const yMax = Math.ceil((maxPace + 10) / 5) * 5;

    const dom = compCharts.pace = echarts.init(el);
    dom.setOption({
      textStyle: CHART_THEME.textStyle,
      grid: { left: 50, right: 16, top: 30, bottom: 32, containLabel: true },
      legend: { data: ['Séance A', 'Séance B'], top: 0, textStyle: { color: INK2, fontSize: 11 } },
      tooltip: {
        ...CHART_THEME.tooltip, trigger: 'axis',
        formatter: (params) => {
          let s = '<b>' + params[0].axisValue + '</b><br/>';
          params.forEach(p => {
            if (p.data != null) s += `<span style="color:${p.color}">${p.seriesName}</span> : ${fmtPace(p.data)}/km<br/>`;
          });
          return s;
        },
      },
      xAxis: { ...CHART_THEME.xAxis, type: 'category', data: xLabels },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', min: yMin, max: yMax,
               name: "sec/km", nameTextStyle: { color: '#94a3b8', fontSize: 10 },
               axisLabel: { ...CHART_THEME.yAxis.axisLabel,
                            formatter: v => Math.floor(v/60) + "'" + String(Math.round(v%60)).padStart(2,'0') } },
      series: [
        { name: 'Séance A', type: 'line', smooth: true, symbol: 'circle', symbolSize: 4,
          data: a.b.map(bk => bk.ps || null),
          lineStyle: { width: 2.4, color: '#5b8af5' },
          itemStyle: { color: '#5b8af5' } },
        { name: 'Séance B', type: 'line', smooth: true, symbol: 'circle', symbolSize: 4,
          data: b.b.map(bk => bk.ps || null),
          lineStyle: { width: 2.4, color: '#f0923e' },
          itemStyle: { color: '#f0923e' } },
      ],
      animationDuration: 500,
    });
  }

  function compChartFc(a, b) {
    disposeCompChart('fc');
    const el = document.getElementById('compChartFc');
    if (!el) return;

    const xLabels = [];
    const maxLen = Math.max(a.b.length, b.b.length);
    for (let i = 0; i < maxLen; i++) xLabels.push('km ' + (i + 1));

    const dom = compCharts.fc = echarts.init(el);
    dom.setOption({
      textStyle: CHART_THEME.textStyle,
      grid: { left: 50, right: 16, top: 30, bottom: 32, containLabel: true },
      legend: { data: ['Séance A', 'Séance B'], top: 0, textStyle: { color: INK2, fontSize: 11 } },
      tooltip: {
        ...CHART_THEME.tooltip, trigger: 'axis',
        formatter: (params) => {
          let s = '<b>' + params[0].axisValue + '</b><br/>';
          params.forEach(p => {
            if (p.data != null) s += `<span style="color:${p.color}">${p.seriesName}</span> : ${p.data} bpm<br/>`;
          });
          return s;
        },
      },
      xAxis: { ...CHART_THEME.xAxis, type: 'category', data: xLabels },
      yAxis: { ...CHART_THEME.yAxis, type: 'value',
               name: 'bpm', nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
      series: [
        { name: 'Séance A', type: 'line', smooth: true, symbol: 'circle', symbolSize: 4,
          data: a.b.map(bk => bk.fc || null),
          lineStyle: { width: 2.4, color: '#5b8af5' },
          itemStyle: { color: '#5b8af5' } },
        { name: 'Séance B', type: 'line', smooth: true, symbol: 'circle', symbolSize: 4,
          data: b.b.map(bk => bk.fc || null),
          lineStyle: { width: 2.4, color: '#f0923e' },
          itemStyle: { color: '#f0923e' } },
      ],
      animationDuration: 500,
    });
  }

  function setupComparator() {
    const elA = document.getElementById('compSelectorA');
    const elB = document.getElementById('compSelectorB');
    const btnSuggest = document.getElementById('compAutoSuggest');
    if (!elA || !elB) return;

    compPopulateSelectors();
    compRender();

    elA.addEventListener('change', () => {
      compState.sessA = elA._sessions[parseInt(elA.value, 10)];
      compRender();
    });
    elB.addEventListener('change', () => {
      compState.sessB = elB._sessions[parseInt(elB.value, 10)];
      compRender();
    });
    btnSuggest?.addEventListener('click', () => {
      const match = compFindBestMatch(compState.sessA);
      if (!match) {
        alert('Aucune séance similaire trouvée.');
        return;
      }
      const idx = elB._sessions.indexOf(match);
      if (idx >= 0) {
        elB.selectedIndex = idx;
        compState.sessB = match;
        compRender();
      } else {
        // La match n'est pas dans le top 500, on prépend exceptionnellement
        elB._sessions.unshift(match);
        const lbl = `${match.d} · ${typeLabel(match.tp)} · ${(match.km||0).toFixed(1)}km · ${fmtChrono(match.dur_s)}`;
        const opt = document.createElement('option');
        opt.value = '0';
        opt.textContent = lbl;
        elB.prepend(opt);
        elB.selectedIndex = 0;
        compState.sessB = match;
        compRender();
      }
    });
  }

  function initCompTab() {
    setupComparator();
  }

  // ============================================================================
  // ===== 19. MODULE PLAN D'ENTRAÎNEMENT =======================================
  // ============================================================================
  //
  // Plan B "Medium" :
  //   - Phase actuelle identifiée pour l'objectif le plus proche
  //   - Volume hebdo recommandé sur 8 prochaines semaines
  //   - Répartition qualitative recommandée (80/20, 70/30, 90/10 selon phase)
  //   - Comparaison réalité 4 dernières semaines vs recommandation
  //
  // Recommandations dérivées de :
  //   - Phase de prépa (preparation / specific / taper / peak) depuis countdowns
  //   - Pic naturel = moyenne des 4 meilleures semaines des 6 derniers mois
  //   - Profil taper standard (S-10 à S-1 issus de races.py)
  //
  // Note duplicabilité : aucune valeur absolue hardcodée. Tout est dérivé de
  // l'historique de l'utilisateur.

  // Calcule le "pic naturel" de l'utilisateur : moy des 4 meilleures semaines
  // des 6 derniers mois.
  function planComputeUserPeak() {
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - 6);

    const wkMap = new Map();
    SESSIONS.forEach(s => {
      if (!s._date || s._date < cutoff) return;
      const wk = isoWeekKey(s._date);
      wkMap.set(wk, (wkMap.get(wk) || 0) + (s.km || 0));
    });

    if (wkMap.size === 0) return 50; // fallback raisonnable

    const sortedKm = Array.from(wkMap.values()).sort((a, b) => b - a);
    const top4 = sortedKm.slice(0, 4);
    return top4.reduce((a, x) => a + x, 0) / top4.length;
  }

  // Détermine la phase pour un nombre de jours restants donné
  function planPhaseForDaysLeft(daysLeft) {
    if (daysLeft < 0) return 'past';
    if (daysLeft <= 7) return 'peak';
    if (daysLeft <= 27) return 'taper';
    if (daysLeft <= 70) return 'specific';
    return 'preparation';
  }

  // Coefficient de volume selon la phase (relatif au pic naturel)
  function planVolumeCoefForPhase(phase, daysLeft) {
    if (phase === 'peak') return 0.40;
    if (phase === 'taper') {
      // Variation sur la fenêtre 8-27j : 85% à 4 semaines, descente jusqu'à 55-40%
      // Mapping linéaire approximatif
      if (daysLeft <= 14) return 0.55;
      if (daysLeft <= 21) return 0.70;
      return 0.85;
    }
    if (phase === 'specific') return 1.00;  // pic de charge
    return 0.85;  // preparation
  }

  // Profil de répartition qualitative par phase
  // [pct_endurance, pct_qualitative]
  function planDistributionForPhase(phase) {
    if (phase === 'peak')        return { easy: 90, hard: 10, label: 'Repos actif' };
    if (phase === 'taper')       return { easy: 85, hard: 15, label: 'Affûtage' };
    if (phase === 'specific')    return { easy: 75, hard: 25, label: 'Spécifique' };
    return                              { easy: 80, hard: 20, label: 'Préparation' };
  }

  function planRenderPhase() {
    const wrap = document.getElementById('planPhase');
    if (!wrap) return;

    const countdowns = (RACES && RACES.countdowns) ? RACES.countdowns : [];
    if (!countdowns.length) {
      wrap.innerHTML = '<p class="race-table-empty">Aucun objectif défini. Ajoutez un objectif dans config.json pour activer le plan.</p>';
      return;
    }
    const goal = countdowns[0];

    const phaseLabels = {
      preparation: { l: 'Préparation', d: 'Construction du volume et de l\'endurance fondamentale' },
      specific:    { l: 'Spécifique',  d: 'Travail à allure cible course, pic de charge' },
      taper:       { l: 'Affûtage',    d: 'Réduction progressive du volume, maintien de l\'intensité' },
      peak:        { l: 'Semaine de course', d: 'Repos et réveil musculaire' },
      past:        { l: 'Course passée', d: '—' },
    };
    const phaseInfo = phaseLabels[goal.phase] || phaseLabels.preparation;

    wrap.innerHTML = `<div class="plan-phase-header">
      <div class="plan-phase-main">
        <div class="plan-phase-label">Phase actuelle</div>
        <div class="plan-phase-name">${phaseInfo.l}</div>
        <div class="plan-phase-desc">${phaseInfo.d}</div>
      </div>
      <div class="plan-phase-goal">
        <div class="plan-phase-goal-label">Objectif</div>
        <div class="plan-phase-goal-name">${escapeHtml(goal.name)}</div>
        <div class="plan-phase-goal-date">${goal.date_fr} · J−${goal.days_left}</div>
        ${goal.target_time ? `<div class="plan-phase-goal-target">Cible : <strong>${escapeHtml(goal.target_time)}</strong></div>` : ''}
      </div>
    </div>`;
  }

  function planRenderVolumeChart() {
    disposeChart('planVolume');
    const el = document.getElementById('planVolumeChart');
    if (!el) return;
    const countdowns = (RACES && RACES.countdowns) ? RACES.countdowns : [];
    if (!countdowns.length) {
      el.innerHTML = '<p style="color:#94a3b8;padding:40px;text-align:center">Définissez un objectif pour activer le plan.</p>';
      return;
    }
    const goal = countdowns[0];
    const peak = planComputeUserPeak();
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // 8 prochaines semaines
    const weeks = [];
    for (let w = 0; w < 8; w++) {
      const monday = new Date(today);
      const daysSinceMonday = (monday.getDay() + 6) % 7;  // 0=lundi
      monday.setDate(monday.getDate() - daysSinceMonday + w * 7);
      // Distance jusqu'au goal au milieu de la semaine
      const midWeek = new Date(monday);
      midWeek.setDate(midWeek.getDate() + 3);
      const daysLeft = Math.round((new Date(goal.date) - midWeek) / 86400000);
      const phase = planPhaseForDaysLeft(daysLeft);
      const coef = planVolumeCoefForPhase(phase, daysLeft);
      const km = peak * coef;
      weeks.push({
        weekLabel: monday.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' }),
        km: Math.round(km),
        phase,
        daysLeft,
      });
    }

    const phaseColors = {
      preparation: '#5b8af5',
      specific:    '#22d3a7',
      taper:       '#f0923e',
      peak:        '#ef5b5b',
      past:        '#94a3b8',
    };

    const dom = chartsExtra.planVolume = echarts.init(el);
    dom.setOption({
      ...CHART_THEME,
      grid: { left: 40, right: 16, top: 30, bottom: 32, containLabel: true },
      tooltip: { ...CHART_THEME.tooltip, trigger: 'axis',
                 formatter: (params) => {
                   const idx = params[0].dataIndex;
                   const w = weeks[idx];
                   return `<b>Semaine du ${w.weekLabel}</b><br/>
                     Volume recommandé : ${w.km} km<br/>
                     Phase : ${w.phase}<br/>
                     J−${w.daysLeft} de l'objectif`;
                 } },
      xAxis: { ...CHART_THEME.xAxis, type: 'category', data: weeks.map(w => w.weekLabel) },
      yAxis: { ...CHART_THEME.yAxis, type: 'value', name: 'km',
               nameTextStyle: { color: '#94a3b8', fontSize: 10 } },
      series: [{
        type: 'bar',
        data: weeks.map(w => ({ value: w.km, itemStyle: { color: phaseColors[w.phase], borderRadius: [4,4,0,0] } })),
        animationDuration: 600,
      }],
    });
  }

  function planRenderDistribution() {
    const wrap = document.getElementById('planDistribution');
    if (!wrap) return;
    const phases = ['preparation', 'specific', 'taper', 'peak'];
    const html = phases.map(ph => {
      const d = planDistributionForPhase(ph);
      const phaseColors = {
        preparation: '#5b8af5', specific: '#22d3a7', taper: '#f0923e', peak: '#ef5b5b',
      };
      return `<div class="plan-distrib-card" style="border-left: 4px solid ${phaseColors[ph]}">
        <div class="plan-distrib-title">${d.label}</div>
        <div class="plan-distrib-bar">
          <div class="plan-distrib-easy" style="width:${d.easy}%; background:#22d3a7">Endurance ${d.easy}%</div>
          <div class="plan-distrib-hard" style="width:${d.hard}%; background:#ef5b5b">Intensité ${d.hard}%</div>
        </div>
      </div>`;
    }).join('');
    wrap.innerHTML = html;
  }

  function planRenderRecentVsReco() {
    const wrap = document.getElementById('planRecentVsReco');
    if (!wrap) return;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Volume + intensité des 4 dernières semaines
    const weeks = [];
    for (let w = 0; w < 4; w++) {
      const monday = new Date(today);
      const daysSinceMonday = (monday.getDay() + 6) % 7;
      monday.setDate(monday.getDate() - daysSinceMonday - w * 7);
      const sunday = new Date(monday);
      sunday.setDate(sunday.getDate() + 6);

      let km = 0, easyKm = 0, hardKm = 0;
      SESSIONS.forEach(s => {
        if (!s._date) return;
        const d = startOfDay(s._date);
        if (d >= monday && d <= sunday) {
          km += s.km || 0;
          // Classification simplifiée : footing/endurance/sortie_longue = easy
          // tout le reste = hard
          if (['footing', 'endurance', 'sortie_longue'].includes(s.tp)) {
            easyKm += s.km || 0;
          } else {
            hardKm += s.km || 0;
          }
        }
      });

      weeks.push({
        label: monday.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' }),
        km, easyKm, hardKm,
        easyPct: km > 0 ? Math.round(easyKm / km * 100) : 0,
        hardPct: km > 0 ? Math.round(hardKm / km * 100) : 0,
      });
    }
    weeks.reverse(); // ancien → récent

    const countdowns = (RACES && RACES.countdowns) ? RACES.countdowns : [];
    const goal = countdowns[0];
    const peak = planComputeUserPeak();

    const rows = weeks.map(w => {
      // Reco pour cette semaine
      let recoKm = '—', recoEasy = '—', recoHard = '—';
      if (goal) {
        const midWeek = new Date(new Date(w.label.split(' ').reverse().join('/')).getTime() + 3*86400000);
        // Simplification : on prend la phase actuelle pour les 4 dernières semaines aussi
        const daysLeftMid = Math.round((new Date(goal.date) - new Date()) / 86400000);
        const phase = planPhaseForDaysLeft(daysLeftMid);
        const coef = planVolumeCoefForPhase(phase, daysLeftMid);
        recoKm = Math.round(peak * coef);
        const d = planDistributionForPhase(phase);
        recoEasy = d.easy;
        recoHard = d.hard;
      }

      const kmCls = goal && Math.abs(w.km - recoKm) < 5 ? 'ok' : goal && w.km < recoKm ? 'under' : 'over';
      const easyCls = goal && Math.abs(w.easyPct - recoEasy) <= 5 ? 'ok' : 'off';

      return `<tr>
        <td>Sem du ${w.label}</td>
        <td class="mono">${Math.round(w.km)} km</td>
        <td class="mono plan-${kmCls}">${recoKm} km</td>
        <td class="mono">${w.easyPct}% / ${w.hardPct}%</td>
        <td class="mono plan-${easyCls}">${recoEasy}% / ${recoHard}%</td>
      </tr>`;
    }).join('');

    wrap.innerHTML = `<table class="aero-table">
      <thead>
        <tr>
          <th>Semaine</th>
          <th>Volume réel</th>
          <th>Volume reco</th>
          <th>Réel End/Int</th>
          <th>Reco End/Int</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="aero-table-legend">
      <span class="plan-ok-tag">aligné</span> : écart &lt; 5 km ou ≤ 5%.
      <span class="plan-under-tag">sous-volume</span> : marge de progression.
      <span class="plan-over-tag">au-dessus</span> : attention à la fatigue.
    </p>`;
  }

  // Utilise un objet chartsExtra pour éviter de polluer `charts` Vue d'ensemble
  const chartsExtra = {};
  function disposeChart(key) {
    if (chartsExtra[key]) { chartsExtra[key].dispose(); chartsExtra[key] = null; }
  }

  // ===== PLAN ENGINE — séance du jour + calendrier 21 sem ====================
  // Si un plan d'entraînement complet est injecté (data.plan), on l'affiche
  // au-dessus de l'analyse générique (phase / volume / reco).

  const PLAN_TYPE_COLORS = {
    rest:       '#94a3b8',
    easy:       '#22d3a7',
    recovery:   '#22d3a7',
    long:       '#5b8af5',
    long_mp:    '#3b6dc7',
    long_prog:  '#3b6dc7',
    intervals:  '#ef4444',
    fartlek:    '#ef5b5b',
    tempo:      '#f0923e',
    mp_run:     '#7c3aed',
    shake:      '#a3e635',
    race:       '#dc2626',
  };

  const PLAN_TYPE_LABELS = {
    rest: 'Repos', easy: 'Footing', recovery: 'Récup',
    long: 'Sortie longue', long_mp: 'SL avec MP', long_prog: 'SL progressive',
    intervals: 'Intervalles', fartlek: 'Fartlek', tempo: 'Tempo',
    mp_run: 'Allure marathon', shake: 'Activation', race: 'Course',
  };

  // Date YYYY-MM-DD au fuseau local (évite le décalage UTC)
  function localISODate(d) {
    d = d || new Date();
    return d.getFullYear() + '-' +
           String(d.getMonth()+1).padStart(2,'0') + '-' +
           String(d.getDate()).padStart(2,'0');
  }

  function planFindToday() {
    if (!PLAN) return null;
    const iso = localISODate();
    for (const w of PLAN.weeks || []) {
      for (const d of w.days || []) {
        if (d.date === iso) return { day: d, week: w };
      }
    }
    return null;
  }

  function planFindCurrentWeek() {
    if (!PLAN) return null;
    const iso = localISODate();
    for (const w of PLAN.weeks || []) {
      if (w.start_date <= iso && iso <= w.end_date) return w;
    }
    return null;
  }

  // --- Verdicts séances (scoring) -------------------------------------
  const VERDICT_META = {
    success: {color: '#22c55e', label: 'Réussie',   icon: '✓'},
    partial: {color: '#f59e0b', label: 'Partielle', icon: '~'},
    failed:  {color: '#ef4444', label: 'Échouée',   icon: '✗'},
    missed:  {color: '#94a3b8', label: 'Manquée',   icon: '✗'},
  };

  function scoreRing(points, verdict, size) {
    const m = VERDICT_META[verdict] || VERDICT_META.partial;
    const s = size || 30;
    const r = (s - 5) / 2;
    const c = 2 * Math.PI * r;
    const filled = c * Math.min(points, 100) / 100;
    return `<svg class="score-ring" width="${s}" height="${s}" viewBox="0 0 ${s} ${s}" role="img" aria-label="${m.label} ${points}/100">
      <circle cx="${s/2}" cy="${s/2}" r="${r}" fill="none" stroke="#e5e9f0" stroke-width="3.5"/>
      <circle cx="${s/2}" cy="${s/2}" r="${r}" fill="none" stroke="${m.color}" stroke-width="3.5"
        stroke-linecap="round" stroke-dasharray="${filled.toFixed(1)} ${c.toFixed(1)}"
        transform="rotate(-90 ${s/2} ${s/2})"/>
      <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle"
        font-size="${Math.round(s*0.34)}" font-weight="700" fill="${m.color}">${points}</text>
    </svg>`;
  }

  function verdictPill(score) {
    if (!score) return '';
    const m = VERDICT_META[score.verdict] || VERDICT_META.partial;
    return `<span class="verdict-pill" style="--vc:${m.color}">${m.icon} ${m.label}</span>`;
  }

  function scoreTooltip(score) {
    if (!score) return '';
    return (score.reasons || []).join(' · ');
  }

  function planRenderTodayCard() {
    const wrap = document.getElementById('planTodayCard');
    const homeWrap = document.getElementById('homeToday');
    if (!wrap && !homeWrap) return;
    const setHTML = (h) => {
      if (wrap) wrap.innerHTML = h;
      if (homeWrap) homeWrap.innerHTML = h;
    };
    if (!PLAN) {
      setHTML('<p class="race-table-empty">Pas de plan actif. Définis un objectif principal dans config.json pour activer le plan.</p>');
      return;
    }
    const today = planFindToday();
    if (!today) {
      setHTML('<p class="race-table-empty">Pas de séance prévue aujourd\'hui.</p>');
      return;
    }
    const d = today.day;
    const w = today.week;
    const color = PLAN_TYPE_COLORS[d.type] || '#5b8af5';
    const planTypeLabel = PLAN_TYPE_LABELS[d.type] || d.type;

    let actualBlock = '';
    if (d.actual && ['done','over','under','bonus'].includes(d.status)) {
      const a = d.actual;
      actualBlock = `<div class="plan-actual-line">
        <span class="plan-actual-tag">Réalisé</span>
        <strong>${a.km} km</strong> en ${Math.floor(a.duration_min/60) > 0 ? Math.floor(a.duration_min/60)+'h'+String(a.duration_min%60).padStart(2,'0') : a.duration_min+'min'}
        ${a.pace_str ? ` · ${escapeHtml(a.pace_str)}` : ''}
        ${a.fc ? ` · FC ${a.fc}` : ''}
        ${d.score ? verdictPill(d.score) : ''}
      </div>
      ${d.score ? `<div class="plan-score-line" title="${escapeHtml(scoreTooltip(d.score))}">${scoreRing(d.score.points, d.score.verdict, 38)}<span class="plan-score-reasons">${escapeHtml(scoreTooltip(d.score))}</span></div>` : ''}`;
    }

    let descHtml = escapeHtml(d.description || '').replace(/\n/g, '<br/>');

    // Séance reprogrammée : on affiche la séance clé ramenée sur ce jour
    let rescheduledBlock = '';
    let displayTitle = d.title;
    let displayPace = d.target_pace;
    let displayDesc = descHtml;
    if (d._rescheduled_title) {
      displayTitle = d._rescheduled_title;
      displayPace = d._rescheduled_pace || d.target_pace;
      displayDesc = escapeHtml(d._rescheduled_desc || '').replace(/\n/g, '<br/>');
      rescheduledBlock = `<div class="plan-reschedule-banner">
        ↻ Séance clé reprogrammée depuis le ${(new Date(d._rescheduled_from)).toLocaleDateString('fr-FR', {weekday:'long', day:'numeric'})} (manquée)
      </div>`;
    }

    const subEl = document.getElementById('homeTodaySub');
    if (subEl) subEl.textContent = `W${w.week_num}/${PLAN.meta.weeks_total} · ${w.phase_label} · J−${Math.floor((new Date(PLAN.meta.goal_date) - new Date(d.date)) / 86400000)}`;
    setHTML(`
      <div class="plan-today-head" style="border-left:6px solid ${color};">
        ${rescheduledBlock}
        <div class="plan-today-meta">
          <span class="plan-today-date">${(new Date(d.date)).toLocaleDateString('fr-FR', {weekday:'long', day:'numeric', month:'long'})}</span>
          <span class="plan-today-week">W${w.week_num}/${PLAN.meta.weeks_total} · ${escapeHtml(w.phase_label)} · J−${(new Date(PLAN.meta.goal_date) - new Date(d.date))/86400000|0}</span>
        </div>
        <div class="plan-today-title">
          <span class="plan-type-pill" style="background:${color}">${planTypeLabel}</span>
          <h2>${escapeHtml(displayTitle)}</h2>
        </div>
        <div class="plan-today-stats">
          ${d.km > 0 ? `<div><span class="kv-label">${d.key ? 'Volume jour' : 'Distance'}</span><span class="kv-value">${d.km} km</span></div>` : ''}
          ${d.duration_min > 0 ? `<div><span class="kv-label">Durée</span><span class="kv-value">${Math.floor(d.duration_min/60)>0 ? Math.floor(d.duration_min/60)+'h'+String(d.duration_min%60).padStart(2,'0') : d.duration_min+' min'}</span></div>` : ''}
          ${displayPace ? `<div><span class="kv-label">${d.key ? 'Allure du bloc' : 'Allure'}</span><span class="kv-value">${escapeHtml(displayPace)}</span></div>` : ''}
        </div>
        ${actualBlock}
        <p class="plan-today-desc${d.actual ? ' is-done' : ''}">${displayDesc}</p>
      </div>`);
  }

  function planRenderCoach() {
    const targets = [
      {card: document.getElementById('coachCard'), wrap: document.getElementById('coachContent'), date: document.getElementById('coachDate')},
      {card: document.getElementById('homeCoachCard'), wrap: document.getElementById('homeCoach'), date: document.getElementById('homeCoachDate')},
    ].filter(t => t.card && t.wrap);
    if (!targets.length) return;
    const c = RAW.coach;
    if (!c || (!c.analysis && !(c.pending || []).length)) {
      targets.forEach(t => { t.card.style.display = 'none'; });
      return;
    }
    const dateStr = c.generated_at
      ? 'analyse du ' + new Date(c.generated_at).toLocaleDateString('fr-FR', {weekday: 'long', day: 'numeric', month: 'long'})
      : '';

    const KIND_LABELS = {
      volume_adjust: 'Ajustement volume', add_note: 'Consigne',
      move_session: 'Déplacement de séance', change_type: 'Changement de séance',
      change_pace: 'Changement d\'allure', restructure_week: 'Restructuration semaine',
      other: 'Proposition',
    };

    let html = '';
    if (c.headline) html += `<div class="coach-headline">${escapeHtml(c.headline)}</div>`;
    if (c.analysis) html += `<p class="coach-analysis">${escapeHtml(c.analysis).replace(/\n/g, '<br/>')}</p>`;

    const applied = c.applied || [];
    if (applied.length) {
      html += `<div class="coach-section-title">Ajustements appliqués automatiquement</div>` +
        applied.map(a => `<div class="coach-item coach-applied">
          <span class="coach-item-icon">✓</span>
          <div><strong>${KIND_LABELS[a.kind] || a.kind}</strong> · ${escapeHtml(a.detail || '')}
          <div class="coach-item-reason">${escapeHtml(a.reason || '')}</div></div>
        </div>`).join('');
    }

    const pending = c.pending || [];
    if (pending.length) {
      html += `<div class="coach-section-title">En attente de ta validation (briefing du matin)</div>` +
        pending.map(p => `<div class="coach-item coach-pending">
          <span class="coach-item-icon">?</span>
          <div><strong>${KIND_LABELS[p.kind] || p.kind}</strong>${p.date ? ' · ' + p.date : ''}
          · ${escapeHtml(typeof p.new_value === 'string' ? p.new_value : JSON.stringify(p.new_value || ''))}
          <div class="coach-item-reason">${escapeHtml(p.reason || '')}</div></div>
        </div>`).join('');
    }
    targets.forEach(t => {
      t.card.style.display = '';
      t.wrap.innerHTML = html;
      if (t.date) t.date.textContent = dateStr;
    });
  }

  function planRenderAdaptations() {
    const wrap = document.getElementById('planAdaptations');
    if (!wrap || !PLAN) return;
    const adapts = PLAN.adaptations || [];
    if (!adapts.length) { wrap.innerHTML = ''; return; }
    const kindIcon = {
      reschedule_key: '↻',
      volume_boost:   '↑',
      volume_reduce:  '↓',
      recovery_week:  '☾',
    };
    const items = adapts.map(a => `
      <div class="plan-adapt-item">
        <span class="plan-adapt-icon">${kindIcon[a.kind] || '●'}</span>
        <div>
          <div class="plan-adapt-reason">${escapeHtml(a.reason || a.kind)}</div>
          ${a.title ? `<div class="plan-adapt-detail">${escapeHtml(a.title)} · ${a.from_date || ''} → ${a.to_date || ''}</div>` : ''}
          ${a.date ? `<div class="plan-adapt-detail">${escapeHtml(a.date)} · ${a.delta_km>0?'+':''}${a.delta_km||''}km</div>` : ''}
        </div>
      </div>`).join('');
    wrap.innerHTML = `<div class="plan-adapt-grid">${items}</div>`;
  }

  function planRenderCurrentWeek() {
    const wrap = document.getElementById('planCurrentWeek');
    if (!wrap || !PLAN) return;
    const w = planFindCurrentWeek();
    if (!w) { wrap.innerHTML = ''; return; }

    const todayIso = localISODate();

    const STATUS_MAP = {
      done:   {cls: 'ok',     icon: '✓'},
      bonus:  {cls: 'bonus',  icon: '+'},
      over:   {cls: 'over',   icon: '↑'},
      under:  {cls: 'under',  icon: '↓'},
      missed: {cls: 'missed', icon: '✗'},
      today:  {cls: 'today',  icon: '●'},
      pending:{cls: '',       icon: '○'},
    };
    const rows = (w.days || []).map(d => {
      const color = PLAN_TYPE_COLORS[d.type] || '#94a3b8';
      const st = STATUS_MAP[d.status] || STATUS_MAP.pending;
      const actualKm = d.actual ? `<span class="plan-actual-km">→ ${d.actual.km}km${d.actual.pace_str?' '+escapeHtml(d.actual.pace_str):''}</span>` : '';
      const isToday = d.date === todayIso ? ' plan-day-today' : '';
      const titleDisplay = d._rescheduled_title ? `${escapeHtml(d._rescheduled_title)} <small>(↻ reprogrammée)</small>` : escapeHtml(d.title);
      // Colonne verdict : anneau de score si séance scorée, sinon icône statut
      let statusCell;
      if (d.score) {
        statusCell = `<span title="${escapeHtml(scoreTooltip(d.score))}">${scoreRing(d.score.points, d.score.verdict, 30)}</span>`;
      } else if (d.status === 'missed') {
        statusCell = `<span class="verdict-cross" title="Séance manquée">✗</span>`;
      } else {
        statusCell = st.icon;
      }
      return `<tr class="${st.cls}${isToday}" data-day-date="${d.date}">
        <td class="plan-day-status">${statusCell}</td>
        <td>${(new Date(d.date)).toLocaleDateString('fr-FR', {weekday:'short', day:'numeric'})}</td>
        <td><span class="plan-type-dot" style="background:${color}"></span> ${titleDisplay} ${d.score ? verdictPill(d.score) : ''}</td>
        <td class="mono">${d.km > 0 ? d.km+' km' : '—'}</td>
        <td class="mono">${actualKm}</td>
      </tr>`;
    }).join('');

    // Bandeau conformité hebdo
    let complianceBar = '';
    if (w.compliance) {
      const c = w.compliance;
      const m = VERDICT_META[c.verdict] || VERDICT_META.partial;
      complianceBar = `<div class="plan-week-compliance">
        <div class="pwc-ring">${scoreRing(c.points, c.verdict, 44)}</div>
        <div class="pwc-body">
          <div class="pwc-bar-wrap"><div class="pwc-bar" style="width:${Math.min(c.km_pct,100)}%;background:${m.color}"></div></div>
          <div class="pwc-detail">${c.km_done} / ${c.km_planned} km (${c.km_pct}%) · ${c.sessions_done}/${c.sessions_planned} séances${c.keys_total ? ` · clés ${c.keys_success}/${c.keys_total}` : ''}</div>
        </div>
      </div>`;
    }

    wrap.innerHTML = `
      <div class="plan-week-head">
        <span>Semaine ${w.week_num} · ${escapeHtml(w.phase_label)}</span>
        <span class="plan-week-target">Objectif volume : <strong>${w.target_km} km</strong></span>
      </div>
      ${complianceBar}
      <div class="plan-week-scroll"><table class="plan-week-table"><tbody>${rows}</tbody></table></div>`;
  }

  function planRenderCalendar() {
    const wrap = document.getElementById('planCalendar');
    if (!wrap || !PLAN) return;
    const todayIso = localISODate();

    const html = PLAN.weeks.map(w => {
      const isCurrent = w.start_date <= todayIso && todayIso <= w.end_date;
      const phaseColor = {
        base: '#5b8af5', specific: '#22d3a7', peak: '#7c3aed',
        taper: '#f0923e', race: '#dc2626',
      }[w.phase] || '#94a3b8';

      const dayCells = (w.days || []).map(d => {
        const color = PLAN_TYPE_COLORS[d.type] || '#94a3b8';
        const isPast = d.date < todayIso;
        const isToday = d.date === todayIso;
        const verdict = d.score ? d.score.verdict : (d.status === 'missed' ? 'missed' : null);
        const cls = [
          'plan-cal-day',
          d.status === 'done' && !verdict ? 'done' : '',
          verdict ? 'v-' + verdict : '',
          isToday ? 'today' : '',
        ].filter(Boolean).join(' ');
        const km = d.km > 0 ? Math.round(d.km) : '';
        const scoreInfo = d.score ? ` · ${d.score.verdict_label} ${d.score.points}/100 (${scoreTooltip(d.score)})` : (d.status === 'missed' ? ' · Manquée' : '');
        const titleAttr = `${d.title}${d.km>0 ? ' · '+d.km+'km' : ''}${d.target_pace ? ' · '+d.target_pace : ''}${scoreInfo}`;
        return `<div class="${cls}" style="--c:${color}" title="${escapeHtml(titleAttr)}" data-day-date="${d.date}">
          <span class="plan-cal-km">${km}</span>
        </div>`;
      }).join('');

      const compBadge = w.compliance
        ? `<div class="plan-cal-comp" style="color:${(VERDICT_META[w.compliance.verdict]||{}).color || '#94a3b8'}">${w.compliance.km_pct}%</div>`
        : '';

      return `<div class="plan-cal-row ${isCurrent ? 'current' : ''}">
        <div class="plan-cal-meta" style="border-left:3px solid ${phaseColor}">
          <div class="plan-cal-wnum">W${w.week_num}</div>
          <div class="plan-cal-phase">${escapeHtml(w.phase_label)}</div>
          <div class="plan-cal-km-total">${w.target_km}km</div>
          ${compBadge}
        </div>
        <div class="plan-cal-days">${dayCells}</div>
      </div>`;
    }).join('');

    wrap.innerHTML = `
      <div class="plan-cal-legend">
        <span class="plan-cal-dot" style="background:#5b8af5"></span>Base
        <span class="plan-cal-dot" style="background:#22d3a7"></span>Spécifique
        <span class="plan-cal-dot" style="background:#7c3aed"></span>Pic
        <span class="plan-cal-dot" style="background:#f0923e"></span>Affûtage
        <span class="plan-cal-dot" style="background:#dc2626"></span>Course
        <span style="margin-left:14px;color:#22c55e">■ réussie</span>
        <span style="margin-left:8px;color:#f59e0b">■ partielle</span>
        <span style="margin-left:8px;color:#ef4444">■ échouée</span>
        <span style="margin-left:8px;color:#94a3b8">■ manquée</span>
      </div>
      ${html}`;
  }

  function planRenderPaces() {
    const wrap = document.getElementById('planPaces');
    if (!wrap || !PLAN || !PLAN.meta || !PLAN.meta.paces_str) return;
    const p = PLAN.meta.paces_str;
    const ordered = [
      ['mp_target', 'Allure marathon CIBLE', '#dc2626'],
      ['mp_strategy', 'Allure marathon NYC (stratégie)', '#7c3aed'],
      ['le_long', 'Allure sortie longue', '#5b8af5'],
      ['seuil', 'Allure seuil', '#f0923e'],
      ['10k', 'Allure 10K', '#ef4444'],
      ['vma', 'Allure VMA', '#ef4444'],
      ['footing', 'Allure footing récup', '#22d3a7'],
    ];
    const cards = ordered.filter(([k]) => p[k]).map(([k, label, color]) =>
      `<div class="plan-pace-card" style="border-top:3px solid ${color}">
        <span class="plan-pace-label">${label}</span>
        <span class="plan-pace-value">${escapeHtml(p[k])}</span>
      </div>`
    ).join('');
    wrap.innerHTML = cards;
  }

  // --- Fiche séance (bottom-sheet) --------------------------------------
  function planFindDay(iso) {
    for (const w of (PLAN?.weeks || [])) {
      for (const d of (w.days || [])) {
        if (d.date === iso) return {day: d, week: w};
      }
    }
    return null;
  }

  function openDaySheet(iso) {
    const found = planFindDay(iso);
    const backdrop = document.getElementById('sheetBackdrop');
    const content = document.getElementById('sheetContent');
    if (!found || !backdrop || !content) return;
    const {day: d, week: w} = found;
    const color = PLAN_TYPE_COLORS[d.type] || '#5b8af5';
    const typeLabel = PLAN_TYPE_LABELS[d.type] || d.type;
    const dateFr = (new Date(d.date)).toLocaleDateString('fr-FR', {weekday: 'long', day: 'numeric', month: 'long'});

    const title = d._rescheduled_title || d.title;
    const desc = (d._rescheduled_desc || d.description || '').replace(/\n/g, '<br/>');
    const pace = d._rescheduled_pace || d.target_pace;

    let actualBlock = '';
    if (d.actual) {
      const a = d.actual;
      actualBlock = `<div class="sheet-section">
        <div class="sheet-section-title">Réalisé</div>
        <div class="sheet-actual">
          <strong>${a.km} km</strong>${a.pace_str ? ' · ' + escapeHtml(a.pace_str) : ''}${a.fc ? ' · FC ' + a.fc : ''}
          ${a.duration_min ? ' · ' + (Math.floor(a.duration_min/60) > 0 ? Math.floor(a.duration_min/60)+'h'+String(a.duration_min%60).padStart(2,'0') : a.duration_min+' min') : ''}
        </div>
        ${d.score ? `<div class="sheet-score">${scoreRing(d.score.points, d.score.verdict, 44)}
          <div><div>${verdictPill(d.score)}</div>
          <div class="coach-item-reason">${escapeHtml(scoreTooltip(d.score))}</div></div></div>` : ''}
      </div>`;
    } else if (d.status === 'missed') {
      actualBlock = `<div class="sheet-section"><span class="verdict-pill" style="--vc:#94a3b8">✗ Manquée</span></div>`;
    }

    content.innerHTML = `
      <div class="sheet-meta">${dateFr} · W${w.week_num}/${PLAN.meta.weeks_total} · ${escapeHtml(w.phase_label)}</div>
      <div class="sheet-title">
        <span class="plan-type-pill" style="background:${color}">${typeLabel}</span>
        <h2>${escapeHtml(title)}</h2>
      </div>
      <div class="sheet-stats">
        ${d.km > 0 ? `<div><span class="kv-label">Distance</span><span class="kv-value">${d.km} km</span></div>` : ''}
        ${d.duration_min > 0 ? `<div><span class="kv-label">Durée</span><span class="kv-value">~${d.duration_min} min</span></div>` : ''}
        ${pace ? `<div><span class="kv-label">Allure cible</span><span class="kv-value">${escapeHtml(pace)}</span></div>` : ''}
      </div>
      ${desc ? `<div class="sheet-section"><div class="sheet-section-title">Consignes</div><p class="sheet-desc">${desc}</p></div>` : ''}
      ${actualBlock}`;
    backdrop.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeDaySheet() {
    const backdrop = document.getElementById('sheetBackdrop');
    if (backdrop) backdrop.hidden = true;
    document.body.style.overflow = '';
  }

  function setupDaySheet() {
    const backdrop = document.getElementById('sheetBackdrop');
    if (!backdrop) return;
    document.getElementById('sheetClose')?.addEventListener('click', closeDaySheet);
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) closeDaySheet(); });
    document.addEventListener('click', (e) => {
      const el = e.target.closest('[data-day-date]');
      if (el) openDaySheet(el.getAttribute('data-day-date'));
    });
  }

  // --- Accueil ------------------------------------------------------------
  function homeRenderLast() {
    const wrap = document.getElementById('homeLast');
    if (!wrap) return;
    let best = null;
    for (const w of (PLAN?.weeks || [])) {
      for (const d of (w.days || [])) {
        if (d.actual && d.date) {
          if (!best || d.date > best.date) best = d;
        }
      }
    }
    if (!best) { wrap.innerHTML = '<p class="race-table-empty">Aucune séance récente.</p>'; return; }
    const a = best.actual;
    wrap.innerHTML = `
      <div class="home-last" data-day-date="${best.date}">
        <div class="home-last-main">
          <div class="home-last-title">${escapeHtml(a.title || best.title || '')}</div>
          <div class="home-last-sub">${(new Date(best.date)).toLocaleDateString('fr-FR', {weekday: 'long', day: 'numeric', month: 'long'})}</div>
          <div class="home-last-stats"><strong>${a.km} km</strong>${a.pace_str ? ' · ' + escapeHtml(a.pace_str) : ''}${a.fc ? ' · FC ' + a.fc : ''}</div>
          ${best.score ? `<div style="margin-top:6px">${verdictPill(best.score)}</div>` : ''}
        </div>
        ${best.score ? `<div>${scoreRing(best.score.points, best.score.verdict, 54)}</div>` : ''}
      </div>`;
  }

  function homeRenderWeek() {
    const wrap = document.getElementById('homeWeek');
    if (!wrap) return;
    const w = planFindCurrentWeek();
    if (!w) { wrap.innerHTML = '<p class="race-table-empty">Hors période de plan.</p>'; return; }
    const sub = document.getElementById('homeWeekSub');
    if (sub) sub.textContent = `W${w.week_num}/${PLAN.meta.weeks_total} · ${w.phase_label}`;
    const todayIso = localISODate();

    const dots = (w.days || []).map(d => {
      const verdict = d.score ? d.score.verdict : (d.status === 'missed' ? 'missed' : null);
      const m = verdict ? VERDICT_META[verdict] : null;
      const isToday = d.date === todayIso;
      const isRest = (d.km || 0) <= 0;
      const bg = m ? m.color : (isRest ? 'transparent' : 'var(--surface-3)');
      const border = isToday ? 'var(--c-blue)' : (isRest ? 'var(--border-2)' : 'transparent');
      return `<div class="home-week-dot" data-day-date="${d.date}"
        style="background:${bg};border:2px ${isRest && !m ? 'dashed' : 'solid'} ${border}"
        title="${escapeHtml(d.title || '')}">
        <span>${['L','M','M','J','V','S','D'][(new Date(d.date)).getDay() === 0 ? 6 : (new Date(d.date)).getDay() - 1]}</span>
      </div>`;
    }).join('');

    let bar = '';
    if (w.compliance) {
      const c = w.compliance;
      const m = VERDICT_META[c.verdict] || VERDICT_META.partial;
      bar = `<div class="pwc-bar-wrap" style="margin-top:12px"><div class="pwc-bar" style="width:${Math.min(c.km_pct, 100)}%;background:${m.color}"></div></div>
        <div class="pwc-detail">${c.km_done} / ${c.km_planned} km (${c.km_pct}%)${c.keys_total ? ` · clés ${c.keys_success}/${c.keys_total}` : ''}</div>`;
    } else {
      const target = w.target_km ? `<div class="pwc-detail">Objectif : ${w.target_km} km</div>` : '';
      bar = target;
    }
    wrap.innerHTML = `<div class="home-week-dots">${dots}</div>${bar}`;
  }

  // --- Compteurs odomètre ---------------------------------------------
  function animateNum(el, target, dec, suffix) {
    if (!el) return;
    const dur = 1300, t0 = performance.now();
    const fmt = (v) => v.toLocaleString('fr-FR', {minimumFractionDigits: dec, maximumFractionDigits: dec}) + (suffix || '');
    function frame(t) {
      const p = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(target * e);
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // --- La route vers NYC ----------------------------------------------
  function homeRenderRoute() {
    const wrap = document.getElementById('homeRoute');
    if (!wrap || !PLAN || !PLAN.weeks?.length) { if (wrap) wrap.innerHTML = ''; return; }
    const weeks = PLAN.weeks;
    const N = weeks.length;
    const todayIso = localISODate();
    const curIdx = Math.max(0, weeks.findIndex(w => w.start_date <= todayIso && todayIso <= w.end_date));
    const daysLeft = Math.max(0, Math.round((new Date(PLAN.meta.goal_date) - new Date()) / 86400000));

    const W = 1000, H = 230, padX = 40, topY = 46, botY = 196;
    const kms = weeks.map(w => w.target_km || 0);
    const kmin = Math.min(...kms), kmax = Math.max(...kms) || 1;
    const pts = weeks.map((w, i) => [
      padX + i * (W - 2 * padX) / (N - 1),
      botY - ((kms[i] - kmin) / (kmax - kmin || 1)) * (botY - topY),
    ]);
    // Lissage : courbe passant par les milieux
    let dRoute = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < N; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
      const mx = (x0 + x1) / 2;
      dRoute += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
    }
    const nodes = weeks.map((w, i) => {
      const [x, y] = pts[i];
      const v = w.compliance ? w.compliance.verdict : null;
      const isCur = i === curIdx, isRace = w.phase === 'race';
      let fill = 'none', stroke = '#94a3b8';
      if (v) { fill = (VERDICT_META[v] || {}).color; stroke = fill; }
      if (isCur) { fill = '#5b8af5'; stroke = '#5b8af5'; }
      if (isRace) { fill = '#dc2626'; stroke = '#dc2626'; }
      return `<g class="route-node${isCur ? ' current' : ''}" data-week="${w.week_num}" transform="translate(${x},${y})">
        ${isCur ? '<circle r="13" class="route-pulse" fill="#5b8af5" opacity="0.25"/>' : ''}
        <circle r="${isRace ? 8 : isCur ? 7 : 5}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
        ${isRace ? `<text y="-14" text-anchor="middle" font-size="15">🏁</text>` : ''}
        <title>W${w.week_num} · ${w.phase_label} · ${w.target_km} km${w.compliance ? ` · ${w.compliance.km_pct}%` : ''}</title>
      </g>`;
    }).join('');

    wrap.innerHTML = `
      <div class="route-card">
        <div class="route-head">
          <div class="route-title">La route vers <strong>NYC</strong></div>
          <div class="route-stats">
            <div class="route-stat"><span class="route-stat-v" id="routeDays">0</span><span class="route-stat-l">jours</span></div>
            <div class="route-stat"><span class="route-stat-v" id="routeWeekKm">0</span><span class="route-stat-l">km cette sem.</span></div>
            <div class="route-stat"><span class="route-stat-v" id="routeVma">0</span><span class="route-stat-l">VMA</span></div>
          </div>
        </div>
        <svg viewBox="0 0 ${W} ${H}" class="route-svg" preserveAspectRatio="xMidYMid meet">
          <path d="${dRoute}" class="route-bg" />
          <path d="${dRoute}" class="route-done" id="routeDonePath" />
          ${nodes}
        </svg>
        <div class="route-legend">W${curIdx + 1}/${N} · ${escapeHtml(weeks[curIdx]?.phase_label || '')} · objectif <strong>${escapeHtml(PLAN.meta.strategy_time || PLAN.meta.target_time || '')}</strong></div>
      </div>`;

    // Progression du tracé jusqu'à la semaine courante
    requestAnimationFrame(() => {
      const done = document.getElementById('routeDonePath');
      if (!done || !done.getTotalLength) return;
      const L = done.getTotalLength();
      const frac = curIdx / (N - 1);
      done.style.strokeDasharray = `${L}`;
      done.style.strokeDashoffset = `${L}`;
      done.getBoundingClientRect();
      done.style.transition = 'stroke-dashoffset 1.6s cubic-bezier(0.16,1,0.3,1)';
      done.style.strokeDashoffset = `${L * (1 - frac)}`;
    });

    // Compteurs
    const curW = weeks[curIdx];
    animateNum(document.getElementById('routeDays'), daysLeft, 0, '');
    animateNum(document.getElementById('routeWeekKm'),
      curW?.compliance ? curW.compliance.km_done : (curW?.target_km || 0), 1, '');
    animateNum(document.getElementById('routeVma'), PLAN.meta.vma_used || 0, 1, '');

    wrap.querySelectorAll('.route-node').forEach(n =>
      n.addEventListener('click', (e) => { e.stopPropagation(); activateTab('plan'); }));
  }

  // --- Le duel ----------------------------------------------------------
  function parsePaceLoose(v) {
    if (v == null) return null;
    if (typeof v === 'number') return v > 20 ? v : null;
    const m = String(v).match(/(\d+)'(\d{1,2})/);
    return m ? (+m[1]) * 60 + (+m[2]) : null;
  }

  function homeRenderDuel() {
    const card = document.getElementById('homeDuelCard');
    const wrap = document.getElementById('homeDuel');
    if (!card || !wrap || !PLAN) return;
    const target = PLAN.meta?.paces_sec?.mp_strategy || parsePaceLoose(PLAN.meta?.paces_str?.mp_strategy) || 255;
    const cur = parsePaceLoose(PERF.now?.paces?.marathon);
    const past = parsePaceLoose(PERF.past?.paces?.marathon) || (cur ? cur + 15 : null);
    if (!cur) { card.style.display = 'none'; return; }
    card.style.display = '';

    const span = Math.max(1, past - target);
    const youPct = Math.max(6, Math.min(100, ((past - cur) / span) * 100));
    const weeksTotal = PLAN.meta.weeks_total || 21;
    const curWeek = (PLAN.weeks || []).findIndex(w => w.start_date <= localISODate() && localISODate() <= w.end_date) + 1;
    const ghostPct = Math.max(6, Math.min(100, (curWeek / weeksTotal) * 100));
    const gap = cur - target;
    const gapTxt = gap <= 0
      ? `${Math.abs(gap)}" d'avance sur l'allure cible`
      : `${gap}" à gagner d'ici novembre`;

    wrap.innerHTML = `
      <div class="duel-lane">
        <div class="duel-label">TOI · allure marathon estimée <strong>${fmtPaceApp(cur)}</strong></div>
        <div class="duel-track"><div class="duel-fill duel-you" style="width:${youPct}%"><span class="duel-runner">🏃</span></div></div>
      </div>
      <div class="duel-lane">
        <div class="duel-label">SUB-3H · le rythme à tenir <strong>${fmtPaceApp(target)}</strong></div>
        <div class="duel-track"><div class="duel-fill duel-ghost" style="width:${ghostPct}%"><span class="duel-runner">👻</span></div></div>
      </div>
      <div class="duel-gap ${gap <= 0 ? 'ahead' : 'behind'}">${gapTxt}</div>`;
  }

  function fmtPaceApp(s) {
    if (!s) return '—';
    const m = Math.floor(s / 60), r = Math.round(s % 60);
    return `${m}'${String(r).padStart(2, '0')}"/km`;
  }

  // --- L'empreinte du coureur ------------------------------------------
  function printWeeksData() {
    const byWeek = new Map();
    SESSIONS.forEach(s => {
      const d = s._date;
      const jan = new Date(d.getFullYear(), 0, 1);
      const wk = d.getFullYear() * 100 + Math.floor(((d - jan) / 86400000 + jan.getDay()) / 7);
      if (!byWeek.has(wk)) byWeek.set(wk, {km: 0, ps: [], sessions: []});
      const b = byWeek.get(wk);
      b.km += s.km || 0;
      if (s.ps) b.ps.push(s.ps);
      b.sessions.push(s.km || 0);
    });
    // 52 dernières semaines seulement : au-delà, l'empreinte devient illisible
    return [...byWeek.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v).slice(-52);
  }

  function paceColor(ps) {
    if (!ps) return '#5b8af5';
    if (ps <= 250) return '#ef4444';
    if (ps <= 280) return '#f0923e';
    if (ps <= 310) return '#9b6dff';
    if (ps <= 340) return '#5b8af5';
    return '#22d3a7';
  }

  function drawPrint(canvas, size) {
    const weeks = printWeeksData();
    if (!weeks.length || !canvas) return 0;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = size * dpr; canvas.height = size * dpr;
    canvas.style.width = size + 'px'; canvas.style.height = size + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, size, size);
    const cx = size / 2, cy = size / 2;
    const r0 = size * 0.045, rMax = size * 0.47;
    const step = (rMax - r0) / weeks.length;
    const kmMax = Math.max(...weeks.map(w => w.km)) || 1;
    weeks.forEach((w, i) => {
      const r = r0 + i * step;
      const lw = Math.max(0.5, (w.km / kmMax) * step * 2.4);
      const avgPs = w.ps.length ? w.ps.reduce((a, b) => a + b, 0) / w.ps.length : null;
      ctx.strokeStyle = paceColor(avgPs);
      ctx.globalAlpha = 0.35 + 0.55 * (w.km / kmMax);
      ctx.lineWidth = Math.min(lw, step * 1.6);
      ctx.lineCap = 'round';
      const total = w.sessions.reduce((a, b) => a + b, 0) || 1;
      let ang = i * 0.35;
      const gapA = 0.06;
      const avail = Math.PI * 2 - gapA * w.sessions.length;
      w.sessions.forEach(km => {
        const a1 = ang + (km / total) * avail;
        ctx.beginPath();
        ctx.arc(cx, cy, r, ang, a1);
        ctx.stroke();
        ang = a1 + gapA;
      });
    });
    ctx.globalAlpha = 1;
    return weeks.length;
  }

  function homeRenderPrint() {
    const canvas = document.getElementById('printCanvas');
    if (!canvas) return;
    const n = drawPrint(canvas, Math.min(320, (canvas.parentElement?.clientWidth || 320)));
    const sub = document.getElementById('homePrintSub');
    if (sub) sub.textContent = `${n} dernières semaines`;
    document.getElementById('printFullBtn')?.addEventListener('click', openPrintFull);
    canvas.addEventListener('click', openPrintFull);
    document.getElementById('printClose')?.addEventListener('click', () => {
      document.getElementById('printOverlay').hidden = true;
      document.body.style.overflow = '';
    });
  }

  function openPrintFull() {
    const ov = document.getElementById('printOverlay');
    const canvas = document.getElementById('printFullCanvas');
    if (!ov || !canvas) return;
    ov.hidden = false;
    document.body.style.overflow = 'hidden';
    const size = Math.min(window.innerWidth, window.innerHeight) * 0.9;
    drawPrint(canvas, size);
    const cap = document.getElementById('printCaption');
    if (cap) {
      const totKm = Math.round(SESSIONS.reduce((a, s) => a + (s.km || 0), 0));
      cap.textContent = `${PROFILE.name || 'Toi'} · ${SESSIONS.length} séances · ${totKm.toLocaleString('fr-FR')} km — une empreinte unique`;
    }
  }

  function renderHomeTab() {
    homeRenderRoute();
    homeRenderDuel();
    homeRenderLast();
    homeRenderWeek();
  }

  function renderPlanTab() {
    // Nouvelles vues plan engine
    planRenderTodayCard();
    planRenderCoach();
    planRenderAdaptations();
    planRenderCurrentWeek();
    planRenderPaces();
    planRenderCalendar();
    // Anciennes vues conservées
    planRenderPhase();
    planRenderVolumeChart();
    planRenderDistribution();
    planRenderRecentVsReco();
  }

  function initPlanTab() {
    renderPlanTab();
    renderHomeTab();
    setupDaySheet();
  }

  // ===== 11. INIT ===========================================================
  function init() {
    renderHero();
    renderOverviewKPIs();
    chartWeekly();
    chartMonthlyPace();
    chartMonthlyHR();
    renderLastSession();
    setupTabs();
    setupYearFilter();
    rerenderRaceTab();
    setupRaceModal();
    initVolumeTab();
    initSessTab();
    initAeroTab();
    initProgTab();
    initChargeTab();
    initPredTab();
    initCompTab();
    initPlanTab();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
