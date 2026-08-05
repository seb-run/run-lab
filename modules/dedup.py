"""
seb-metrics — modules/dedup.py
========================================
Fusion des séances vues deux fois : une par la voie .fit (intervals.icu),
une par la voie Strava.

Le problème
-----------
Les deux voies alimentent le même cache mais ne partagent aucun identifiant.
La déduplication Strava se fait sur `_strava_id`, absent des entrées .fit :
une séance ingérée d'abord en .fit réapparaît donc quand Strava la synchronise
à son tour. Le cache contenait ainsi MaxiRace Annecy du 31/05/2026 en double.

L'appariement
-------------
Aucune clé commune, donc on rapproche sur ce que les deux voies mesurent :
même date, distance à 300 m près, durée à 2 minutes près. L'heure n'entre pas
dans le critère — les entrées .fit ingérées par le CI avant le correctif de
fuseau portent une heure décalée de deux heures, et ce sont précisément
celles qu'on veut rattraper.

En cas d'ambiguïté — deux candidats possibles pour une même entrée, ce qui
arriverait sur un doublé de deux sorties très semblables le même jour — on ne
fusionne pas et on le signale. Perdre une séance coûte plus cher que garder
un doublon visible.

La fusion
---------
On part de l'entrée .fit, qui porte la dynamique de course que Strava jette
(contact au sol, oscillation, équilibre G/D, intervalles R-R), et on lui
emprunte de Strava ce que le .fit n'a pas : le titre saisi sur la montre,
l'heure de départ locale fiable, et l'identifiant qui évitera le prochain
doublon.
"""
from __future__ import annotations

from typing import Any, Iterable

# Tolérances d'appariement.
# La distance est mesurée par le même GPS des deux côtés : elle colle à
# quelques dizaines de mètres. La durée, elle, ne mesure pas la même chose —
# le .fit rapporte le temps écoulé, Strava le temps en mouvement. Sur MaxiRace
# (4h30 avec ravitaillements) l'écart atteignait 6m37. D'où une tolérance
# proportionnelle, avec un plancher pour les sorties courtes.
_KM_TOL = 0.30           # km
_DUR_TOL_MIN = 180       # secondes
_DUR_TOL_RATIO = 0.08    # 8 % de la durée


def is_strava(sess: dict) -> bool:
    """Vrai si la séance vient de l'API Strava plutôt que d'un fichier .fit."""
    return (bool(sess.get('_strava_id'))
            or str(sess.get('source', '')).startswith('strava_'))


def strava_id(sess: dict) -> str | None:
    sid = sess.get('_strava_id')
    if sid:
        return str(sid)
    src = str(sess.get('source', ''))
    return src[len('strava_'):] if src.startswith('strava_') else None


def _same_session(a: dict, b: dict) -> bool:
    """Deux entrées décrivent-elles la même sortie ?"""
    if not a.get('d') or a.get('d') != b.get('d'):
        return False
    ka, kb = a.get('km'), b.get('km')
    if not ka or not kb or abs(ka - kb) > _KM_TOL:
        return False
    da, db = a.get('dur_s'), b.get('dur_s')
    if da and db:
        tol = max(_DUR_TOL_MIN, _DUR_TOL_RATIO * max(da, db))
        if abs(da - db) > tol:
            return False
    return True


def merge(fit: dict, strava: dict) -> dict:
    """Fusionne une entrée .fit et son équivalent Strava.

    Le .fit sert de base : lui seul porte la dynamique de course. Strava
    fournit le titre, l'heure de départ et l'identifiant.
    """
    out = dict(fit)

    title = (strava.get('t') or '').strip()
    if title:
        out['t'] = title

    if strava.get('h'):
        out['h'] = strava['h']

    sid = strava_id(strava)
    if sid:
        out['_strava_id'] = sid

    # La description saisie dans Strava est le canal « sensations » : elle
    # ne doit pas se perdre dans la fusion.
    for key in ('desc', 'description', 'rpe', 'feel'):
        if not out.get(key) and strava.get(key):
            out[key] = strava[key]

    # Trace GPS : on garde la plus fournie des deux.
    if not out.get('track') and strava.get('track'):
        out['track'] = strava['track']

    out['_merged_from'] = [str(fit.get('source', '')), str(strava.get('source', ''))]
    return out


def find_pairs(cache: dict[str, dict]) -> tuple[list[tuple[str, str]], list[str]]:
    """Repère les paires (clé .fit, clé Strava) à fusionner.

    Retourne aussi la liste des dates ambiguës, laissées intactes.
    """
    fits = [(k, v) for k, v in cache.items() if not is_strava(v)]
    stravas = [(k, v) for k, v in cache.items() if is_strava(v)]

    by_day: dict[str, list[tuple[str, dict]]] = {}
    for k, v in stravas:
        by_day.setdefault(v.get('d') or '', []).append((k, v))

    pairs: list[tuple[str, str]] = []
    ambiguous: list[str] = []
    taken: set[str] = set()

    for fk, fv in fits:
        cands = [(sk, sv) for sk, sv in by_day.get(fv.get('d') or '', [])
                 if sk not in taken and _same_session(fv, sv)]
        if not cands:
            continue
        if len(cands) > 1:
            ambiguous.append(f"{fv.get('d')} · {fv.get('km')} km "
                             f"({len(cands)} candidats Strava)")
            continue
        sk = cands[0][0]
        taken.add(sk)
        pairs.append((fk, sk))

    return pairs, ambiguous


def dedupe(cache: dict[str, dict]) -> tuple[dict[str, dict], dict[str, Any]]:
    """Retourne un cache fusionné et un rapport, sans modifier l'entrée.

    La clé conservée est celle de l'entrée .fit (le MD5 du fichier), pour que
    le cache de parsing continue de reconnaître les fichiers déjà traités.
    """
    pairs, ambiguous = find_pairs(cache)
    out = dict(cache)
    details: list[str] = []

    for fit_key, strava_key in pairs:
        merged = merge(cache[fit_key], cache[strava_key])
        out[fit_key] = merged
        out.pop(strava_key, None)
        details.append(f"{merged.get('d')} {merged.get('h')} · "
                       f"{merged.get('km')} km · {merged.get('t', '')[:40]}")

    report = {
        'avant': len(cache),
        'apres': len(out),
        'fusionnees': len(pairs),
        'ambigues': ambiguous,
        'details': details,
    }
    return out, report


def format_report(report: dict[str, Any]) -> str:
    lines = [f"  {report['avant']} séances → {report['apres']} "
             f"({report['fusionnees']} fusionnée(s))"]
    for d in report['details']:
        lines.append(f"    ✓ {d}")
    for a in report['ambigues']:
        lines.append(f"    ? ambigu, laissé tel quel : {a}")
    return "\n".join(lines)
