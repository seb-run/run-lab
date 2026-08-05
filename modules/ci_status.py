"""
seb-metrics — modules/ci_status.py
==================================
Journal d'état des étapes du pipeline, écrit dans data/ci_status.json.

Pourquoi : les étapes de récupération et d'analyse sont volontairement non
bloquantes — une panne d'API ne doit jamais empêcher la publication du
dashboard. Effet de bord : une panne peut durer des jours sans que personne
la voie, puisque le build reste vert.

Ce module rend la panne visible dans les DONNÉES plutôt que dans les logs :
le fichier est commité par l'étape « Persist data », donc consultable depuis
le dépôt, affichable dans le dashboard et lisible par le briefing du matin.

Usage :
    from modules.ci_status import note
    note('coach', ok=False, message=str(exc))
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _path() -> Path:
    data_dir = Path(os.environ.get('SEB_DATA_DIR') or (_REPO_ROOT / 'data'))
    return data_dir / 'ci_status.json'


def note(step: str, ok: bool, message: str = '') -> None:
    """Enregistre le résultat d'une étape. Ne lève jamais."""
    try:
        path = _path()
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except Exception:  # noqa: BLE001
                data = {}
        entry = {
            'ok': bool(ok),
            'at': datetime.now().isoformat(timespec='seconds'),
        }
        if message:
            # Tronqué : on veut un diagnostic, pas une trace complète — et le
            # fichier est public puisque le dépôt l'est.
            entry['message'] = str(message)[:400]
        if ok:
            entry['last_ok'] = entry['at']
        elif isinstance(data.get(step), dict) and data[step].get('last_ok'):
            entry['last_ok'] = data[step]['last_ok']
        data[step] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding='utf-8')
    except Exception:  # noqa: BLE001
        pass   # un journal d'état ne doit jamais casser ce qu'il observe
