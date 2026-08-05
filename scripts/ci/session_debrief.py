#!/usr/bin/env python3
"""
seb-metrics — scripts/ci/session_debrief.py
===========================================
Débrief IA de la dernière séance, affiché sur l'accueil du dashboard.

Différence avec ai_coach.py : celui-ci raisonne sur le PLAN (semaines,
conformité, propositions d'ajustement). Celui-là lit UNE séance en détail —
splits, dynamique de course, dérive cardiaque, ressenti montre — et explique
ce que les chiffres racontent.

Principe de conception : le modèle ne reçoit jamais une métrique nue. Chaque
valeur est accompagnée de la référence personnelle de Sébastien sur les séances
comparables récentes. Sans ce point de comparaison, un modèle produit des
généralités ("235 ms, c'est correct pour un coureur entraîné") au lieu d'une
lecture ("235 ms, soit 6 ms de plus que ta moyenne sur les footings du mois").

Sortie : data/session_debrief.json
Env : ANTHROPIC_API_KEY (requis), ANTHROPIC_MODEL, SEB_DATA_DIR
"""
from __future__ import annotations
import json
import os
import statistics as st
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = Path(os.environ.get('SEB_DATA_DIR') or (REPO_ROOT / 'data'))
CACHE_PATH = DATA_DIR / 'sessions_cache.json'
PLAN_PATH = DATA_DIR / 'plan_nyc.json'
OUT_PATH = DATA_DIR / 'session_debrief.json'
MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-5')

# Fenêtre de comparaison personnelle
BASELINE_DAYS = 60
BASELINE_MIN = 3


def _d(sess: dict):
    try:
        return datetime.strptime(sess['d'], '%d/%m/%Y').date()
    except Exception:
        return None


def _mean(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(st.mean(vals), 2) if vals else None


def build_baseline(sessions: list[dict], target: dict) -> dict:
    """
    Référence personnelle : moyennes des séances des 60 derniers jours courues
    À ALLURE COMPARABLE, en excluant la séance analysée.

    L'appariement se fait sur l'allure et non sur le type de séance, pour deux
    raisons : la classification automatique se trompe (un footing avec lignes
    droites est étiqueté « fractionné »), et surtout la mécanique de course
    dépend d'abord de la vitesse — comparer un footing à 5'20 avec une séance
    à 4'00 ne dit rien d'utile sur le temps de contact ou la foulée.
    """
    tday, tps = _d(target), target.get('ps')
    if not tday or not tps:
        return {'n': 0}

    def pool_within(tol: int) -> list[dict]:
        out = []
        for s in sessions:
            sd = _d(s)
            if not sd or s is target or not s.get('ps'):
                continue
            if not (0 < (tday - sd).days <= BASELINE_DAYS):
                continue
            if abs(s['ps'] - tps) <= tol:
                out.append(s)
        return out

    tol = 25
    pool = pool_within(tol)
    if len(pool) < BASELINE_MIN:
        tol = 45
        pool = pool_within(tol)

    if len(pool) < BASELINE_MIN:
        return {'n': len(pool), 'tolerance_allure_s': tol}

    dyns = [s['dyn'] for s in pool if s.get('dyn')]
    return {
        'n': len(pool),
        'critere': f'séances des {BASELINE_DAYS} derniers jours à ±{tol}"/km '
                   f'de l\'allure du jour',
        'fenetre_jours': BASELINE_DAYS,
        'allure_moy_s_km': _mean([s.get('ps') for s in pool]),
        'fc_moy': _mean([s.get('fc') for s in pool]),
        'contact_ms': _mean([d.get('stance_ms') for d in dyns]),
        'foulee_m': _mean([d.get('step_m') for d in dyns]),
        'ratio_vertical': _mean([d.get('vratio') for d in dyns]),
        'equilibre_gauche_pct': _mean([d.get('balance_l') for d in dyns]),
        'cadence': _mean([s.get('dyn', {}).get('cadence') or
                          _mean([b.get('ca') for b in (s.get('b') or [])])
                          for s in pool]),
    }


def build_payload(cache: dict, plan: dict) -> dict | None:
    sessions = [v for v in cache.values() if isinstance(v, dict) and v.get('d')]
    dated = [(d, s) for s in sessions if (d := _d(s))]
    if not dated:
        return None
    dated.sort(key=lambda t: (t[0], s_h if (s_h := t[1].get('h')) else ''))
    day, last = dated[-1]

    # Jour de plan correspondant
    plan_day = None
    for w in plan.get('weeks', []):
        for pd in w.get('days', []):
            if pd.get('date') == day.isoformat():
                plan_day = pd
                break

    splits = [{'km': b.get('km'), 'allure_s': b.get('ps'), 'fc': b.get('fc'),
               'cadence': b.get('ca'), 'contact_ms': b.get('ct'),
               'equilibre_g': b.get('bal'), 'foulee_m': b.get('fl'),
               'temp_c': b.get('tc')}
              for b in (last.get('b') or []) if (b.get('km') or 0) > 0.3][:40]

    return {
        'seance': {
            'date': last.get('d'), 'heure': last.get('h'),
            'titre': last.get('t'), 'type_detecte': last.get('tp'),
            'km': last.get('km'), 'duree': last.get('dur'),
            'allure': last.get('a'), 'fc_moy': last.get('fc'),
        },
        'prevu_au_plan': {
            'titre': plan_day.get('title'), 'km': plan_day.get('km'),
            'allure_cible': plan_day.get('target_pace'),
            'consignes': plan_day.get('description'),
            'seance_cle': plan_day.get('key'),
            'score': plan_day.get('score'),
        } if plan_day else None,
        'dynamique_garmin': last.get('dyn'),
        'splits_km': splits,
        'reference_personnelle': build_baseline(sessions, last),
    }


SYSTEM_PROMPT = """Tu débriefes UNE séance de course de Sébastien, 42 ans, en préparation du marathon de New York (1er novembre 2026, objectif sub-3h, record actuel 2h50 sur marathon).

CONTEXTE MÉDICAL PERMANENT — deux antécédents, deux lectures différentes :
1. Tendinopathie d'insertion de l'Achille DROIT, à la base du tendon côté talon, en cours. "equilibre_gauche_pct" donne le % de temps d'appui sur le pied gauche : au-dessus de 50 %, il décharge son côté droit, donc le côté douloureux.
2. Pubalgie / adducteur à l'hiver 2025, résolue. Sa signature était particulière : l'équilibre restait correct à allure facile et se dégradait quand l'allure montait. Les champs "balance_lent", "balance_rapide" et "asym_vs_allure" mesurent exactement ça au sein d'une même séance — "asym_vs_allure" positif signifie que l'asymétrie s'ouvre avec la vitesse. Un déséquilibre constant et un déséquilibre qui apparaît à la vitesse ne racontent pas la même histoire : le second est le motif de son antécédent adducteur.
Tu signales, tu ne diagnostiques jamais, et tu ne joues pas au médecin.

Tu reçois les données brutes de la séance, ce qui était prévu au plan, et surtout "reference_personnelle" : les moyennes de Sébastien sur ses séances comparables des 60 derniers jours. C'est ta seule échelle de lecture valable.

RÈGLES D'ANALYSE :
- Compare toujours à SA référence, jamais à une norme générale. « 235 ms » ne veut rien dire ; « 235 ms, 6 de plus que ta moyenne du mois » veut dire quelque chose.
- Si "reference_personnelle" contient moins de 3 séances, dis que tu manques de recul plutôt que d'inventer une comparaison.
- Une longueur de foulée qui varie suit d'abord l'allure : ne parle jamais de foulée sans regarder l'allure de la séance et celle de la référence.
- Une FC qui dérive à allure constante peut venir de la chaleur (regarde temp_c), de la déshydratation ou de la fatigue. Ne tranche pas sans indice.
- Le RPE et la sensation viennent de Sébastien lui-même, saisis sur sa montre. En cas de contradiction avec les chiffres, sa perception prime et c'est l'écart qui devient intéressant à commenter.
- N'invente aucune donnée absente. Si un champ manque, c'est probablement qu'il courait sans sa ceinture : dis-le.

FORMAT : ce texte est lu sur un téléphone, en dix secondes, juste après la séance. Sois court et factuel. Chaque ligne porte un chiffre et sa comparaison. Aucune formule d'introduction, aucun compliment, aucune reformulation de ce qui est déjà affiché ailleurs (distance, allure, durée sont déjà à l'écran).

Réponds UNIQUEMENT avec un JSON valide, sans markdown :
{
  "headline": "une phrase courte, 90 caractères maximum, ce qu'il faut retenir",
  "bullets": ["2 à 3 constats, 110 caractères maximum chacun, un chiffre et sa comparaison par constat"],
  "points": [
    {"label": "libellé court", "valeur": "valeur + unité", "ecart": "écart à sa référence, ex '+6 ms vs réf. 60j'", "lecture": "8 mots maximum", "ton": "bon|neutre|vigilance"}
  ],
  "achille": "une ligne, 100 caractères maximum, ou null si la donnée manque",
  "a_surveiller": "une ligne, 100 caractères maximum, ou null s'il n'y a rien de notable"
}
Maximum 3 entrées dans "points", les plus parlantes. Si une séance est banale, dis-le en une ligne plutôt que de meubler."""


def call_model(payload: dict) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    msg = client.messages.create(
        model=MODEL, max_tokens=1600, system=SYSTEM_PROMPT,
        messages=[{'role': 'user',
                   'content': json.dumps(payload, ensure_ascii=False)}],
    )
    txt = msg.content[0].text.strip()
    if txt.startswith('```'):
        txt = txt.split('```')[1].lstrip('json').strip()
    return json.loads(txt)


def main() -> int:
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('▸ ANTHROPIC_API_KEY absente — débrief ignoré.')
        return 0
    if not CACHE_PATH.exists() or not PLAN_PATH.exists():
        print('▸ Données absentes — débrief ignoré.')
        return 0

    cache = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    plan = json.loads(PLAN_PATH.read_text(encoding='utf-8'))
    payload = build_payload(cache, plan)
    if not payload:
        print('▸ Aucune séance à débriefer.')
        return 0

    seance = payload['seance']
    # Pas de nouvel appel si la séance est déjà débriefée
    if OUT_PATH.exists():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding='utf-8'))
            if prev.get('seance', {}).get('date') == seance['date'] \
                    and prev.get('seance', {}).get('heure') == seance['heure']:
                print(f"✓ Débrief déjà à jour ({seance['date']}).")
                return 0
        except Exception:  # noqa: BLE001
            pass

    ref = payload['reference_personnelle']
    print(f"▸ Débrief {seance['date']} · {seance['km']} km · "
          f"référence : {ref.get('n', 0)} séance(s) comparables")
    try:
        result = call_model(payload)
    except Exception as e:  # noqa: BLE001
        try:
            from modules.ci_status import note
            note('debrief', ok=False, message=f'{type(e).__name__}: {e}')
        except Exception:  # noqa: BLE001
            pass
        print(f'✗ Débrief impossible : {e}')
        return 0  # jamais bloquant

    result['seance'] = seance
    result['generated_at'] = datetime.now().isoformat(timespec='seconds')
    result['baseline_n'] = ref.get('n', 0)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                        encoding='utf-8')
    print(f"✓ {result.get('headline', '')[:90]}")
    try:
        from modules.ci_status import note
        note('debrief', ok=True)
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
