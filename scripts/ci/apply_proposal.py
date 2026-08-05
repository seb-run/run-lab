#!/usr/bin/env python3
"""
seb-metrics — scripts/ci/apply_proposal.py
==========================================
Applique ou refuse une proposition MAJEURE du coach IA, validée par Seb depuis
le dashboard (bouton → Cloudflare Worker → repository_dispatch "coach-validate").

Les propositions mineures ne passent pas par ici : ai_coach.py les applique
seul, avec ses garde-fous (±10 % de volume, note sur un jour futur).

Usage :
    python3 scripts/ci/apply_proposal.py --id 7e4375e9 --action accept
    python3 scripts/ci/apply_proposal.py --id 7e4375e9 --action reject

Entrées/sorties : data/coach_proposals.json, data/plan_nyc.json,
                  data/coach_analysis.json (liste "pending" resynchronisée)

Ce script est appelé avec des valeurs venues d'Internet (payload du webhook) :
tout argument est validé strictement avant usage, et une entrée invalide fait
sortir en erreur sans rien écrire.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get('SEB_DATA_DIR') or (REPO_ROOT / 'data'))
PLAN_PATH = DATA_DIR / 'plan_nyc.json'
ANALYSIS_PATH = DATA_DIR / 'coach_analysis.json'
PROPOSALS_PATH = DATA_DIR / 'coach_proposals.json'

ID_RE = re.compile(r'^[0-9a-f]{6,32}$')
VALID_ACTIONS = ('accept', 'reject')

# Types dont la valeur est structurée et peut être appliquée telle quelle.
# Tout le reste (move_session, change_type, restructure_week, other) est une
# consigne en langage naturel : on l'inscrit dans la description du jour plutôt
# que de tenter une réécriture automatique du plan, qui serait devinée.
STRUCTURED_KINDS = {'volume_adjust'}


def load(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'✗ Lecture {path.name} : {e}')
        sys.exit(1)


def save(path: Path, doc, indent=1):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=indent, default=str),
                    encoding='utf-8')


def find_day(plan: dict, iso: str):
    for w in plan.get('weeks', []):
        for d in w.get('days', []):
            if d.get('date') == iso:
                return d
    return None


def apply_to_plan(plan: dict, prop: dict) -> tuple[bool, str]:
    """Applique une proposition majeure validée. Retourne (plan_modifié, détail)."""
    iso = prop.get('date')
    day = find_day(plan, iso) if iso else None
    if not day:
        return False, f'jour {iso} introuvable dans le plan'
    if day.get('type') == 'race':
        return False, 'jour de course intouchable'

    kind = prop.get('kind')
    reason = (prop.get('reason') or '').strip()

    if kind in STRUCTURED_KINDS and prop.get('field') == 'km':
        try:
            new_km = round(float(prop.get('new_value')), 1)
        except (TypeError, ValueError):
            return False, 'valeur km invalide'
        if not 0 <= new_km <= 60:
            return False, f'valeur km hors bornes ({new_km})'
        cur = float(day.get('km') or 0)
        day['km'] = new_km
        day['description'] = (day.get('description') or '') + \
            f"\n[COACH IA — validé : volume {cur:g}→{new_km:g} km. {reason}]"
        return True, f'{iso} : {cur:g}→{new_km:g} km'

    # Consigne en langage naturel : inscrite dans la séance, visible dans le
    # dashboard et le briefing. Le plan garde sa structure ; c'est Seb (ou une
    # régénération du plan) qui tranche l'exécution concrète.
    txt = prop.get('new_value')
    txt = txt.strip() if isinstance(txt, str) else json.dumps(txt, ensure_ascii=False)
    day['description'] = (day.get('description') or '') + \
        f"\n[COACH IA — validé : {txt[:400]}]"
    return True, f'{iso} : consigne inscrite ({kind})'


def sync_analysis(proposals: list, applied_prop: dict | None = None, detail: str = ''):
    """Resynchronise coach_analysis.json : sans ça le dashboard continuerait
    d'afficher une proposition déjà tranchée jusqu'au prochain passage du coach.
    Appelé sur TOUS les chemins qui modifient un statut."""
    analysis = load(ANALYSIS_PATH)
    if not isinstance(analysis, dict):
        return
    analysis['pending'] = [p for p in proposals if p.get('status') == 'pending']
    if applied_prop is not None:
        analysis.setdefault('applied', []).append({
            **{k: applied_prop.get(k) for k in
               ('severity', 'kind', 'date', 'field', 'new_value', 'reason', 'id')},
            'detail': detail,
            'validated': True,
        })
    save(ANALYSIS_PATH, analysis)


def _note(ok: bool, message: str = '') -> None:
    """Journalise le résultat sans jamais faire échouer l'appelant."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from modules.ci_status import note
        note('coach_validate', ok=ok, message=message)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', required=True)
    ap.add_argument('--action', required=True)
    args = ap.parse_args()

    prop_id = (args.id or '').strip().lower()
    action = (args.action or '').strip().lower()
    if not ID_RE.match(prop_id):
        print(f'✗ Identifiant invalide : {args.id!r}')
        _note(False, f'identifiant invalide : {args.id!r}')
        return
    if action not in VALID_ACTIONS:
        print(f'✗ Action invalide : {args.action!r} (attendu accept ou reject)')
        _note(False, f'action invalide : {args.action!r}')
        return

    doc = load(PROPOSALS_PATH, {'proposals': []})
    proposals = doc.get('proposals', [])
    prop = next((p for p in proposals if p.get('id') == prop_id), None)
    if prop is None:
        # Cas courant : le coach a régénéré ses propositions depuis que la
        # page consultée a été publiée, l'identifiant affiché n'existe plus.
        print(f'✗ Proposition {prop_id} introuvable')
        _note(False, f'proposition {prop_id} introuvable — '
                     'la page consultée date probablement d\'un build antérieur')
        return
    if prop.get('status') != 'pending':
        # Idempotence : un double clic ne doit pas appliquer deux fois.
        print(f"✓ Proposition {prop_id} déjà traitée (statut « {prop.get('status')} ») — rien à faire")
        return

    stamp = datetime.now().isoformat(timespec='seconds')
    detail = ''

    if action == 'reject':
        prop['status'] = 'rejected'
        prop['decided_at'] = stamp
        print(f'✓ Proposition {prop_id} refusée')
    else:
        # Garde-fou : on n'applique pas rétroactivement.
        if prop.get('date') and prop['date'] < date.today().isoformat():
            prop['status'] = 'expired'
            prop['decided_at'] = stamp
            save(PROPOSALS_PATH, doc)
            sync_analysis(proposals)
            print(f"✗ Proposition {prop_id} datée du {prop['date']} : jour passé, marquée expirée")
            return

        plan = load(PLAN_PATH)
        if plan is None:
            print('✗ Plan introuvable')
            _note(False, 'plan introuvable')
            return

        ok, detail = apply_to_plan(plan, prop)
        if not ok:
            print(f'✗ Application impossible : {detail}')
            _note(False, f'application impossible : {detail}')
            return

        plan.setdefault('adaptations', []).append({
            'source': 'coach_ia_validee',
            'proposal_id': prop_id,
            'kind': prop.get('kind'),
            'date': prop.get('date'),
            'detail': detail,
            'reason': prop.get('reason'),
            'applied_at': stamp,
        })
        save(PLAN_PATH, plan, indent=2)

        prop['status'] = 'accepted'
        prop['decided_at'] = stamp
        prop['applied_detail'] = detail
        print(f'✓ Proposition {prop_id} appliquée : {detail}')

    save(PROPOSALS_PATH, doc)
    sync_analysis(proposals, prop if action == 'accept' else None, detail)
    _note(True, f'{action} {prop_id}')


if __name__ == '__main__':
    main()
