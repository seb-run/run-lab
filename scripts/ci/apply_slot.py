#!/usr/bin/env python3
"""
seb-metrics — scripts/ci/apply_slot.py
=======================================
Applique la séance de piste du mercredi, saisie par Seb depuis le dashboard
(formulaire → Cloudflare Worker /slot → repository_dispatch "apply-slot").

Le club donne la séance le lundi soir pour le mercredi ; aucune IA ne la
connaît d'avance. Ce script remplace la séance du plan à cette date par ce
que Seb a saisi (échauffement / effort en répétitions / récup / retour au
calme), exactement comme apply_proposal.py remplace une séance validée par
le coach — même schéma de jour, même logique de chaussure recalculée.

Usage (CI uniquement) :
    SLOT_PAYLOAD='{"date":"2026-09-23","title":"...", ...}' \
    python3 scripts/ci/apply_slot.py

Entrée : variable d'environnement SLOT_PAYLOAD (JSON, posée par le workflow
via toJSON(github.event.client_payload)).
Sortie : data/plan_nyc.json.

Ce script est appelé avec des valeurs venues d'Internet (payload du webhook,
déjà filtré une première fois côté Worker) : tout champ est revalidé
strictement ici avant usage, sans faire confiance au filtrage amont. Une
entrée invalide fait sortir en erreur sans rien écrire.
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get('SEB_DATA_DIR') or (REPO_ROOT / 'data'))
PLAN_PATH = DATA_DIR / 'plan_nyc.json'

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def load(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'✗ Lecture {path.name} : {e}')
        sys.exit(1)


def save(path: Path, doc, indent=2):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=indent, default=str),
                    encoding='utf-8')


def find_day(plan: dict, iso: str):
    for w in plan.get('weeks', []):
        for d in w.get('days', []):
            if d.get('date') == iso:
                return d
    return None


def _note(ok: bool, message: str = '') -> None:
    """Journalise le résultat sans jamais faire échouer l'appelant."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from modules.ci_status import note
        note('apply_slot', ok=ok, message=message)
    except Exception:
        pass


def _num(v, lo: float, hi: float):
    """Nombre borné, ou None si invalide/hors bornes — jamais d'exception."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or n < lo or n > hi:  # NaN ou hors bornes
        return None
    return n


def _str(v, max_len: int) -> str:
    if not isinstance(v, str):
        return ''
    return v.strip()[:max_len]


def fmt_dist(km: float) -> str:
    """Cohérent avec le style du plan existant : « 5×1000m », pas « 5×1km »."""
    if km <= 2:
        return f'{round(km * 1000)}m'
    return f'{km:g}km'


def fmt_km(km: float) -> str:
    return f'{km:g}'


def build_description(warmup_km: float, reps: int, rep_km: float, rep_pace: str,
                       recovery: str, cooldown_km: float, notes: str) -> str:
    lines: list[str] = []
    if warmup_km > 0:
        lines.append(f'{fmt_km(warmup_km)}km échauffement')
    if reps > 0 and rep_km > 0:
        seg = f'{reps}×{fmt_dist(rep_km)}'
        if rep_pace:
            seg += f' à {rep_pace}'
        if recovery:
            seg += f' · récup {recovery}'
        lines.append(seg)
    if cooldown_km > 0:
        lines.append(f'{fmt_km(cooldown_km)}km retour au calme')
    if notes:
        lines.append(notes)
    return '\n'.join(lines)


def validate_payload(raw: dict) -> dict | None:
    """Revalidation stricte, indépendante de ce que le Worker a déjà filtré.
    Retourne un payload propre, ou None si quoi que ce soit cloche."""
    if not isinstance(raw, dict):
        return None

    iso = str(raw.get('date') or '')
    if not DATE_RE.match(iso):
        print(f'✗ Date invalide : {iso!r}')
        return None
    try:
        date.fromisoformat(iso)
    except ValueError:
        print(f'✗ Date invalide : {iso!r}')
        return None

    title = _str(raw.get('title'), 80) or 'Piste club'

    # warmup_km / cooldown_km : absents ou hors bornes → 0 plutôt qu'un rejet
    # total (un échauffement à 0 est une séance valide, juste optimiste).
    # reps / rep_km : c'est le cœur de la séance, ceux-là sont obligatoires.
    warmup_km = _num(raw.get('warmup_km'), 0, 10) or 0
    cooldown_km = _num(raw.get('cooldown_km'), 0, 10) or 0
    reps_f = _num(raw.get('reps'), 1, 20)
    rep_km = _num(raw.get('rep_km'), 0.05, 5)
    if reps_f is None or rep_km is None:
        print('✗ Répétitions ou distance par répétition manquantes/hors bornes (reps, rep_km)')
        return None
    reps = round(reps_f)

    rep_pace = _str(raw.get('rep_pace'), 20)
    recovery = _str(raw.get('recovery'), 40)
    notes = _str(raw.get('notes'), 300)

    total_km = round(warmup_km + reps * rep_km + cooldown_km, 1)
    if not 0 < total_km <= 60:
        print(f'✗ Distance totale hors bornes ({total_km} km)')
        return None

    return {
        'date': iso, 'title': title,
        'warmup_km': warmup_km, 'cooldown_km': cooldown_km,
        'reps': reps, 'rep_km': rep_km,
        'rep_pace': rep_pace, 'recovery': recovery, 'notes': notes,
        'total_km': total_km,
    }


def apply_to_plan(plan: dict, p: dict) -> tuple[bool, str]:
    day = find_day(plan, p['date'])
    if not day:
        return False, f"jour {p['date']} introuvable dans le plan"
    if day.get('type') == 'race':
        return False, 'jour de course intouchable'

    orig_title = day.get('title')
    orig_pace = day.get('target_pace')

    day['title'] = p['title']
    day['type'] = 'intervals'
    day['km'] = p['total_km']
    day['key'] = True
    if p['rep_pace']:
        day['target_pace'] = p['rep_pace']
    else:
        day.pop('target_pace', None)
    day['description'] = build_description(
        p['warmup_km'], p['reps'], p['rep_km'], p['rep_pace'],
        p['recovery'], p['cooldown_km'], p['notes'])
    day.pop('duration_min', None)  # pas d'estimation fiable, mieux vaut absent que faux

    day['_replaced_by_user'] = True
    day['_replaced_from'] = {'title': orig_title, 'target_pace': orig_pace}

    # Chaussure recalculée sur le nouveau type, comme pour un remplacement coach.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from _shoes_nyc import assign as _assign_shoe
        _assign_shoe(day)
    except Exception:
        pass

    stamp = datetime.now().isoformat(timespec='seconds')
    day.setdefault('coach_notes', []).append({
        'kind': 'user_slot',
        'text': f"Séance club saisie par toi le {stamp[:10]}.",
        'validated': True,
    })

    detail = f"{p['date']} : {orig_title or '?'} → {day['title']} ({p['total_km']}km)"
    plan.setdefault('adaptations', []).append({
        'source': 'saisie_mercredi',
        'date': p['date'],
        'detail': detail,
        'applied_at': stamp,
    })
    return True, detail


def main():
    raw_env = os.environ.get('SLOT_PAYLOAD', '')
    if not raw_env.strip():
        print('✗ SLOT_PAYLOAD absent ou vide')
        _note(False, 'SLOT_PAYLOAD absent ou vide')
        return

    try:
        raw = json.loads(raw_env)
    except json.JSONDecodeError as e:
        print(f'✗ SLOT_PAYLOAD JSON invalide : {e}')
        _note(False, f'SLOT_PAYLOAD JSON invalide : {e}')
        return

    p = validate_payload(raw)
    if p is None:
        _note(False, 'payload invalide — voir logs')
        return

    # Garde-fou : pas d'application rétroactive sur un jour déjà passé.
    if p['date'] < date.today().isoformat():
        print(f"✗ {p['date']} est déjà passé — séance non appliquée")
        _note(False, f"date passée ({p['date']}) — non appliquée")
        return

    plan = load(PLAN_PATH)
    if plan is None:
        print('✗ Plan introuvable')
        _note(False, 'plan introuvable')
        return

    ok, detail = apply_to_plan(plan, p)
    if not ok:
        print(f'✗ Application impossible : {detail}')
        _note(False, f'application impossible : {detail}')
        return

    save(PLAN_PATH, plan, indent=2)
    print(f'✓ Séance du mercredi appliquée : {detail}')
    _note(True, detail)


if __name__ == '__main__':
    main()
