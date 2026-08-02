"""
_shoes_nyc.py — Rotation chaussures du plan NYC 2026.

Attribue une paire à chaque sortie du plan et projette le kilométrage de chaque
paire jusqu'au 1er novembre.

Deux contraintes structurent la rotation :

  1. **Disponibilité.** Du 3 au 16 août, Sebastien est à Mondonville avec
     seulement 3 paires (Boston 13, Evo SL usagée, Pegasus 40). Les paires
     neuves et le reste du placard ne sont disponibles qu'à partir du 17 août.

  2. **Drop et tendon d'Achille.** La tendinopathie réactive impose de garder du
     drop élevé sur le gros du volume facile. Après retrait de la Pegasus 40
     (1137 km), les seules paires à 10 mm sont la Pegasus 41 et la On
     Cloudsurfer — elles portent donc prioritairement les footings et récups.
     Les séances rapides vont sur les paires les plus dynamiques (6 mm), où le
     temps passé est court.

Kilométrages relevés sur Strava le 2 août 2026.
"""
from __future__ import annotations

from datetime import date

# Date à partir de laquelle tout le placard est disponible
HOME = date(2026, 8, 17)

# clé : (nom affiché, km au 02/08, drop mm, durée de vie estimée km, dispo dès)
SHOES: dict[str, tuple[str, int, int, int, date]] = {
    "boston13":  ("Adizero Boston 13",        157,  6,  700, date(2026, 8, 3)),
    "evosl_old": ("Evo SL (usagée)",          749,  6,  600, date(2026, 8, 3)),
    "peg40":     ("Pegasus 40 (fin de vie)", 1137, 10,  900, date(2026, 8, 3)),
    "hyper":     ("Hyperboost Edge (neuve)",    0,  6,  700, HOME),
    "evosl_new": ("Evo SL (neuve)",             0,  6,  600, HOME),
    "peg41":     ("Pegasus 41",               477, 10,  850, HOME),
    "on_cs":     ("On Cloudsurfer",           163, 10,  700, HOME),
    "af3_proto": ("Alphafly 3 Prototype",     238,  8,  320, HOME),
    "af3_chi":   ("Alphafly 3 « Chicago »",   126,  8,  320, HOME),
    "vf3":       ("Vaporfly Next% 3 (neuve)",   0,  8,  320, HOME),
}

RACE_CHOICE = "Alphafly 3 « Chicago » ou Vaporfly Next% 3"


def _mondonville(dtype: str) -> tuple[str, str]:
    """3 paires seulement, du 3 au 16 août."""
    if dtype in ("seuil", "tempo", "mp", "vma", "long", "long_mp",
                 "progressive", "race"):
        return "boston13", "La seule paire fraîche : elle prend tout ce qui compte."
    if dtype == "recovery":
        return "peg40", ("Uniquement les récups courtes et lentes : c'est ton seul "
                         "10 mm, mais la semelle est morte.")
    return "evosl_old", "Footings faciles jusqu'à épuisement de la paire."


def _home(dtype: str, easy_idx: int, d: date) -> tuple[str, str]:
    """Placard complet, à partir du 17 août."""
    if dtype == "recovery":
        return "peg41", "10 mm de drop sur les lendemains de séance : le tendon respire."
    if dtype in ("seuil", "vma"):
        return "boston13", "Dynamique et ferme, pour le travail rapide."
    if dtype == "mp":
        return "boston13", "Allure marathon : la paire la plus proche de tes sensations de course."
    if dtype == "long_mp":
        if d >= date(2026, 10, 5):
            return "af3_chi", ("Sortie longue avec bloc à allure course en octobre : "
                               "on rode la chaussure de course.")
        return "boston13", "Bloc à allure marathon en fin de sortie longue."
    if dtype in ("long", "progressive"):
        return "evosl_new", "Légère et amortie, confortable sur la durée."
    if dtype == "race":
        return "af3_proto", ("Test 10 km : l'occasion d'écouler les derniers "
                             "kilomètres utiles d'une paire de course en fin de vie.")
    if dtype == "shake":
        return "on_cs", "Déblocage très lent, drop élevé."
    # easy : on alterne pour maximiser l'exposition au drop élevé
    return [("on_cs",  "10 mm : le drop élevé porte le gros du volume facile."),
            ("hyper",  "Stack maximal : amorti maximal sur les kilomètres faciles."),
            ("peg41",  "10 mm, la valeur sûre du volume."),
            ][easy_idx % 3]


def assign(day: dict) -> None:
    """Ajoute les clés `shoe` et `shoe_note` à un jour du plan (in place)."""
    dtype = day.get("type") or ""
    if dtype == "rest" or not (day.get("km") or 0):
        return
    d = date.fromisoformat(day["date"])

    # Le marathon et la sortie longue signature : décision matérielle à part
    if dtype == "race" and d == date(2026, 11, 1):
        day["shoe"] = RACE_CHOICE
        day["shoe_note"] = "Choix tranché sur la sortie longue du 11 octobre."
        return

    key, note = (_mondonville(dtype) if d < HOME
                 else _home(dtype, day.get("_easy_idx", 0), d))
    day["shoe"] = SHOES[key][0]
    day["shoe_note"] = note
    day["_shoe_key"] = key


def annotate(plan: dict) -> list[dict]:
    """
    Attribue une paire à chaque sortie des semaines 9-21 et retourne la
    projection de kilométrage par paire au 1er novembre.
    """
    easy_idx = 0
    for w in plan.get("weeks", []):
        if w.get("week_num", 0) < 9:
            continue
        for day in w.get("days", []):
            if (day.get("type") or "") == "easy":
                day["_easy_idx"] = easy_idx
                easy_idx += 1
            assign(day)

    # --- projection
    add: dict[str, float] = {k: 0.0 for k in SHOES}
    for w in plan.get("weeks", []):
        if w.get("week_num", 0) < 9:
            continue
        for day in w.get("days", []):
            k = day.get("_shoe_key")
            if k:
                add[k] += day.get("km") or 0

    proj = []
    for k, (name, km0, drop, life, avail) in SHOES.items():
        end = km0 + add[k]
        proj.append({
            "key": k, "name": name, "start_km": km0, "added_km": round(add[k]),
            "end_km": round(end), "drop": drop, "life": life,
            "pct": round(end / life * 100),
            "available": avail.isoformat(),
        })
    proj.sort(key=lambda p: -p["pct"])
    return proj
