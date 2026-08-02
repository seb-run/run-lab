#!/usr/bin/env python3
"""
rebuild_plan_nyc.py — Réécriture des semaines 9 à 21 du plan NYC 2026.

Contexte (2 août 2026) :
  - Le plan initial était calibré sur VMA 18.37 / objectif 2h44, ce qui produisait
    des semaines à 100-110 km jamais tenues (0 séance clé validée sur 4 semaines).
  - Recalibrage sur les performances réelles : marathon 2h50'03 (12/04/2026),
    2h54'35 (12/10/2025), semi 1h22'40 (09/03/2025).
  - Objectif NYC retenu : sub-3h maîtrisé (4'12/km), NYC servant de marche vers
    un 2h44 au marathon de Milan du 4 avril 2027.
  - Contraintes : tendinopathie d'Achille débutante (douleur au démarrage),
    chaleur de Mondonville en août, terrain d'entraînement = forêt de Bouconne.

Les semaines 1-8 (passées) ne sont pas touchées. Les champs remplis par le CI
(actual / status / score) sont préservés jour par jour quand ils existent.

Usage : python3 scripts/rebuild_plan_nyc.py [--dry-run]
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
PLAN_PATH = Path(__file__).resolve().parent.parent / "data" / "plan_nyc.json"

# ---------------------------------------------------------------------------
# Allures recalibrées (sec/km)
# ---------------------------------------------------------------------------
PACES = {
    "vma": 205,          # 3'25 — VMA courte / 5K
    "10k": 220,          # 3'40
    "seuil": 230,        # 3'50
    "semi": 237,         # 3'57
    "marathon": 245,     # 4'05 — allure marathon "potentiel"
    "mp_target": 252,    # 4'12 — allure objectif NYC (2h57)
    "mp_strategy": 258,  # 4'18 — plan B / départ prudent
    "le_long": 295,      # 4'55 — sortie longue
    "footing": 320,      # 5'20 — endurance fondamentale
    "recup": 340,        # 5'40 — récupération
}


def fmt_pace(sec: int) -> str:
    return f"{sec // 60}'{sec % 60:02d}\"/km"


PACE_STR = {k: fmt_pace(v) for k, v in PACES.items()}

# ---------------------------------------------------------------------------
# Définition des semaines 9 à 21
#
# Chaque jour : (type, titre, km, key, target_pace_key|None, description)
#   type : rest | recovery | easy | tempo | seuil | vma | mp | long | long_mp
#          | progressive | shake | race
#   Ces types sont ceux reconnus par modules/session_scoring.py
#     QUALITY_TYPES = interval, vma, seuil, threshold, tempo, mp, marathon_pace, race
#     STEADY_TYPES  = easy, recovery, long, long_mp, shake, progressive
# ---------------------------------------------------------------------------

import _shoes_nyc as shoes_nyc  # noqa: E402
from _weeks_nyc import WEEKS, R, DISCIPLINE  # noqa: E402  (défini à côté)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Allure moyenne approximative de la séance complète, pour estimer la durée
DURATION_PACE = {
    "rest": 0, "recovery": 340, "easy": 318, "tempo": 290, "seuil": 285,
    "vma": 285, "mp": 285, "long": 295, "long_mp": 285, "progressive": 285,
    "shake": 340, "race": 252,
}


def build_day(d: date, spec: tuple) -> dict:
    dtype, title, km, key, pace_key, desc = spec
    dur = round(km * DURATION_PACE.get(dtype, 300) / 60) if km else 0
    day = {
        "date": d.isoformat(),
        "dow": DOW[d.weekday()],
        "type": dtype,
        "title": title,
        "km": km,
        "duration_min": dur,
        "key": key,
        "description": desc,
    }
    if pace_key:
        day["target_pace"] = PACE_STR[pace_key]
    return day


def main(dry_run: bool = False) -> int:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    # --- meta recalibrée
    meta = plan["meta"]
    meta["target_time"] = "2h57'00"
    meta["strategy_time"] = "3h00'00"
    meta["paces_sec"] = dict(PACES)
    meta["paces_str"] = dict(PACE_STR)
    meta["recalibrated_at"] = datetime.now().isoformat(timespec="seconds")
    meta["recalibration_note"] = (
        "Allures recalibrées le 2026-08-02 sur les performances réelles "
        "(marathon 2h50'03 le 12/04/2026, 2h54'35 le 12/10/2025, semi 1h22'40) "
        "et non plus sur une VMA estimée. Objectif NYC : sub-3h maîtrisé, "
        "étape vers un 2h44 au marathon de Milan du 04/04/2027."
    )
    meta["plan_peak_km"] = 98.0

    # --- index des jours existants pour préserver le réalisé
    existing = {}
    for w in plan["weeks"]:
        for day in w.get("days", []):
            existing[day["date"]] = day

    today = date.today()
    rebuilt = 0

    for w in plan["weeks"]:
        wn = w["week_num"]
        if wn not in WEEKS:
            continue
        spec = WEEKS[wn]
        start = date.fromisoformat(w["start_date"])

        new_days = []
        for i, day_spec in enumerate(spec["days"]):
            d = start + timedelta(days=i)
            nd = build_day(d, day_spec)
            # Préserve ce que le CI a écrit sur les jours déjà passés
            old = existing.get(nd["date"], {})
            for field in ("actual", "status", "score"):
                if old.get(field) is not None:
                    nd[field] = old[field]
            if d < today and "status" not in nd:
                nd["status"] = "missed" if nd["km"] > 0 else "rest"
            new_days.append(nd)

        w["days"] = new_days
        w["phase"] = spec["phase"]
        w["phase_label"] = spec["phase_label"]
        w["focus"] = spec["focus"]
        w["target_km"] = round(sum(d["km"] for d in new_days), 1)
        # Purge les traces d'adaptations compoundées des builds précédents
        for stale in ("volume_actual_to_date", "volume_planned_to_date",
                      "volume_drift_pct"):
            w.pop(stale, None)
        rebuilt += 1

    plan["adaptations"] = []

    # --- rotation chaussures
    projection = shoes_nyc.annotate(plan)
    plan["meta"]["shoe_projection"] = projection

    print(f"Semaines réécrites : {rebuilt}")
    print()
    print("S#  début       phase                     km     séances clés")
    print("-" * 78)
    for w in plan["weeks"]:
        if w["week_num"] not in WEEKS:
            continue
        keys = [d["title"] for d in w["days"] if d.get("key")]
        print(f"{w['week_num']:2d}  {w['start_date']}  {w['phase_label'][:24]:24s} "
              f"{w['target_km']:5.1f}  {len(keys)}")

    total = sum(w["target_km"] for w in plan["weeks"] if w["week_num"] in WEEKS)
    print("-" * 78)
    print(f"Total semaines 9-21 : {total:.0f} km")

    if dry_run:
        print("\n[dry-run] fichier non écrit")
        return 0

    PLAN_PATH.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nÉcrit : {PLAN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
