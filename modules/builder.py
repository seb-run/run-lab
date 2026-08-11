"""
seb-metrics — modules/builder.py
========================================
Assemblage du dashboard HTML autonome depuis :
  - la liste des sessions parsées
  - le profil utilisateur (nom, birthdate, zones FC, objectif)
  - les templates Jinja2 (HTML + CSS + JS)

Sortie : un seul fichier index.html embarquant tout (CSS inliné, JS inliné,
données JSON inlinées dans une balise <script type="application/json">).
"""

from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Optional

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError as e:
    raise ImportError("Jinja2 est requis. Installe avec : pip install jinja2") from e
from modules.races import build_races_payload

# ============================================================================
# CHARGEMENT TEMPLATES
# ============================================================================

def _load_template_env(templates_dir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _read_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================================
# PROFIL UTILISATEUR
# ============================================================================

DEFAULT_PROFILE = {
    'name': 'Sébastien',
    'birthdate': '1992-05-22',          # ISO YYYY-MM-DD
    'role': 'Chef de Projets FFF',
    'hr_zones': {
        'z1_max': 135,
        'z2_max': 150,
        'z3_max': 166,
        'z4_max': 175,
    },
    'pb_marathon': '2h49\'41"',
    'goal_name': 'Marathon de Cologne',
    'goal_date': '2026-10-04',
    'goal_time': '2h43\'00"',
    'github_repo': '',                  # rempli par INSTALL.command
}


def build_profile(overrides: Optional[dict] = None) -> dict:
    """Construit le profil utilisateur en fusionnant les overrides CLI."""
    profile = dict(DEFAULT_PROFILE)
    profile['hr_zones'] = dict(DEFAULT_PROFILE['hr_zones'])
    if overrides:
        for k, v in overrides.items():
            if k == 'hr_zones' and isinstance(v, dict):
                profile['hr_zones'].update(v)
            elif v is not None:
                profile[k] = v
    return profile


# ============================================================================
# CALCULS D'AGRÉGATS (pour l'onglet Vue d'ensemble)
# ============================================================================

def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, '%d/%m/%Y')


def compute_overview(sessions: list[dict]) -> dict:
    """Calcule les KPIs principaux pour l'onglet Vue d'ensemble."""
    if not sessions:
        return {
            'total_sessions': 0,
            'total_km': 0,
            'total_hours': 0,
            'avg_pace': '--',
            'last_session': None,
            'years': [],
            'weekly_volume': [],
            'monthly_pace': [],
            'monthly_hr': [],
        }

    total_km = round(sum(s['km'] for s in sessions), 1)
    total_sec = sum(s.get('dur_s', 0) for s in sessions)
    total_hours = round(total_sec / 3600, 1)

    # Allure moyenne pondérée par la distance
    paces = [s['ps'] for s in sessions if s.get('ps')]
    weights = [s['km'] for s in sessions if s.get('ps')]
    if paces and weights:
        avg_pace_sec = sum(p * w for p, w in zip(paces, weights)) / sum(weights)
        m, sc = divmod(round(avg_pace_sec), 60)
        avg_pace = f"{m}'{sc:02d}\"/km"
    else:
        avg_pace = '--'

    # Années disponibles pour les filtres
    years = sorted({_parse_date(s['d']).year for s in sessions}, reverse=True)

    # Volume hebdomadaire (52 dernières semaines)
    from collections import defaultdict
    weekly: dict[str, float] = defaultdict(float)
    monthly_pace_data: dict[str, list[tuple[float, float]]] = defaultdict(list)  # (pace, weight)
    monthly_hr_data: dict[str, list[int]] = defaultdict(list)

    for s in sessions:
        d = _parse_date(s['d'])
        iso_year, iso_week, _ = d.isocalendar()
        wk_key = f"{iso_year}-W{iso_week:02d}"
        weekly[wk_key] += s['km']

        mo_key = f"{d.year}-{d.month:02d}"
        if s.get('ps'):
            monthly_pace_data[mo_key].append((s['ps'], s['km']))
        if s.get('fc'):
            monthly_hr_data[mo_key].append(s['fc'])

    weekly_sorted = sorted(weekly.items())[-52:]  # 52 dernières semaines

    monthly_pace = []
    for mo, items in sorted(monthly_pace_data.items())[-24:]:
        total_w = sum(w for _, w in items)
        if total_w > 0:
            avg = sum(p * w for p, w in items) / total_w
            monthly_pace.append({'mo': mo, 'pace': round(avg)})

    monthly_hr = []
    for mo, items in sorted(monthly_hr_data.items())[-24:]:
        monthly_hr.append({'mo': mo, 'hr': round(sum(items) / len(items))})

    return {
        'total_sessions': len(sessions),
        'total_km': total_km,
        'total_hours': total_hours,
        'avg_pace': avg_pace,
        'last_session': sessions[0] if sessions else None,
        'years': years,
        'weekly_volume': [{'wk': k, 'km': round(v, 1)} for k, v in weekly_sorted],
        'monthly_pace': monthly_pace,
        'monthly_hr': monthly_hr,
    }


# ============================================================================
# BUILD HTML
# ============================================================================

def build_html(
    sessions: list[dict],
    profile: dict,
    templates_dir: str,
    output_path: str,
    config: Optional[dict] = None,
    plan: Optional[dict] = None,
) -> None:
    """
    Génère le fichier index.html autonome.

    Args:
      sessions      : liste des sessions parsées (triées date desc)
      profile       : dict de profil utilisateur
      templates_dir : dossier contenant index.html.j2, app.js, styles.css
      output_path   : chemin du fichier de sortie
    """
    env = _load_template_env(templates_dir)

    # Lecture des assets statiques (CSS + JS)
    css_path = os.path.join(templates_dir, 'styles.css')
    js_path = os.path.join(templates_dir, 'app.js')
    css_content = _read_file(css_path) if os.path.exists(css_path) else ""
    js_content = _read_file(js_path) if os.path.exists(js_path) else ""

    # Calcul des agrégats
    overview = compute_overview(sessions)

    # Estimation VMA + allures de forme + tendance 30j
    try:
        from modules.performance import compute_trend, compute_history
        performance = compute_trend(sessions)
    except Exception as e:
        print(f"  ⚠ Erreur calcul performance : {e}")
        performance = {'now': {'vma': None, 'paces': {}, 'confidence': 0},
                       'past': {'vma': None, 'paces': {}, 'confidence': 0},
                       'delta': {'vma': None, 'paces': {}},
                       'window_days': 30}

    # Historique VMA pour l'onglet Progression VMA
    try:
        performance_history = compute_history(sessions, step_days=14)
    except Exception as e:
        print(f"  ⚠ Erreur calcul historique VMA : {e}")
        performance_history = []

    # Rattrapage rétroactif des remplacements validés
    # ------------------------------------------------
    # Les propositions `change_type` validées avant que apply_proposal.py sache
    # les traiter n'ont créé qu'une `coach_notes` en langage naturel. La cible
    # d'origine est restée, et le scoring compare toujours contre elle.
    # On détecte ici ces notes et on pose le drapeau qui manque, pour que le
    # prochain build score correctement — sans attendre une régénération.
    def _looks_like_replacement(note):
        if not note.get('validated'): return False
        if note.get('kind') == 'replacement': return False   # déjà traité
        txt = (note.get('text') or '').lower()
        return txt.startswith('remplace') or 'remplacer' in txt[:40]

    if plan and plan.get('weeks'):
        try:
            from scripts._shoes_nyc import assign as _assign_shoe
        except Exception:
            _assign_shoe = None
        propagated = 0
        for w in plan['weeks']:
            for day in w.get('days', []):
                if day.get('_replaced_by_coach'):
                    continue
                repl = next((n for n in day.get('coach_notes', [])
                             if _looks_like_replacement(n)), None)
                if not repl:
                    continue
                day['_replaced_by_coach'] = True
                day['_replaced_from'] = {
                    'title': day.get('title'),
                    'target_pace': day.get('target_pace'),
                    'type': day.get('type'),
                }
                # Cible d'allure effacée : le scoring ne juge plus l'allure
                day.pop('target_pace', None)
                propagated += 1
                # Chaussure recalculée sur le nouveau type quand possible
                if _assign_shoe:
                    try: _assign_shoe(day)
                    except Exception: pass
        if propagated:
            print(f"  ▸ {propagated} remplacement(s) validé(s) — flag rétroactif posé")

        # Cascade : quand une séance clé a été remplacée par autre chose, le
        # jour suivant peut ne plus avoir de sens dans sa forme actuelle
        # (récupération prévue pour une charge qu'on n'a pas produite, séance
        # dépendante déplacée…). Plutôt que de bricoler mécaniquement, on
        # inscrit une note explicite sur le lendemain, à charge du coach ou
        # de Seb de trancher au prochain matin.
        from datetime import date as _date, timedelta as _td
        by_iso = {d['date']: d for w in plan['weeks'] for d in w.get('days', [])
                  if d.get('date')}
        for iso, day in list(by_iso.items()):
            if not day.get('_replaced_by_coach'):
                continue
            if day.get('_replaced_from', {}).get('type') not in ('seuil','vma','mp','tempo','long'):
                continue
            try:
                nxt_iso = (_date.fromisoformat(iso) + _td(days=1)).isoformat()
            except Exception:
                continue
            nxt = by_iso.get(nxt_iso)
            if not nxt or nxt.get('_cascade_from'):
                continue
            orig = day['_replaced_from'].get('title', 'séance clé')
            nxt.setdefault('coach_notes', []).insert(0, {
                'kind': 'cascade',
                'text': (f"Hier tu as remplacé « {orig} » par un footing : "
                         "aujourd'hui la récupération prévue peut être "
                         "conservée, ou rebasculée en séance clé si les "
                         "sensations le permettent. À trancher au réveil."),
            })
            nxt['_cascade_from'] = iso

    # Analyse du coach IA (déposée par scripts/ci/ai_coach.py, optionnelle)
    coach = None
    try:
        from modules.paths import data_dir
        coach_path = data_dir() / 'coach_analysis.json'
        if coach_path.exists():
            coach = json.loads(coach_path.read_text(encoding='utf-8'))
        # Historique des décisions : coach_analysis ne garde que les mineures
        # appliquées, les refus vivent dans coach_proposals. On les remonte
        # pour que l'app puisse afficher « refusée le X » — sans quoi
        # l'utilisateur peut craindre qu'un refus n'ait pas été pris en compte.
        prop_path = data_dir() / 'coach_proposals.json'
        if coach and prop_path.exists():
            props = (json.loads(prop_path.read_text(encoding='utf-8')) or {}).get('proposals', [])
            coach['rejected'] = sorted(
                [p for p in props if p.get('status') == 'rejected'],
                key=lambda p: p.get('decided_at') or '', reverse=True)[:5]
            coach['expired'] = sorted(
                [p for p in props if p.get('status') == 'expired'],
                key=lambda p: p.get('decided_at') or '', reverse=True)[:3]
    except Exception as e:
        print(f"  ⚠ Lecture coach_analysis.json : {e}")

    # Débrief IA de la dernière séance (scripts/ci/session_debrief.py, optionnel)
    debrief = None
    try:
        from modules.paths import data_dir
        debrief_path = data_dir() / 'session_debrief.json'
        if debrief_path.exists():
            debrief = json.loads(debrief_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"  ⚠ Lecture session_debrief.json : {e}")

    # Payload de données pour le JS (injecté en JSON inline)
    data_payload = {
        'sessions': sessions,
        'profile': profile,
        'overview': overview,
        'performance': performance,
        'performance_history': performance_history,
        'races': build_races_payload(config or {}),
        'plan': plan,
        'coach': coach,
        'debrief': debrief,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
    }

    # Rendu du template principal
    template = env.get_template('index.html.j2')
    html = template.render(
        profile=profile,
        overview=overview,
        performance=performance,
        css_content=css_content,
        js_content=js_content,
        data_payload_json=json.dumps(data_payload, ensure_ascii=False, default=str),
        generated_at=data_payload['generated_at'],
    )

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
