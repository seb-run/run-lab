#!/usr/bin/env python3
"""
build_ics.py — Génère plan_nyc.ics à partir de data/plan_nyc.json.

Le fichier est publié à la racine du site GitHub Pages. Sebastien s'y abonne une
seule fois depuis son iPhone (Réglages → Calendrier → Comptes → Ajouter un compte
→ Autre → Ajouter un abonnement), et iOS le resynchronise tout seul à chaque
publication du CI : toute évolution du plan remonte automatiquement.

Choix techniques :
  - Heures "flottantes" (DATE-TIME sans timezone) : interprétées dans le fuseau
    de l'appareil. 7h du matin reste 7h du matin, y compris après l'arrivée à
    New York — pas de VTIMEZONE, pas de bascule d'heure d'été à gérer.
  - UID stables et dérivés de la date : une nouvelle publication met à jour
    l'événement existant au lieu d'en créer un doublon.
  - SEQUENCE incrémenté via un hash du contenu : iOS ne rafraîchit un événement
    que si quelque chose a réellement changé.

Usage : python3 scripts/build_ics.py [chemin_sortie.ics]
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = ROOT / "data" / "plan_nyc.json"
DEFAULT_OUT = ROOT / "plan_nyc.ics"

CAL_NAME = "Plan NYC 2026 · Seb-Metrics"
DOMAIN = "run-lab.seb-run.github.io"

EMOJI = {
    "rest": "😴", "recovery": "🫧", "easy": "🏃", "tempo": "🌡️",
    "seuil": "🔥", "vma": "⚡", "mp": "🎯", "long": "🛣️",
    "long_mp": "🎯", "progressive": "📈", "shake": "🫧", "race": "🏁",
}
LABEL = {
    "rest": "Repos", "recovery": "Récup", "easy": "Endurance", "tempo": "Tempo",
    "seuil": "Seuil", "vma": "VMA / 10K", "mp": "Allure marathon",
    "long": "Sortie longue", "long_mp": "SL + allure marathon",
    "progressive": "Progressif", "shake": "Déblocage", "race": "Course",
}

# Heure de début par défaut selon le type de séance
DEFAULT_HOUR = {"race": (8, 30)}
TRACK_HOUR = (19, 0)     # piste du mercredi soir avec Harbat
MORNING = (7, 0)         # tout le reste : avant la chaleur


def esc(s: str) -> str:
    """Échappement iCalendar (RFC 5545 §3.3.11)."""
    return (s.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\n", "\\n"))


def fold(line: str) -> str:
    """Pliage à 75 octets, continuation par une espace (RFC 5545 §3.1)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > 73:
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def start_time(day: dict) -> tuple[int, int]:
    if day["type"] in DEFAULT_HOUR:
        return DEFAULT_HOUR[day["type"]]
    if "🏟️" in (day.get("title") or ""):
        return TRACK_HOUR
    return MORNING


def build_description(day: dict, week: dict, meta: dict) -> str:
    parts = []
    if day.get("target_pace"):
        parts.append(f"Allure cible : {day['target_pace']}")
    if day.get("shoe"):
        note = day.get("shoe_note") or ""
        parts.append(f"Chaussures : {day['shoe']}" + (f" — {note}" if note else ""))
    parts.append("")
    parts.append(day.get("description") or "")
    parts.append("")
    goal = date.fromisoformat(meta["goal_date"])
    dleft = (goal - date.fromisoformat(day["date"])).days
    parts.append(f"Semaine {week['week_num']}/{meta['weeks_total']} · "
                 f"{week['phase_label']} · {week['target_km']:.0f} km")
    parts.append(f"J−{dleft} avant New York")
    if week.get("focus"):
        parts.append("")
        parts.append(f"Objectif de la semaine : {week['focus']}")
    return "\n".join(parts).strip()


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    meta = plan["meta"]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    L = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Seb-Metrics//Plan NYC 2026//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(CAL_NAME)}",
        "X-WR-CALDESC:" + esc(
            f"Plan marathon de New York — objectif {meta.get('target_time','')}. "
            "Mis à jour automatiquement."),
        "X-WR-TIMEZONE:Europe/Paris",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]

    n = 0
    for w in plan["weeks"]:
        if w["week_num"] < 9:      # semaines passées : pas dans le calendrier
            continue
        for d in w["days"]:
            iso = d["date"]
            dt = date.fromisoformat(iso)
            typ = d["type"]
            km = d.get("km") or 0
            uid = f"sebmetrics-{iso}@{DOMAIN}"
            desc = build_description(d, w, meta)

            if typ == "rest" or km == 0:
                summary = f"{EMOJI['rest']} Repos · protocole Achille"
                ev = [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART;VALUE=DATE:{dt.strftime('%Y%m%d')}",
                    f"DTEND;VALUE=DATE:{(dt + timedelta(days=1)).strftime('%Y%m%d')}",
                    f"SUMMARY:{esc(summary)}",
                    f"DESCRIPTION:{esc(desc)}",
                    "CATEGORIES:Repos",
                    "TRANSP:TRANSPARENT",
                ]
            else:
                h, mn = start_time(d)
                dur = int(d.get("duration_min") or max(30, km * 5))
                st = datetime(dt.year, dt.month, dt.day, h, mn)
                en = st + timedelta(minutes=dur)
                star = " ★" if d.get("key") else ""
                # Certains titres portent déjà leur emoji (🏟️ piste, 🏁 course,
                # 🎯 séance signature) : on ne le double pas.
                title = d["title"]
                prefix = "" if title[:1] in "🏟🏁🎯" else EMOJI.get(typ, "🏃") + " "
                summary = f"{prefix}{title} · {km:g} km{star}"
                ev = [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART:{st.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND:{en.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{esc(summary)}",
                    f"DESCRIPTION:{esc(desc)}",
                    f"CATEGORIES:{esc(LABEL.get(typ, typ))}",
                    "TRANSP:OPAQUE",
                ]
                if typ == "race" and dt == date(2026, 11, 1):
                    ev.append("LOCATION:" + esc(
                        "Départ Staten Island, New York City"))
                # Rappel la veille au soir pour les séances clés,
                # 45 min avant pour les autres
                if d.get("key"):
                    ev += ["BEGIN:VALARM", "ACTION:DISPLAY",
                           f"DESCRIPTION:{esc('Demain : ' + d['title'])}",
                           "TRIGGER:-PT13H", "END:VALARM"]
                ev += ["BEGIN:VALARM", "ACTION:DISPLAY",
                       f"DESCRIPTION:{esc(d['title'])}",
                       "TRIGGER:-PT45M", "END:VALARM"]

            sig = hashlib.md5(
                (summary + desc).encode("utf-8")).hexdigest()[:6]
            ev.insert(3, f"SEQUENCE:{int(sig, 16) % 1000}")
            ev.append("END:VEVENT")
            L += ev
            n += 1

    L.append("END:VCALENDAR")
    out.write_text("\r\n".join(fold(x) for x in L) + "\r\n", encoding="utf-8")
    print(f"Écrit : {out}  ({n} événements, {out.stat().st_size // 1024} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
