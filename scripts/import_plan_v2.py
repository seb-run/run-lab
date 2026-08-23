#!/usr/bin/env python3
"""
seb-metrics — scripts/import_plan_v2.py
========================================
Importe un plan au format « v2 » (celui du fichier plan_nyc_v2_1.json) et le
transforme au format que l'app comprend (data/plan_nyc.json).

Deux exigences guident la conversion :

  1. Ne pas perdre l'historique. Les semaines déjà courues du plan actuel
     conservent leurs séances réalisées, leurs scores et leurs adaptations.
     Le nouveau plan ne remplace que la période qu'il couvre.

  2. Repartir sur un vocabulaire homogène. Le v2 range les séances par codes
     d'allure (AR, AF, AM, SE…) et types génériques (footing, seance, piste,
     sl). L'app attend des types précis (easy, mp, seuil, vma, long, race)
     et des cibles d'allure au format « m'ss"/km ». La conversion utilise
     l'allure de la séance pour choisir le type, et le point milieu de la
     plage d'allure pour la cible.

Utilisation :
    python3 scripts/import_plan_v2.py <chemin/plan_v2.json> [--write]
    python3 scripts/import_plan_v2.py --write     # cherche dans uploads/

Sans --write : simulation, affichage du diff, aucun fichier modifié.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# TABLES DE CONVERSION
# ---------------------------------------------------------------------------

# Code d'allure → type de séance que l'app connaît. Pour les codes qualité,
# on privilégie la précision : SE=seuil, AM=mp, VO/VM=vma, AS=tempo/semi.
# Les codes lents (AR/AF/AE) sont ramenés au type d'origine du bloc.
_TYPE_FROM_PACE = {
    'AR': 'recovery',
    'AF': 'easy',
    'AE': 'endurance',
    'AM': 'mp',
    'AS': 'tempo',
    'SE': 'seuil',
    'VO': 'intervals',
    'VM': 'intervals',
}

# Type v2 → type app quand aucune allure ne suffit à décider
_TYPE_FROM_V2 = {
    'repos':   'rest',
    'footing': 'easy',
    'sl':      'long',
    'piste':   'intervals',
    'seance':  'tempo',    # séance qualité générique, précisé par l'allure
    'voyage':  'shake',
    'course':  'race',
}

# Séances qualifiantes → clé pour le compteur « clés » et les scores allure
_KEY_TYPES = {'seuil', 'vma', 'intervals', 'mp', 'tempo', 'long', 'race'}


def parse_pace_range(s):
    """« 4'07–4'12/km » → moyenne en secondes.

    On prend le milieu de la plage : le score compare à cette valeur avec
    une tolérance qui absorbe la fourchette d'origine.
    """
    if not s:
        return None
    m = re.findall(r"(\d+)['′](\d{1,2})", s)
    if not m:
        return None
    secs = [int(a) * 60 + int(b) for a, b in m]
    return sum(secs) // len(secs)


def format_pace(sec):
    if not sec:
        return None
    return f"{sec // 60}'{sec % 60:02d}\"/km"


def choose_type(v2_seance):
    """Type le plus précis possible pour l'app."""
    t = v2_seance.get('type') or ''
    allure = v2_seance.get('allure') or ''
    # Une séance dite « qualité » (seance/piste) tire son type de l'allure.
    if t in ('seance', 'piste'):
        if allure in _TYPE_FROM_PACE:
            return _TYPE_FROM_PACE[allure]
    # Un footing avec plage AM/SE/VO est en fait une séance qualité.
    if t == 'footing' and allure in ('AM', 'SE', 'VO', 'VM', 'AS'):
        return _TYPE_FROM_PACE[allure]
    return _TYPE_FROM_V2.get(t, 'easy')


def build_description(v2_seance, allures_ref):
    """Description lisible : reprend le détail v2, plus la plage d'allure."""
    parts = []
    detail = (v2_seance.get('detail') or '').strip()
    if detail:
        parts.append(detail)
    plage = v2_seance.get('allure_plage')
    code = v2_seance.get('allure')
    if plage and code:
        aname = (allures_ref.get(code) or {}).get('nom', code)
        parts.append(f"[{aname} · {plage}]")
    chaus = v2_seance.get('chaussures')
    if chaus:
        parts.append(f"Chaussures : {chaus}")
    return "\n".join(parts)


def convert_day(v2_seance, week_num, phase_label, allures_ref):
    """Un jour au format app à partir d'un « seance » v2."""
    iso = v2_seance['date']
    dt = date.fromisoformat(iso)
    typ = choose_type(v2_seance)
    is_key = typ in _KEY_TYPES

    target_sec = parse_pace_range(v2_seance.get('allure_plage'))
    day = {
        'date': iso,
        # Format attendu par render_plan_doc.py : anglais court capitalisé
        'dow': ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dt.weekday()],
        'type': typ,
        'title': v2_seance.get('titre') or '',
        'km': float(v2_seance.get('km') or 0),
        'duration_min': int(v2_seance.get('duree_min') or 0),
        'key': is_key,
        'description': build_description(v2_seance, allures_ref),
        'status': 'pending',
    }
    if target_sec:
        day['target_pace'] = format_pace(target_sec)
        day['target_pace_sec'] = target_sec
    if v2_seance.get('chaussures'):
        day['shoe'] = v2_seance['chaussures']
    if v2_seance.get('heure'):
        day['scheduled_time'] = v2_seance['heure']
    return day


def convert_week(v2_week, first_week_num_offset, allures_ref):
    """Une semaine complète au format app."""
    num = int(v2_week['numero']) + first_week_num_offset
    phase_label = v2_week.get('titre') or v2_week.get('bloc') or ''
    # Rangement de phase pour l'app : peak / build / taper / race
    focus = (v2_week.get('titre') or '').upper()
    if 'AFF' in focus or 'AFFÛT' in focus:
        phase = 'taper'
    elif 'PIC' in focus or 'RÉPÉTITION' in focus:
        phase = 'peak'
    elif 'REPRISE' in focus or 'ASSIMILATION' in focus:
        phase = 'base'
    else:
        phase = 'build'
    days = [convert_day(s, num, phase_label, allures_ref)
            for s in v2_week.get('seances', [])]
    return {
        'week_num': num,
        'weeks_left': None,   # rempli plus bas quand on connaît la date de course
        'phase': phase,
        'phase_label': phase_label,
        'start_date': v2_week['du'],
        'end_date': v2_week['au'],
        'target_km': float(v2_week.get('km_cible') or 0),
        'days': days,
    }


def meta_from_v2(v2, weeks):
    """Bloc `meta` compatible app à partir du v2."""
    goal_date = None
    for w in weeks:
        for d in w['days']:
            if d.get('type') == 'race':
                goal_date = d['date']
                break
        if goal_date: break
    goal_date = goal_date or v2.get('meta', {}).get('objectif', '2026-11-01')

    a = v2.get('allures', {})
    def milieu(code):
        return format_pace(parse_pace_range((a.get(code) or {}).get('plage')))

    return {
        'goal_name': 'NYC Marathon',
        'goal_date': goal_date,
        'target_time': '2h57\'00',
        'strategy_time': '2h57\'00',
        'weeks_total': len(weeks),  # sera ajusté après fusion avec l'historique
        'plan_peak_km': max((w['target_km'] for w in weeks), default=0),
        'user_peak_km': None,
        'vma_used': v2.get('meta', {}).get('vdot'),
        # Toutes les clés attendues par render_plan_doc.py (« recup »,
        # « footing », « le_long »…) doivent être fournies, sinon la génération
        # du plan.html plante et l'étape « Assemble site » du CI échoue —
        # empêchant tout déploiement Pages jusqu'au correctif.
        'paces_str': {
            'vma':          milieu('VM') or milieu('VO'),
            '10k':          milieu('AS'),
            'seuil':        milieu('SE'),
            'semi':         milieu('AS'),
            'marathon':     milieu('AM'),
            'mp_target':    milieu('AM'),
            'mp_strategy':  "4'18\"/km",
            'le_easy':      milieu('AF'),
            'recovery':     milieu('AR'),
            # Alias attendus par render_plan_doc.py
            'recup':        milieu('AR'),
            'footing':      milieu('AF'),
            'le_long':      milieu('AE') or milieu('AF'),
        },
        'paces_sec': {
            'mp_strategy': 258,
        },
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': 'plan_v2_import',
    }


def fusion_avec_historique(nouveau_weeks, ancien_plan):
    """Combine les semaines historiques de l'ancien plan et les nouvelles.

    Les semaines de l'ancien qui se terminent AVANT le début du nouveau sont
    conservées telles quelles (séances réalisées, scores, chaussures).
    Le reste est écrasé par le nouveau — même si certaines séances y avaient
    déjà été réalisées, c'est le prix d'un vrai reset.
    """
    if not ancien_plan or 'weeks' not in ancien_plan:
        return nouveau_weeks
    nouveau_debut = date.fromisoformat(nouveau_weeks[0]['start_date'])
    histo = [w for w in ancien_plan['weeks']
             if date.fromisoformat(w['end_date']) < nouveau_debut]
    # Renuméroter proprement l'ensemble
    total = histo + nouveau_weeks
    for i, w in enumerate(total, start=1):
        w['week_num'] = i
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', nargs='?',
                    help="Fichier plan v2 à importer (défaut : uploads/plan_nyc_v2_1.json)")
    ap.add_argument('--write', action='store_true',
                    help="Écrit vraiment data/plan_nyc.json (sinon simulation)")
    args = ap.parse_args()

    # 1. Source
    if args.source:
        source = Path(args.source)
    else:
        candidates = [
            ROOT / 'uploads' / 'plan_nyc_v2_1.json',
            Path.home() / 'Library/Application Support/Claude/local-agent-mode-sessions',
        ]
        source = next((c for c in candidates if c.exists() and c.is_file()), None)
        if not source:
            print("✗ Source introuvable. Précise le chemin en argument.")
            return 1
    print(f"▸ Source : {source}")
    v2 = json.loads(source.read_text(encoding='utf-8'))

    # 2. Cible
    from modules.paths import data_dir
    cible = data_dir() / 'plan_nyc.json'
    if not cible.exists():
        cible = ROOT / 'data' / 'plan_nyc.json'
    print(f"▸ Cible  : {cible}")
    ancien = json.loads(cible.read_text(encoding='utf-8')) if cible.exists() else None

    # 3. Conversion
    allures_ref = v2.get('allures', {})
    nouveau_weeks = [convert_week(w, first_week_num_offset=0, allures_ref=allures_ref)
                     for w in v2['semaines']]
    weeks = fusion_avec_historique(nouveau_weeks, ancien)
    meta = meta_from_v2(v2, weeks)
    meta['weeks_total'] = len(weeks)

    # 4. Chaussures : projection à partir des séances qui portent une paire
    for w in weeks:
        for d in w['days']:
            if not d.get('shoe') and d.get('type') != 'rest':
                # On laisse le module scripts/_shoes_nyc.py compléter au build
                pass

    # 5. Compte-rendu
    hist_n = sum(1 for w in weeks if date.fromisoformat(w['end_date']) < date.fromisoformat(nouveau_weeks[0]['start_date']))
    print()
    print(f"  Semaines historiques conservées : {hist_n}")
    print(f"  Semaines du nouveau plan        : {len(nouveau_weeks)}")
    print(f"  Total après fusion              : {len(weeks)}")
    print()
    print("  Aperçu des 5 prochaines semaines :")
    today = date.today()
    upcoming = [w for w in weeks if date.fromisoformat(w['end_date']) >= today][:5]
    for w in upcoming:
        keys = sum(1 for d in w['days'] if d.get('key'))
        print(f"    W{w['week_num']:2}  {w['start_date']} → {w['end_date']}  "
              f"{w['target_km']:.0f} km · {keys} séance(s) clé · {w['phase_label']}")

    plan = {'meta': meta, 'weeks': weeks, 'adaptations': ancien.get('adaptations', []) if ancien else []}

    # 6. Écriture
    if not args.write:
        print()
        print("  Simulation. Relance avec --write pour appliquer.")
        return 0

    if cible.exists():
        backup = cible.with_name(f"{cible.stem}.avant_v2_{datetime.now():%Y%m%d_%H%M%S}.json")
        shutil.copy2(cible, backup)
        print(f"\n  Sauvegarde : {backup.name}")
    cible.write_text(json.dumps(plan, ensure_ascii=False, indent=1, default=str),
                     encoding='utf-8')
    print(f"  ✓ Écrit : {cible}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
