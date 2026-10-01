#!/usr/bin/env python3
"""
seb-metrics — scripts/ci/apply_move.py
=======================================
Décale une séance dans le plan, à la demande de Seb depuis le dashboard
(glisser / bouton « Décaler » → Cloudflare Worker /move → repository_dispatch
"move-session").

Sémantique : ÉCHANGE. La séance du jour A va au jour B, et ce qui était prévu en B
(séance ou repos) passe en A. C'est le geste naturel d'un athlète — « je
fais ma séance de qualité jeudi plutôt que mercredi » — et il garde le volume
hebdomadaire intact. Chaque emplacement conserve sa date, son jour de la semaine,
son statut et son réalisé ; seul le contenu prévu voyage.

Garde-fous (le payload vient d'Internet, tout est revalidé) :
  - dates ISO strictes, toutes deux dans le plan
  - ni passé ni séance déjà réalisée (on ne réécrit pas l'histoire)
  - jour de course intouchable
  - même semaine ou semaines voisines : écart ≤ 6 jours

Usage (CI uniquement) :
    MOVE_PAYLOAD='{"from":"2026-10-07","to":"2026-10-08"}' python3 scripts/ci/apply_move.py

Entrée : variable d'environnement MOVE_PAYLOAD (JSON).
Sortie : data/plan_nyc.json, data/ci_status.json (clé `move`).
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
DATA_DIR = Path(os.environ.get('SEB_DATA_DIR') or (REPO_ROOT / 'data'))
PLAN_PATH = DATA_DIR / 'plan_nyc.json'
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
# Champs « positionnels » : ils appartiennent à l'emplacement, pas à la séance.
SLOT_KEYS = ('date', 'dow', 'status', 'actual', 'score')
MAX_GAP_DAYS = 6


def _note(ok: bool, message: str = ''):
    try:
        from modules.ci_status import note
        note('move', ok=ok, message=message)
    except Exception:  # noqa: BLE001
        pass


def _fail(msg: str):
    print(f'✗ {msg}')
    _note(False, msg)
    sys.exit(1)


def find_day(plan: dict, iso: str):
    for w in plan.get('weeks', []):
        for d in w.get('days', []):
            if d.get('date') == iso:
                return d
    return None


def swap(plan: dict, a_iso: str, b_iso: str) -> str:
    today = date.today()
    for iso in (a_iso, b_iso):
        if not DATE_RE.match(iso or ''):
            _fail(f'date invalide : {iso!r}')
    a_d, b_d = date.fromisoformat(a_iso), date.fromisoformat(b_iso)
    if a_d == b_d:
        _fail('même jour')
    if a_d < today or b_d < today:
        _fail('on ne décale pas une séance passée')
    if abs((a_d - b_d).days) > MAX_GAP_DAYS:
        _fail(f'écart > {MAX_GAP_DAYS} jours')
    a, b = find_day(plan, a_iso), find_day(plan, b_iso)
    if not a or not b:
        _fail('jour introuvable dans le plan')
    for d in (a, b):
        if d.get('type') == 'race':
            _fail('jour de course intouchable')
        if d.get('status') in ('done', 'validated') or d.get('actual'):
            _fail(f"{d.get('date')} est déjà réalisé")

    keep_a = {k: a.get(k) for k in SLOT_KEYS if k in a}
    keep_b = {k: b.get(k) for k in SLOT_KEYS if k in b}
    content_a = {k: v for k, v in a.items() if k not in SLOT_KEYS}
    content_b = {k: v for k, v in b.items() if k not in SLOT_KEYS}
    a.clear(); a.update(content_b); a.update(keep_a)
    b.clear(); b.update(content_a); b.update(keep_b)
    # Traces : l'app affiche « décalée depuis … » et le coach sait que ce
    # n'est pas un raté.
    a['moved_from'] = b_iso
    b['moved_from'] = a_iso
    stamp = datetime.now().isoformat(timespec='seconds')
    plan.setdefault('moves', []).append({'at': stamp, 'from': a_iso, 'to': b_iso})
    plan['moves'] = plan['moves'][-30:]
    return f"{a_iso} ⇄ {b_iso} : « {b.get('title')} » ↔ « {a.get('title')} »"


def main():
    raw = os.environ.get('MOVE_PAYLOAD', '')
    try:
        payload = json.loads(raw)
    except Exception:
        _fail('MOVE_PAYLOAD illisible')
    if not isinstance(payload, dict):
        _fail('payload non objet')
    a_iso, b_iso = str(payload.get('from', '')), str(payload.get('to', ''))

    if not PLAN_PATH.exists():
        _fail('plan_nyc.json absent')
    plan = json.loads(PLAN_PATH.read_text(encoding='utf-8'))
    detail = swap(plan, a_iso, b_iso)
    PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str),
                         encoding='utf-8')
    print(f'✓ Séance décalée — {detail}')
    _note(True, detail)


if __name__ == '__main__':
    main()
