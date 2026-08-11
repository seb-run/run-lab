#!/usr/bin/env python3
"""
seb-metrics — scripts/ci/ai_coach.py
========================================
Coach IA : analyse les séances récentes vs plan et propose des ajustements.

Politique d'autonomie (validée par Seb) :
  - MINEUR (appliqué automatiquement, garde-fous codés en dur) :
      · ajustement de volume d'un jour futur, borné à ±10 %
      · note ajoutée à la description d'une séance future
  - MAJEUR (jamais appliqué seul → data/coach_proposals.json, statut "pending",
    affiché dans le dashboard et validé via le briefing du matin) :
      · déplacement/suppression de séance, changement de type ou d'allure cible,
        restructuration de semaine, changement de stratégie course

Sorties :
  data/coach_analysis.json   analyse du jour + ajustements appliqués/pendants
  data/coach_proposals.json  propositions majeures (historique + statuts)
  data/plan_nyc.json         modifié si ajustements mineurs

Env : ANTHROPIC_API_KEY (requis), ANTHROPIC_MODEL (défaut claude-sonnet-5),
      SEB_DATA_DIR (défaut ./data)
"""
from __future__ import annotations
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = Path(os.environ.get('SEB_DATA_DIR') or (REPO_ROOT / 'data'))
PLAN_PATH = DATA_DIR / 'plan_nyc.json'
ANALYSIS_PATH = DATA_DIR / 'coach_analysis.json'
PROPOSALS_PATH = DATA_DIR / 'coach_proposals.json'

MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-5')

# Garde-fous ajustements mineurs
MINOR_KM_MAX_PCT = 0.10          # ±10 % max sur le volume d'un jour
MINOR_HORIZON_DAYS = 10          # on ne touche pas au-delà de 10 jours


# ============================================================================
# CONTEXTE POUR LE MODÈLE
# ============================================================================

def _fmt_splits(splits: list[dict], max_laps: int = 30) -> str:
    """
    Splits compactés : "1:5'18/136 2:5'21/141 ..." (km : allure/FC[/cadence]).
    Tronqué au-delà de max_laps pour borner la taille du contexte.
    """
    out = []
    for i, s in enumerate(splits[:max_laps], 1):
        ps = s.get('ps')
        if not ps:
            continue
        m, sec = divmod(int(ps), 60)
        piece = f"{i}:{m}'{sec:02d}"
        if s.get('fc'):
            piece += f"/{s['fc']}"
        if s.get('ca'):
            piece += f"/{s['ca']}spm"
        out.append(piece)
    if len(splits) > max_laps:
        out.append(f"(+{len(splits) - max_laps} laps)")
    return ' '.join(out)


def build_context(plan: dict) -> dict:
    today = date.today()
    recent, upcoming, weeks_summary = [], [], []

    for w in plan.get('weeks', []):
        if w.get('compliance'):
            weeks_summary.append({
                'week': w['week_num'], 'phase': w['phase'],
                **{k: w['compliance'][k] for k in
                   ('km_pct', 'km_done', 'km_planned', 'sessions_done',
                    'sessions_planned', 'keys_success', 'keys_total', 'verdict')},
            })
        for d in w.get('days', []):
            try:
                dd = date.fromisoformat(d['date'])
            except Exception:
                continue
            if today - timedelta(days=14) <= dd < today:
                entry = {
                    'date': d['date'], 'title': d.get('title'), 'type': d.get('type'),
                    'planned_km': d.get('km'), 'key': d.get('key'),
                    'status': d.get('status'), 'target_pace': d.get('target_pace'),
                }
                if d.get('actual'):
                    a = d['actual']
                    entry['actual'] = {k: a.get(k) for k in
                                       ('km', 'pace_str', 'fc', 'cadence',
                                        'duration_min')}
                    # Ressenti saisi par Sébastien (description Strava)
                    if a.get('note'):
                        entry['sensations'] = a['note']
                    # Splits km/km : allure, FC, cadence — compactés en texte
                    # pour rester lisibles sans exploser le contexte.
                    if a.get('splits'):
                        entry['splits'] = _fmt_splits(a['splits'])
                    # Dynamique de course Garmin, si le .fit est remonté
                    if a.get('dyn'):
                        dy = a['dyn']
                        entry['garmin'] = {k: dy.get(k) for k in
                                           ('te_aero', 'te_ana', 'load', 'rpe',
                                            'feel_label', 'temp_c', 'balance_l',
                                            'flags') if dy.get(k) is not None}
                        if (dy.get('drift') or {}).get('stance'):
                            entry['garmin']['stance_drift_pct'] = \
                                dy['drift']['stance'].get('pct')
                        if (dy.get('drift') or {}).get('step'):
                            entry['garmin']['step_drift_pct'] = \
                                dy['drift']['step'].get('pct')
                if d.get('score'):
                    entry['score'] = {k: d['score'].get(k) for k in
                                      ('points', 'verdict', 'volume_pct', 'pace_delta_s')}
                    if d['score'].get('hr'):
                        entry['hr'] = {k: d['score']['hr'].get(k) for k in
                                       ('avg', 'cap', 'over_cap',
                                        'decoupling_pct', 'flags')}
                recent.append(entry)
            elif today <= dd <= today + timedelta(days=MINOR_HORIZON_DAYS):
                upcoming.append({
                    'date': d['date'], 'dow': d.get('dow'), 'title': d.get('title'),
                    'type': d.get('type'), 'km': d.get('km'), 'key': d.get('key'),
                    'target_pace': d.get('target_pace'),
                })

    meta = plan.get('meta', {})
    return {
        'today': today.isoformat(),
        'goal': {k: meta.get(k) for k in
                 ('goal_name', 'goal_date', 'target_time', 'strategy_time',
                  'weeks_total', 'vma_used')},
        'paces': meta.get('paces_str', {}),
        'auto_adaptations_deja_appliquees': plan.get('adaptations', []),
        'weeks_summary': weeks_summary[-4:],
        'last_14_days': recent,
        'next_10_days': upcoming,
    }


SYSTEM_PROMPT = """Tu es le coach running de Sébastien. Objectif : NYC Marathon (2026-11-01), sub-3h.
Tu reçois l'état du plan : 14 derniers jours scorés (réussie/partielle/échouée/manquée), conformité hebdo, 10 prochains jours.

Pour les séances récentes tu peux aussi recevoir :
  · "splits" : allure/FC/cadence km par km, format "3:5'21/141/176spm". Sers-t'en pour
    distinguer une séance mal partie d'une séance qui s'effondre à la fin.
  · "hr" : FC moyenne, consigne du jour (cap), dépassement, et "decoupling_pct" =
    dérive du rapport vitesse/FC entre 1re et 2e moitié (méthode Friel).
    Repères : < 5 % normal, > 8 % notable. ATTENTION : la chaleur, l'humidité et la
    déshydratation produisent la même dérive que la fatigue. Ne conclus jamais à la
    fatigue sur la seule dérive — croise avec les sensations, la période de l'année
    et l'historique récent. Une FC au-dessus de la consigne avec des sensations
    faciles par temps chaud n'est pas un signal d'alerte.
  · "garmin" : données de la montre absentes de Strava. "stance_drift_pct" et
    "step_drift_pct" = évolution du temps de contact au sol et de la longueur de
    foulée entre le 1er et le dernier tiers. Un contact qui s'allonge de plus de
    4 % ou une foulée qui raccourcit de plus de 3 % = fatigue MÉCANIQUE réelle,
    à distinguer d'une simple dérive cardiaque. "rpe" (0-10) et "feel_label" sont
    saisis par Sébastien sur la montre en fin de séance : traite-les comme sa
    parole. "balance_l" = % d'appui à gauche, pertinent vu son historique Achille.
  · "sensations" : texte écrit par Sébastien lui-même après la séance (météo, RPE,
    douleurs, contexte). C'est la source la plus fiable du lot : elle prime sur
    l'interprétation des chiffres en cas de contradiction. Si elle est absente, ne
    l'invente pas et ne suppose pas que tout allait bien.

Réponds UNIQUEMENT avec un JSON valide, sans markdown :
{
  "headline": "1 phrase, l'essentiel du moment",
  "analysis": "Analyse en français, 4-8 phrases : forme actuelle, ce que disent les scores (volume, allures, régularité), risque principal, focus de la semaine. Tutoiement, ton direct de coach.",
  "proposals": [
    {
      "severity": "minor" | "major",
      "kind": "volume_adjust" | "add_note" | "move_session" | "change_type" | "change_pace" | "restructure_week" | "other",
      "date": "YYYY-MM-DD",
      "field": "km" | "description_note" | null,
      "new_value": <nombre pour km, texte pour note, sinon description du changement>,
      "reason": "justification courte",
      "replacement": {
        "title": "titre court de la nouvelle séance (ex. Footing récup)",
        "type":  "recovery | easy | endurance | tempo | seuil | vma | long | shake",
        "km":    12.0,
        "target_pace": "5'40\"/km",
        "description": "consigne complète pour Sébastien (4-6 lignes max)"
      }
    }
  ]
}

Règles :
- "minor" = uniquement volume_adjust (±10 % max) ou add_note sur un jour futur. Tout le reste est "major".
- `replacement` : obligatoire pour change_type, move_session et change_pace, absent pour les autres. C'est ce bloc qui remplace concrètement la séance quand Sébastien valide — sans lui, la cible d'origine reste et son réalisé sera jugé contre elle.
- Ne propose des changements QUE si les données le justifient. Zéro proposition est une réponse valable.
- Jamais de modification du jour de course.
- Si plusieurs séances clés échouées/manquées, privilégie la réduction de charge, pas l'ajout.
- Les adaptations automatiques déjà appliquées par le moteur te sont fournies : ne les duplique pas."""


def call_model(context: dict) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    # max_tokens couvre AUSSI les blocs de raisonnement du modèle. À 2000, le
    # raisonnement consommait tout le budget et la réponse revenait sans aucun
    # bloc texte — d'où le JSONDecodeError sur une chaîne vide.
    msg = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}],
    )
    text = ''.join(b.text for b in msg.content
                   if getattr(b, 'type', '') == 'text').strip()
    if not text:
        kinds = ', '.join(sorted({getattr(b, 'type', '?') for b in msg.content}))
        raise RuntimeError(
            f'réponse sans bloc texte (blocs reçus : {kinds}, '
            f'stop_reason={msg.stop_reason}) — augmenter max_tokens')
    # Tolère un éventuel bloc de code
    if text.startswith('```'):
        text = text.strip('`')
        text = text[text.index('{'):text.rindex('}') + 1]
    return json.loads(text)


# ============================================================================
# APPLICATION DES PROPOSITIONS
# ============================================================================

def find_day(plan: dict, iso: str):
    for w in plan.get('weeks', []):
        for d in w.get('days', []):
            if d.get('date') == iso:
                return d
    return None


def apply_minor(plan: dict, prop: dict) -> tuple[bool, str]:
    """Applique une proposition mineure avec garde-fous. Retourne (ok, détail)."""
    today = date.today()
    try:
        dd = date.fromisoformat(prop.get('date', ''))
    except Exception:
        return False, 'date invalide'
    if dd <= today:
        return False, 'jour passé ou en cours'
    if dd > today + timedelta(days=MINOR_HORIZON_DAYS):
        return False, f'au-delà de {MINOR_HORIZON_DAYS} jours'
    day = find_day(plan, prop['date'])
    if not day:
        return False, 'jour introuvable'
    if day.get('type') == 'race':
        return False, 'jour de course intouchable'

    if prop.get('kind') == 'volume_adjust' and prop.get('field') == 'km':
        try:
            new_km = float(prop.get('new_value'))
        except (TypeError, ValueError):
            return False, 'valeur km invalide'
        cur = float(day.get('km') or 0)
        if cur <= 0:
            return False, 'pas de volume à ajuster (repos)'
        lo, hi = cur * (1 - MINOR_KM_MAX_PCT), cur * (1 + MINOR_KM_MAX_PCT)
        clamped = round(max(lo, min(hi, new_km)), 1)
        day['km'] = clamped
        # Les consignes vivent à part de la description : elles s'accumulaient
        # dans le corps du texte et le rendaient illisible au fil des builds.
        day.setdefault('coach_notes', []).append({
            'kind': 'volume', 'from': cur, 'to': clamped,
            'reason': prop.get('reason', ''),
        })
        return True, f"{prop['date']} : {cur:g}→{clamped:g} km"

    if prop.get('kind') == 'add_note':
        note = str(prop.get('new_value') or '').strip()[:300]
        if not note:
            return False, 'note vide'
        day.setdefault('coach_notes', []).append({'kind': 'note', 'text': note})
        return True, f"{prop['date']} : note ajoutée"

    return False, 'kind non autorisé en minor'


def main():
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('⚠ ANTHROPIC_API_KEY absent — coach IA sauté')
        return

    if not PLAN_PATH.exists():
        print('⚠ Pas de plan — coach IA sauté')
        return
    plan = json.loads(PLAN_PATH.read_text(encoding='utf-8'))

    context = build_context(plan)

    # Économie d'appels : le coach tournait à CHAQUE build, y compris les
    # rebuilds déclenchés par un simple changement de code. Tant qu'aucune
    # séance nouvelle n'est arrivée et que l'analyse a moins de 12 h, il n'y a
    # rien de neuf à dire.
    signature = json.dumps(context['last_14_days'][-3:], ensure_ascii=False)
    if ANALYSIS_PATH.exists() and '--force' not in sys.argv:
        try:
            prev = json.loads(ANALYSIS_PATH.read_text(encoding='utf-8'))
            age_h = (datetime.now()
                     - datetime.fromisoformat(prev['generated_at'])).total_seconds() / 3600
            if prev.get('signature') == signature and age_h < 12:
                print(f'✓ Analyse encore valable ({age_h:.1f} h, rien de neuf) '
                      '— appel modèle évité.')
                return
        except Exception:  # noqa: BLE001
            pass

    print(f"▸ Coach IA ({MODEL}) : {len(context['last_14_days'])} jours récents, "
          f"{len(context['next_10_days'])} jours à venir")
    try:
        result = call_model(context)
    except Exception as e:
        # Consigné dans les données : cette étape est non bloquante, donc une
        # panne resterait invisible dans un build vert.
        try:
            from modules.ci_status import note
            note('coach', ok=False, message=f'{type(e).__name__}: {e}')
        except Exception:  # noqa: BLE001
            pass
        print(f'✗ Appel modèle échoué : {e}')
        sys.exit(1)

    applied, pending = [], []
    plan_modified = False
    for prop in result.get('proposals', []):
        prop.setdefault('id', uuid.uuid4().hex[:8])
        if prop.get('severity') == 'minor':
            ok, detail = apply_minor(plan, prop)
            if ok:
                plan_modified = True
                applied.append({**prop, 'detail': detail})
                print(f'  ✓ mineur appliqué : {detail}')
            else:
                # Mineur refusé par les garde-fous → escaladé en proposition
                prop['guardrail_reject'] = detail
                pending.append(prop)
                print(f'  ↗ mineur escaladé ({detail})')
        else:
            pending.append(prop)
            print(f"  ● majeur en attente : {prop.get('kind')} {prop.get('date', '')}")

    # Persistance des propositions majeures (merge avec l'historique)
    proposals_doc = {'proposals': []}
    if PROPOSALS_PATH.exists():
        try:
            proposals_doc = json.loads(PROPOSALS_PATH.read_text(encoding='utf-8'))
        except Exception:
            pass
    existing = proposals_doc.get('proposals', [])
    # Purge : garde les 30 dernières, marque expirées celles dont la date est passée
    today_iso = date.today().isoformat()
    for p in existing:
        if p.get('status') == 'pending' and p.get('date') and p['date'] < today_iso:
            p['status'] = 'expired'
    for p in pending:
        p['status'] = 'pending'
        p['created_at'] = datetime.now().isoformat(timespec='seconds')
        existing.append(p)
    proposals_doc['proposals'] = existing[-30:]
    PROPOSALS_PATH.write_text(
        json.dumps(proposals_doc, ensure_ascii=False, indent=1), encoding='utf-8')

    # Analyse du jour
    analysis = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'model': MODEL,
        'signature': signature,
        'headline': result.get('headline', ''),
        'analysis': result.get('analysis', ''),
        'applied': applied,
        'pending': [p for p in proposals_doc['proposals'] if p.get('status') == 'pending'],
    }
    ANALYSIS_PATH.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"✓ Analyse : {analysis['headline'][:80]}")
    try:
        from modules.ci_status import note
        note('coach', ok=True)
    except Exception:  # noqa: BLE001
        pass

    if plan_modified:
        PLAN_PATH.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print('✓ Plan mis à jour (ajustements mineurs)')


if __name__ == '__main__':
    main()
