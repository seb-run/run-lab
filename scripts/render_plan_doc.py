#!/usr/bin/env python3
"""
render_plan_doc.py — Génère le document de référence HTML du plan NYC 2026
à partir de data/plan_nyc.json (source de vérité unique).

Usage : python3 scripts/render_plan_doc.py [chemin_sortie.html]
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = ROOT / "data" / "plan_nyc.json"
DEFAULT_OUT = ROOT / "PLAN_NYC_2026.html"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
JOURS = {"Mon": "Lun", "Tue": "Mar", "Wed": "Mer", "Thu": "Jeu",
         "Fri": "Ven", "Sat": "Sam", "Sun": "Dim"}

TYPE_CLASS = {
    "rest": "t-rest", "recovery": "t-rec", "easy": "t-easy",
    "tempo": "t-q", "seuil": "t-q", "vma": "t-q", "mp": "t-mp",
    "long": "t-long", "long_mp": "t-long", "progressive": "t-long",
    "shake": "t-rec", "race": "t-race",
}
TYPE_LABEL = {
    "rest": "Repos", "recovery": "Récup", "easy": "Endurance",
    "tempo": "Tempo", "seuil": "Seuil", "vma": "VMA / 10K", "mp": "Allure marathon",
    "long": "Sortie longue", "long_mp": "SL + allure marathon",
    "progressive": "Progressif", "shake": "Déblocage", "race": "Course",
}


def fdate(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MOIS[d.month - 1]}"


def md_inline(s: str) -> str:
    """Échappe le HTML puis rend **gras** et les retours à la ligne."""
    s = html.escape(s)
    out, bold = [], False
    i = 0
    while i < len(s):
        if s[i:i + 2] == "**":
            out.append("</strong>" if bold else "<strong>")
            bold = not bold
            i += 2
        else:
            out.append(s[i])
            i += 1
    if bold:
        out.append("</strong>")
    return "".join(out).replace("\n", "<br>")


CSS = """
*{box-sizing:border-box}
body{margin:0;padding:2rem 1.25rem 4rem;background:#0f1115;color:#e6e8ec;
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
 max-width:1000px;margin-inline:auto}
h1{font-size:1.9rem;margin:0 0 .3rem;letter-spacing:-.02em}
h2{font-size:1.25rem;margin:2.6rem 0 .9rem;padding-bottom:.4rem;
 border-bottom:1px solid #262a33;letter-spacing:-.01em}
h3{font-size:1rem;margin:1.6rem 0 .5rem;color:#c9ced8}
.sub{color:#8b93a3;margin:0 0 2rem;font-size:.95rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.6rem;margin:1rem 0}
.card{background:#171a21;border:1px solid #262a33;border-radius:10px;padding:.75rem .9rem}
.card .k{color:#8b93a3;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}
.card .v{font-size:1.15rem;font-weight:600;margin-top:.15rem}
.card .n{color:#8b93a3;font-size:.78rem;margin-top:.1rem}
table{width:100%;border-collapse:collapse;margin:.8rem 0;font-size:.9rem}
th{text-align:left;color:#8b93a3;font-weight:500;font-size:.75rem;
 text-transform:uppercase;letter-spacing:.05em;padding:.5rem .6rem;border-bottom:1px solid #262a33}
td{padding:.55rem .6rem;border-bottom:1px solid #1c2028;vertical-align:top}
tr:last-child td{border-bottom:none}
.wk{background:#171a21;border:1px solid #262a33;border-radius:12px;
 padding:1rem 1.1rem;margin:1rem 0}
.wk-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:.6rem;margin-bottom:.2rem}
.wk-n{font-weight:700;font-size:1.05rem}
.wk-d{color:#8b93a3;font-size:.85rem}
.wk-km{margin-left:auto;font-weight:600;color:#7dd3a0}
.wk-f{color:#a8b0bf;font-size:.87rem;margin:.4rem 0 .8rem;font-style:italic}
.badge{display:inline-block;padding:.1rem .45rem;border-radius:5px;font-size:.7rem;
 font-weight:600;letter-spacing:.02em;white-space:nowrap}
.t-rest{background:#22262f;color:#7b8494}
.t-rec{background:#1e2a35;color:#79a8c9}
.t-easy{background:#1c2b26;color:#6dbb96}
.t-q{background:#332420;color:#e08b6a}
.t-mp{background:#33291a;color:#e0b46a}
.t-long{background:#2a2135;color:#b08cd9}
.t-race{background:#3a1f26;color:#f08fa3}
.key{color:#e0b46a;font-weight:700}
.d-day{color:#8b93a3;font-size:.8rem;white-space:nowrap}
.d-t{font-weight:600}
.d-km{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.d-desc{color:#a8b0bf;font-size:.85rem;margin-top:.25rem}
.pace{color:#7dd3a0;font-size:.8rem;font-weight:600;white-space:nowrap}
.warn{background:#2a1f1a;border:1px solid #4a3526;border-left:3px solid #e08b6a;
 border-radius:8px;padding:.85rem 1rem;margin:1rem 0}
.info{background:#151f26;border:1px solid #24384a;border-left:3px solid #79a8c9;
 border-radius:8px;padding:.85rem 1rem;margin:1rem 0}
ul{margin:.5rem 0;padding-left:1.2rem}li{margin:.25rem 0}
code{background:#22262f;padding:.1rem .3rem;border-radius:4px;font-size:.87em}
@media print{body{background:#fff;color:#000;max-width:none}
 .wk,.card,.warn,.info{border-color:#ccc;background:#fff;break-inside:avoid}
 h2{border-color:#ccc}}
"""


def render(plan: dict) -> str:
    m = plan["meta"]
    ps = m["paces_str"]
    weeks = [w for w in plan["weeks"] if w["week_num"] >= 9]
    total = sum(w["target_km"] for w in weeks)

    o: list[str] = []
    a = o.append

    a("<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>")
    a("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    a("<title>Plan NYC 2026 — Sebastien</title>")
    a(f"<style>{CSS}</style></head><body>")

    a("<h1>Plan marathon de New York — 1<sup>er</sup> novembre 2026</h1>")
    a("<p class='sub'>Plan définitif du 3 août au 1<sup>er</sup> novembre 2026 · "
      "13 semaines · recalibré le 2 août 2026 sur les performances réelles</p>")

    # ---- Cadre
    a("<h2>Le cadre</h2>")
    a("<div class='grid'>")
    for k, v, n in [
        ("Objectif NYC", "2h57", "4'12/km — sub-3h maîtrisé"),
        ("Objectif réel", "2h44", "Marathon de Milan, 4 avril 2027"),
        ("Volume total", f"{total:.0f} km", "sur 13 semaines"),
        ("Pic hebdo", f"{max(w['target_km'] for w in weeks):.0f} km", "semaine 16, 21-27 sept."),
        ("Sortie la plus longue", "32 km", "11 octobre · dont 18 km à allure course"),
        ("Séances clés", str(sum(1 for w in weeks for d in w["days"] if d.get("key"))),
         "réparties sur 13 semaines"),
    ]:
        a(f"<div class='card'><div class='k'>{k}</div><div class='v'>{v}</div>"
          f"<div class='n'>{n}</div></div>")
    a("</div>")

    a("<div class='info'><strong>Pourquoi 2h57 et pas 2h44 ?</strong><br>"
      "Le plan précédent était calibré sur une VMA estimée à 18,37 km/h, "
      "qui produisait des semaines à 100-110 km pendant huit semaines d'affilée — "
      "un volume que tu n'as jamais tenu. Résultat : zéro séance clé validée en un mois, "
      "et un coach automatique qui dégradait tout.<br><br>"
      "Ce plan est calibré sur ce que tu as réellement couru : "
      "<strong>2h50'03 le 12 avril 2026</strong>, 2h54'35 en octobre 2025, "
      "semi en 1h22'40. NYC est un parcours dur (ponts, remontée de la 5<sup>e</sup> Avenue) : "
      "compte 3 à 5 minutes de plus qu'un parcours plat. "
      "Viser 2h57 à NYC après un été creux, c'est une course maîtrisée qui te laisse "
      "frais pour attaquer un vrai bloc hivernal vers 2h44 à Milan.</div>")

    # ---- Allures
    a("<h2>Tes allures</h2>")
    a("<table><tr><th>Zone</th><th>Allure</th><th>Usage</th></tr>")
    for key, usage in [
        ("recup", "Lendemain de séance, footings de décrassage. FC &lt; 130."),
        ("footing", "Endurance fondamentale, 60 % du volume. FC &lt; 140. "
                    "<strong>C'est ici que tu triches</strong> : tes footings sortent à 4'50 avec 155 de FC."),
        ("le_long", "Sorties longues sans bloc rapide."),
        ("mp_strategy", "Départ prudent, plan B si la chaleur ou la forme l'imposent."),
        ("mp_target", "Allure objectif NYC. Toutes les séances « allure marathon »."),
        ("marathon", "Allure marathon « potentiel » — blocs progressifs en fin de sortie longue."),
        ("semi", "Séances tempo d'entretien."),
        ("seuil", "Séances de seuil du mardi. Le moteur du marathon."),
        ("10k", "Séances 8×1000 m et 6×1200 m."),
        ("vma", "Lignes et rappels de vitesse pure."),
    ]:
        a(f"<tr><td><strong>{key}</strong></td><td class='pace'>{ps[key]}</td>"
          f"<td>{usage}</td></tr>")
    a("</table>")

    # ---- Achille
    a("<h2>Le tendon d'Achille — à lire avant de courir</h2>")
    a("<div class='warn'>Une douleur au démarrage qui s'estompe en courant, c'est le signe "
      "d'une <strong>tendinopathie réactive débutante</strong>. Ça se gère très bien, "
      "mais ça ne se soigne pas en l'ignorant — et une reprise de vitesse mal dosée est "
      "exactement ce qui la fait basculer en tendinopathie chronique, qui coûte 3 à 6 mois. "
      "C'est le seul vrai risque sur ta préparation.</div>")
    a("<h3>La règle des 3/10</h3><ul>"
      "<li>Douleur <strong>≤ 3/10</strong> pendant la course, qui diminue en s'échauffant → tu continues.</li>"
      "<li>Douleur qui <strong>augmente</strong> pendant l'effort, ou qui persiste au-delà de 24 h → "
      "tu supprimes l'intensité pendant 5 jours, footings souples seulement.</li>"
      "<li><strong>Raideur matinale plus marquée</strong> que la veille → la charge d'hier était trop élevée.</li>"
      "<li>Douleur &gt; 4/10, boiterie, ou gonflement → arrêt de l'intensité et rendez-vous kiné.</li></ul>")
    a("<h3>Renforcement quotidien — non négociable</h3><ul>"
      "<li><strong>Mollets excentriques jambe tendue</strong> : 3×15, descente lente sur 3 s, "
      "sur une marche. Cible le gastrocnémien.</li>"
      "<li><strong>Mollets genou fléchi</strong> : 3×15, même tempo. Cible le soléaire — "
      "c'est celui qui encaisse en course à pied, et celui qu'on oublie.</li>"
      "<li>Une fois par jour les deux premières semaines, puis deux fois si bien toléré. "
      "Ajoute de la charge (sac à dos lesté) plutôt que des répétitions.</li>"
      "<li>Un tendon aime être chargé. Ne pas courir du tout est contre-productif : "
      "c'est la <em>progression</em> de la charge qui compte.</li></ul>")
    a("<h3>Ce que ça change dans le plan</h3><ul>"
      "<li>Tout ce qui est rapide se fait <strong>sur les chemins souples de Bouconne</strong>, "
      "pas sur bitume et pas sur piste avant d'être asymptomatique.</li>"
      "<li>Échauffement <strong>allongé à 4 km minimum</strong> avant chaque séance de qualité.</li>"
      "<li>Les côtes n'arrivent qu'en semaine 10, courtes et modérées : "
      "la montée charge fortement l'Achille.</li>"
      "<li>Chaussures habituelles, drop normal. Les pointes et le carbone seulement si "
      "le tendon est totalement silencieux — et pas avant octobre.</li></ul>")

    # ---- Chaleur
    a("<h2>La chaleur — août à Mondonville</h2><ul>"
      "<li>Séances de qualité et sorties longues <strong>avant 8 h</strong>. "
      "Au-delà de 25 °C, la FC grimpe de 8 à 12 battements à allure identique et la séance "
      "ne produit plus l'effet recherché.</li>"
      "<li><strong>Correction d'allure</strong> : +10 s/km entre 25 et 28 °C, "
      "+20 s/km au-delà. Une séance de seuil courue 10 s trop lentement par 30 °C reste "
      "une bonne séance de seuil. Une séance courue à l'allure prévue par 30 °C est une séance ratée.</li>"
      "<li>Bouconne à 2,5 km : les 2,5 km aller/retour font un échauffement et un retour au calme "
      "parfaits, et la forêt te donne l'ombre et le sol souple dont le tendon a besoin.</li>"
      "<li>500 ml/h minimum sur les sorties de plus de 1 h 15, avec électrolytes.</li></ul>")

    # ---- Structure
    a("<h2>La structure de la semaine</h2>")
    a("<p>Trois rendez-vous fixes, le reste est du volume facile. C'est volontairement "
      "simple : un plan qu'on retient est un plan qu'on suit.</p>")
    a("<table><tr><th>Jour</th><th>Contenu</th><th>Pourquoi</th></tr>"
      "<tr><td><strong>Mardi</strong></td><td>Seuil</td>"
      "<td>Le meilleur rapport bénéfice/fatigue pour le marathon. Repousse le seuil "
      "au-dessus de l'allure course.</td></tr>"
      "<tr><td><strong>Jeudi</strong></td><td>Allure marathon</td>"
      "<td>Spécificité pure : le geste et l'allure du jour J, à l'état frais.</td></tr>"
      "<tr><td><strong>Dimanche</strong></td><td>Sortie longue</td>"
      "<td>Endurance, économie de course, et sur les grosses semaines un bloc à allure "
      "course en fatigue — le plus proche de ce que demande la course.</td></tr>"
      "<tr><td>Lun / Ven</td><td>Repos ou récup</td><td>C'est là que le progrès se fabrique.</td></tr>"
      "<tr><td>Mer / Sam</td><td>Endurance</td><td>Volume aérobie. Lent. Vraiment lent.</td></tr>"
      "</table>")

    # ---- Semaines
    a("<h2>Le plan, semaine par semaine</h2>")
    for w in weeks:
        d0, d1 = fdate(w["start_date"]), fdate(w["end_date"])
        pont = " · plan pont" if w["week_num"] <= 10 else ""
        a("<div class='wk'>")
        a(f"<div class='wk-h'><span class='wk-n'>S{w['week_num']}</span>"
          f"<span class='wk-d'>{d0} → {d1} · {html.escape(w['phase_label'])}{pont}</span>"
          f"<span class='wk-km'>{w['target_km']:.0f} km</span></div>")
        if w.get("focus"):
            a(f"<div class='wk-f'>{html.escape(w['focus'])}</div>")
        a("<table>")
        for d in w["days"]:
            cls = TYPE_CLASS.get(d["type"], "t-easy")
            lbl = TYPE_LABEL.get(d["type"], d["type"])
            star = " <span class='key'>★</span>" if d.get("key") else ""
            km = f"{d['km']:g} km" if d["km"] else "—"
            pace = (f"<div class='pace'>{html.escape(d['target_pace'])}</div>"
                    if d.get("target_pace") else "")
            a(f"<tr><td class='d-day'>{JOURS[d['dow']]} {date.fromisoformat(d['date']).day}</td>"
              f"<td><span class='badge {cls}'>{lbl}</span></td>"
              f"<td><div class='d-t'>{html.escape(d['title'])}{star}</div>"
              f"<div class='d-desc'>{md_inline(d['description'])}</div></td>"
              f"<td class='d-km'>{km}{pace}</td></tr>")
        a("</table></div>")

    # ---- Points de contrôle
    a("<h2>Les trois points de contrôle</h2>")
    a("<table><tr><th>Quand</th><th>Quoi</th><th>Décision</th></tr>"
      "<tr><td><strong>13 sept.</strong><br><span class='d-day'>S14</span></td>"
      "<td>Test 10 km chrono</td>"
      "<td>Recalibre toutes les allures du bloc 2. 37'30 → on garde 4'12/km. "
      "36'30 → on peut viser 4'05. Au-delà de 38'30 → on sécurise à 4'18.</td></tr>"
      "<tr><td><strong>27 sept.</strong><br><span class='d-day'>S16</span></td>"
      "<td>SL 30 km dont 2×8 km à allure course</td>"
      "<td>Si les deux blocs passent sans dérive, le volume est assimilé. "
      "Sinon on allège la S18.</td></tr>"
      "<tr><td><strong>11 oct.</strong><br><span class='d-day'>S18</span></td>"
      "<td>SL signature 32 km dont 18 km à 4'12</td>"
      "<td>Le meilleur prédicteur de ta course. Tenue sans dérive → le sub-3h est acquis. "
      "Dérive de plus de 10 s/km sur les 6 derniers km → pars à 4'18 le jour J.</td></tr>"
      "</table>")

    a("<div class='info'><strong>Après NYC — la vraie cible</strong><br>"
      "Milan, le 4 avril 2027, c'est 22 semaines après New York. "
      "C'est le bon intervalle : 3 semaines de coupure, 6 semaines de reconstruction "
      "aérobie sans contrainte, puis un bloc de 12 semaines qui peut monter plus haut "
      "que celui-ci parce qu'il partira d'une base intacte plutôt que d'un été creux. "
      "Un NYC couru en maîtrise à 2h57 est une bien meilleure rampe de lancement "
      "vers 2h44 qu'un NYC couru à fond à 2h50.</div>")

    a(f"<p class='sub' style='margin-top:3rem'>Généré depuis "
      f"<code>data/plan_nyc.json</code> — source de vérité unique, "
      f"synchronisée avec le dashboard.</p>")
    a("</body></html>")
    return "\n".join(o)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    out.write_text(render(plan), encoding="utf-8")
    print(f"Écrit : {out}  ({out.stat().st_size / 1024:.0f} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
