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

    # Corpus corporel : historique poids + masse grasse pour tendance mesurée.
    # Le coach l'utilise pour composer l'état de forme, jamais pour édicter
    # un objectif de poids sans contexte.
    body = None
    try:
        from modules.config import load_config
        cfg = load_config() or {}
        prof = (cfg.get('profile') or {})
        hist = ((prof.get('body') or {}).get('history') or [])
        if hist:
            body = {
                'height_cm': prof.get('height_cm'),
                'history': hist[-6:],  # 6 dernières mesures suffisent
            }
    except Exception:
        pass

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
        'body': body,
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
  · "body" (optionnel) : historique poids/masse grasse. Si présent, tu peux
    l'utiliser pour composer l'état de forme, en TENDANCE mesurée (pente sur
    les 3-4 derniers relevés). N'édicte JAMAIS un objectif chiffré de poids
    sans que Sébastien te l'ait demandé. Un ratio watts/kg descendant est
    positif tant qu'il s'accompagne d'une masse grasse qui diminue et
    d'une performance stable ; s'il monte alors que la MG descend, tu peux
    évoquer la piste d'une masse musculaire fonctionnelle qui se réorganise
    — sans conclure.

Réponds UNIQUEMENT avec un JSON valide, sans markdown :
{
  "headline": "1 phrase, l'essentiel du moment",
  "analysis": "Analyse en français, 4-8 phrases : forme actuelle, ce que disent les scores (volume, allures, régularité), risque principal, focus de la semaine. Tutoiement, ton direct de coach.",
  "forme": {
    "score": 0-100,
    "verdict": "bon" | "surveiller" | "alerte",
    "headline": "Une phrase courte (max 65 caractères) qui synthétise l'état — ex. « Progression solide, tendon à surveiller »",
    "detail": "2-3 phrases : ce qui va, ce qui mérite attention, quel focus pour les prochains jours. Ton coach direct, tutoiement. Cite au moins un chiffre concret pour ancrer.",
    "indicateurs": {
      "fraicheur": {
        "valeur": "Chaîne courte — ex. « +8 », « −12 », « équilibre »",
        "trend": "up" | "down" | "flat",
        "etat": "ok" | "watch" | "alert",
        "note": "≤ 25 caractères : « bien récupéré », « dette 2 jours »…"
      },
      "compliance": {
        "valeur": "Chaîne courte — ex. « 74/74 km · 3/3 clés »",
        "trend": "up" | "down" | "flat",
        "etat": "ok" | "watch" | "alert",
        "note": "≤ 25 caractères — ex. « semaine tenue »"
      },
      "aerobie": {
        "valeur": "Chaîne courte — ex. « 2,4 % », « 6,1 % »",
        "trend": "up" | "down" | "flat",
        "etat": "ok" | "watch" | "alert",
        "note": "≤ 25 caractères — ex. « dérive dernière SL »"
      },
      "achille": {
        "valeur": "Chaîne courte — ex. « stable », « 6,1 % », « 3/10 »",
        "trend": "up" | "down" | "flat",
        "etat": "ok" | "watch" | "alert",
        "note": "≤ 25 caractères — ex. « asym. samedi »"
      }
    }
  },
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


def build_forme_fallback(context: dict, error: str = '') -> dict:
    """Compose un `forme` minimal sans appel modèle.

    S'exécute quand Anthropic échoue : le pipeline continue d'écrire un
    coach_analysis.json exploitable côté UI, quitte à ce que les phrases
    soient sèches. Les quatre indicateurs sont calculés à partir des données
    déjà disponibles dans le contexte (compliance, verdicts récents,
    ressenti Achille de la dernière séance longue).
    """
    recent = context.get('last_14_days') or []
    weeks = context.get('weeks_summary') or []
    body = context.get('body') or {}

    # Compliance : dernière semaine avec des données
    last_week = weeks[-1] if weeks else {}
    keys_ok = last_week.get('keys_success', 0)
    keys_tot = last_week.get('keys_total', 0)
    km_pct = last_week.get('km_pct', 0)
    if keys_tot > 0:
        compliance_str = f"{last_week.get('km_done', 0):.0f}/{last_week.get('km_planned', 0):.0f} km · {keys_ok}/{keys_tot} clés"
    else:
        compliance_str = f"{km_pct} %"
    compliance_etat = 'ok' if km_pct >= 80 else 'watch' if km_pct >= 60 else 'alert'

    # Fraîcheur : pas de TSB direct ici, on approxime avec les 3 derniers scores
    recent_scores = [d.get('score', {}).get('points') for d in recent[-5:]
                     if d.get('score')]
    if recent_scores:
        avg = sum(recent_scores) / len(recent_scores)
        fraicheur_str = f"{avg:.0f}/100 moy."
        fraicheur_etat = 'ok' if avg >= 65 else 'watch' if avg >= 45 else 'alert'
    else:
        fraicheur_str, fraicheur_etat = '—', 'ok'

    # Efficacité aérobie : dernière dérive cardiaque disponible
    last_dr = next(
        (d.get('hr', {}).get('decoupling_pct') for d in reversed(recent)
         if d.get('hr', {}).get('decoupling_pct') is not None), None)
    if last_dr is not None:
        aerobie_str = f"{last_dr:.1f} %"
        aerobie_etat = 'ok' if last_dr < 5 else 'watch' if last_dr < 8 else 'alert'
    else:
        aerobie_str, aerobie_etat = '—', 'ok'

    # Achille : cherche un flag ou une asymétrie forte
    achille_alerts = 0
    for d in recent[-5:]:
        garmin = d.get('garmin') or {}
        bal = garmin.get('balance_l')
        if bal is not None and abs(50 - bal) > 3:
            achille_alerts += 1
        sensations = (d.get('sensations') or '').lower()
        if any(k in sensations for k in ('achille', 'tendon', 'douleur')):
            achille_alerts += 1
    if achille_alerts >= 2:
        achille_str, achille_etat = 'signaux', 'watch'
    else:
        achille_str, achille_etat = 'stable', 'ok'

    # Verdict global : plus mauvais des 4 états
    etats = [fraicheur_etat, compliance_etat, aerobie_etat, achille_etat]
    if 'alert' in etats:
        verdict, score = 'alerte', 35
    elif 'watch' in etats:
        verdict, score = 'surveiller', 60
    else:
        verdict, score = 'bon', 78

    return {
        'score': score, 'verdict': verdict,
        'headline': f'État composé automatiquement ({verdict})',
        'detail': ('Le modèle IA n\'a pas répondu — indicateurs calculés '
                   f"à partir des données locales.{' Erreur : ' + error[:80] if error else ''}"),
        'indicateurs': {
            'fraicheur':  {'valeur': fraicheur_str, 'trend': 'flat',
                           'etat': fraicheur_etat, 'note': 'moyenne 5 dernières'},
            'compliance': {'valeur': compliance_str, 'trend': 'flat',
                           'etat': compliance_etat, 'note': 'semaine en cours'},
            'aerobie':    {'valeur': aerobie_str, 'trend': 'flat',
                           'etat': aerobie_etat, 'note': 'dernière avec FC'},
            'achille':    {'valeur': achille_str, 'trend': 'flat',
                           'etat': achille_etat, 'note': f'{achille_alerts} signal(aux)'},
        },
    }


def call_model(context: dict) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    # max_tokens couvre AUSSI les blocs de raisonnement du modèle. À 8000, le
    # nouveau format (forme + 4 indicateurs + analysis + propositions) sortait
    # tronqué et le json.loads plantait sans que rien ne soit écrit. À 20000
    # on a de la marge pour le raisonnement ET la réponse structurée.
    msg = client.messages.create(
        model=MODEL,
        max_tokens=20000,
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
    # Détection explicite d'un JSON tronqué (utile quand max_tokens saute).
    if msg.stop_reason == 'max_tokens':
        raise RuntimeError(
            f'réponse coupée par max_tokens ({len(text)} caractères produits). '
            'Le JSON est incomplet — augmenter max_tokens ou alléger le prompt.')
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


def _write_min_analysis(reason: str, context: dict | None = None):
    """Écrit un coach_analysis.json minimal avec un `forme` fallback.

    S'exécute quand main() sort avant l'appel modèle (secret absent, plan
    manquant). Sans cette écriture, l'UI resterait sur une ancienne
    analyse indéfiniment — la panne était invisible dans un build vert.
    """
    forme = build_forme_fallback(context or {}, error=reason) if context is not None \
        else {'score': 50, 'verdict': 'surveiller',
              'headline': f'Analyse indisponible : {reason}',
              'detail': 'Impossible de produire un état de forme sans plan.',
              'indicateurs': {}}
    doc = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'model': MODEL, 'signature': '',
        'headline': f'Analyse indisponible : {reason}',
        'analysis': f'Le coach n\'a pas pu s\'exécuter ({reason}). '
                    'Les indicateurs affichés sont locaux, sans intervention modèle.',
        'forme': forme, 'applied': [], 'pending': [],
    }
    ANALYSIS_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                             encoding='utf-8')
    try:
        from modules.ci_status import note
        note('coach', ok=False, message=reason)
    except Exception:  # noqa: BLE001
        pass


def main():
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('⚠ ANTHROPIC_API_KEY absent — coach IA sauté')
        _write_min_analysis('ANTHROPIC_API_KEY absent')
        return

    if not PLAN_PATH.exists():
        print('⚠ Pas de plan — coach IA sauté')
        _write_min_analysis('plan_nyc.json absent')
        return
    plan = json.loads(PLAN_PATH.read_text(encoding='utf-8'))

    context = build_context(plan)

    # Économie d'appels : le coach tournait à CHAQUE build, y compris les
    # rebuilds déclenchés par un simple changement de code. Tant qu'aucune
    # séance nouvelle n'est arrivée et que l'analyse a moins de 12 h, il n'y a
    # rien de neuf à dire.
    #
    # Version 2 du schéma (introduction du champ `forme`) : le skip est levé
    # tant que l'ancienne analyse en cache n'a pas ce champ, sinon le nouveau
    # format ne serait jamais produit.
    signature = json.dumps(context['last_14_days'][-3:], ensure_ascii=False)
    if ANALYSIS_PATH.exists() and '--force' not in sys.argv:
        try:
            prev = json.loads(ANALYSIS_PATH.read_text(encoding='utf-8'))
            age_h = (datetime.now()
                     - datetime.fromisoformat(prev['generated_at'])).total_seconds() / 3600
            schema_ok = prev.get('forme') is not None
            if prev.get('signature') == signature and age_h < 12 and schema_ok:
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
        # Fallback : produit un `forme` minimal à partir des données locales
        # pour que l'onglet Coach affiche quelque chose plutôt qu'un vide,
        # et que ci_status refléte la panne visible dans l'analyse.
        forme_fallback = build_forme_fallback(context, error=str(e))
        analysis_min = {
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'model': MODEL, 'signature': signature,
            'headline': f'Analyse indisponible ({type(e).__name__})',
            'analysis': (f"Le coach n'a pas pu produire son analyse : {e}. "
                         'Les indicateurs affichés sont calculés localement '
                         'sans intervention du modèle. Retentera au prochain build.'),
            'forme': forme_fallback,
            'applied': [], 'pending': [],
        }
        ANALYSIS_PATH.write_text(
            json.dumps(analysis_min, ensure_ascii=False, indent=1), encoding='utf-8')
        print('✓ Fallback `forme` écrit (analyse minimale)')
        sys.exit(0)

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
        # État de forme composé par le coach : centre de gravité de l'onglet
        # Coach dans l'app. Peut être absent si le modèle échoue à le produire.
        'forme': result.get('forme'),
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
# retrigger
