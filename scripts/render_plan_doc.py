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
.shoe{margin-top:.35rem;font-size:.8rem;color:#8fbfa8;background:#16211c;
 border:1px solid #23372e;border-radius:6px;padding:.2rem .45rem;display:inline-block}
.shoe-n{color:#7b8494}
.bar{height:6px;border-radius:3px;background:#22262f;overflow:hidden;margin-top:.25rem}
.bar>i{display:block;height:100%}
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
    d10 = [w["target_km"] for w in weeks if w["week_num"] >= 12]
    d10[-1] -= 42.2
    for k, v, n in [
        ("Objectif NYC", "2h57", "4'12/km, en négatif"),
        ("Objectif réel", "2h44", "Marathon de Milan, 4 avril 2027"),
        ("10 dernières semaines", f"{sum(d10):.0f} km", "record 2023 : 745 · Chicago : 923"),
        ("Pic hebdo", f"{max(w['target_km'] for w in weeks):.0f} km", "semaine 16, 21-27 sept."),
        ("Sortie la plus longue", "32 km", "11 octobre · dont 18 km à allure course"),
        ("Semaine de course", "35 km", "hors marathon — soit −59 %"),
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

    # ---- Rétrospective
    a("<h2>Ce que disent tes sept marathons</h2>")
    a("<p>Volume des 10 semaines précédant chaque course, allure des 5 premiers "
      "kilomètres, et dérive de la seconde moitié.</p>")
    a("<table><tr><th>Course</th><th>Temps</th><th>10 sem.</th><th>Départ 5 km</th>"
      "<th>Moyenne</th><th>Écart</th><th>Dérive 2<sup>e</sup> moitié</th></tr>")
    for name, tps, vol, dep, moy, ec, dr, good in [
        ("Paris 2022", "3h01'35", "392 km", "4'12", "4'16", "+4 s", "−4'40", True),
        ("Paris 2023", "2h56'13", "586 km", "4'00", "4'08", "+8 s", "−3'03", True),
        ("Automne 2023", "2h49'40", "745 km", "3'54", "3'59", "+5 s", "−1'53", True),
        ("Août 2024", "3h12'54", "683 km", "4'10", "4'30", "+21 s", "+6'38", False),
        ("Paris 2025", "2h56'12", "701 km", "3'50", "4'08", "+18 s", "+3'13", False),
        ("Chicago 2025", "2h54'35", "923 km", "3'47", "4'05", "+18 s", "+5'12", False),
        ("Paris 2026", "2h50'03", "626 km", "3'59", "4'00", "+1 s", "−4'27", True),
    ]:
        col = "#7dd3a0" if good else "#f08fa3"
        pb = " 🏆" if tps == "2h49'40" else ""
        a(f"<tr><td><strong>{name}</strong>{pb}</td><td>{tps}</td><td>{vol}</td>"
          f"<td>{dep}</td><td>{moy}</td><td><strong>{ec}</strong></td>"
          f"<td style='color:{col};font-weight:600'>{dr}</td></tr>")
    a("</table>")

    a("<div class='warn'><strong>Le volume n'est pas ton facteur limitant.</strong><br>"
      "Ton record — 2h49'40 — est sorti du <strong>deuxième plus gros bloc de ta vie, "
      "745 km</strong>. Pas d'un bloc léger.<br><br>"
      "Ce qui prédit tes courses, c'est la colonne « écart » : la vitesse de tes "
      "5 premiers kilomètres par rapport à ton allure moyenne finale. "
      "<strong>La corrélation avec la dérive de la seconde moitié est de 0,97</strong> — "
      "c'est quasiment déterministe.<br><br>"
      "Tes trois courses ratées partent 18 à 21 s/km trop vite. Tes quatre réussies, "
      "entre 1 et 8 s/km. Il n'y a pas une seule exception en sept marathons. "
      "À Chicago tu es parti à <strong>3'47/km</strong>, ton allure de semi.<br><br>"
      "Cela dit, tu n'as pas tort sur Chicago : 923 km avec 6,7 sorties par semaine "
      "contre 4 à 5 habituellement, c'est une rupture. La fatigue n'a pas causé "
      "l'explosion — elle a désarmé ton juge-arbitre, et 3'47 t'a semblé facile. "
      "D'où le choix de <strong>777 km</strong> ici : le territoire de ton record, "
      "pas celui de Chicago.</div>")

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
        # Défensif : sans cette clé, un import de plan qui n'aurait pas
        # tous les alias faisait planter le rendu — donc l'assemblage du
        # site Pages, donc le déploiement. Une ligne « — » vaut mieux
        # qu'un site figé sur l'ancienne version.
        pace = ps.get(key) or ps.get({'recup':'recovery','footing':'le_easy'}.get(key,''),'—')
        a(f"<tr><td><strong>{key}</strong></td><td class='pace'>{pace}</td>"
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

    # ---- Chaussures
    a("<h2>Les chaussures — plus important que d'habitude</h2>")
    a("<p>Avec un tendon d'Achille réactif, le drop et l'usure du couple de chaussures "
      "ne sont plus un détail de confort : un drop bas allonge le tendon davantage à "
      "chaque foulée, et une semelle morte augmente les contraintes globales. "
      "Kilométrages relevés sur Strava au 2 août :</p>")
    a("<div class='warn'><strong>Deux régimes, parce que ton placard est à la maison.</strong><br>"
      "Du 3 au 16 août à Mondonville tu n'as que <strong>trois paires</strong> : "
      "Boston 13, Evo SL usagée et Pegasus 40. C'est peu pour 144 km, et la seule "
      "vraiment saine est la Boston 13.<br><br>"
      "Conséquence : <strong>la Pegasus 40 ne part pas encore au recyclage.</strong> "
      "Morte ou pas, c'est ton unique 10 mm sur ces deux semaines, et garder un peu "
      "de variété de drop vaut mieux que tout faire en 6 mm. Elle est donc cantonnée "
      "aux deux footings de récup les plus courts et les plus lents — 21 km au total, "
      "à faible vitesse, où la semelle écrasée fait peu de dégâts. Elle passe à la "
      "poubelle le 17 août, pas avant.<br><br>"
      "Sur ces deux semaines, les talonnettes de 8-10 mm dans la Boston 13 et l'Evo SL "
      "sont donc plus utiles que jamais : c'est ce qui compense l'absence de vrai "
      "drop élevé.</div>")
    a("<h3>À partir du 17 août — le placard complet</h3>")
    a("<table><tr><th>Paire</th><th>Km</th><th>Drop</th><th>Rôle</th></tr>"
      "<tr><td><strong>Pegasus 41</strong></td><td>477 km</td><td>10 mm</td>"
      "<td style='color:#7dd3a0'>Récups et footings. Avec la On, c'est ce qui protège "
      "ton tendon.</td></tr>"
      "<tr><td><strong>On Cloudsurfer</strong></td><td>163 km</td>"
      "<td>10 mm<br><span class='d-day'>stack 37/27</span></td>"
      "<td style='color:#7dd3a0'>Ta meilleure carte pour l'Achille : drop élevé et "
      "peu usée. Elle porte le gros du volume facile.</td></tr>"
      "<tr><td><strong>Hyperboost Edge</strong><br><span class='d-day'>neuve</span></td>"
      "<td>0 km</td><td>6 mm<br><span class='d-day'>stack 45/39</span></td>"
      "<td style='color:#7dd3a0'>Le gros du volume facile et les récups. Stack maximal, "
      "donc amorti maximal — exactement ce qu'il faut quand on encaisse 144 km en "
      "deux semaines avec un tendon sensible. Trop pataude pour la qualité.</td></tr>"
      "<tr><td><strong>Adidas Evo SL</strong><br><span class='d-day'>neuve</span></td>"
      "<td>0 km</td><td>6 mm</td>"
      "<td style='color:#7dd3a0'>Footings moyens, lignes, sorties longues sans bloc. "
      "La polyvalente.</td></tr>"
      "<tr><td><strong>Adidas Boston 13</strong></td><td>157 km</td>"
      "<td>6 mm<br><span class='d-day'>stack 36/30</span></td>"
      "<td style='color:#7dd3a0'>Séances de qualité, tempo, sorties longues avec bloc "
      "à allure marathon.</td></tr>"
      "<tr><td><strong>Adidas Evo SL</strong><br><span class='d-day'>usagée</span></td>"
      "<td>749 km</td><td>6 mm</td>"
      "<td style='color:#e0b46a'>Fin de vie. Récups courtes jusqu'à épuisement, puis "
      "au recyclage.</td></tr>"
      "<tr><td><strong>Nike Vaporfly Next% 3</strong><br><span class='d-day'>neuve</span></td>"
      "<td>0 km</td><td>8 mm</td>"
      "<td style='color:#79a8c9'>Intacte jusqu'en octobre. Durée de vie utile "
      "250-350 km : chaque kilomètre d'entraînement est volé à la course.</td></tr>"
      "<tr><td><strong>Nike Pegasus 40</strong></td><td>1 137 km</td><td>10 mm annoncés</td>"
      "<td style='color:#f08fa3'>Récups courtes jusqu'au 16 août, puis au recyclage.</td></tr>"
      "</table>")

    a("<div class='info'><strong>Bonne nouvelle : tu n'as rien à acheter.</strong> "
      "Avec la Pegasus 41 et la On Cloudsurfer, tu retrouves deux paires à 10 mm dès le "
      "17 août — c'est exactement ce qui manquait. Elles portent donc en priorité les "
      "récups et les footings, là où se concentre le volume, pendant que les 6 mm "
      "(Boston, Evo SL, Hyperboost) prennent les séances rapides, où le temps passé "
      "est court.<br><br>"
      "Les talonnettes restent utiles en août ; tu peux les retirer progressivement en "
      "septembre à mesure que la raideur matinale disparaît.</div>")

    # ---- Projection d'usure
    proj = m.get("shoe_projection") or []
    if proj:
        a("<h3>Usure projetée au 1<sup>er</sup> novembre</h3>")
        a("<p>Kilométrage de chaque paire si tu suis la rotation du plan, "
          "rapporté à sa durée de vie estimée.</p>")
        a("<table><tr><th>Paire</th><th>Drop</th><th>Aujourd'hui</th><th>+ plan</th>"
          "<th>Au 1<sup>er</sup> nov.</th><th>Usure</th></tr>")
        for x in proj:
            if x["added_km"] == 0 and x["start_km"] == 0:
                continue
            pct = x["pct"]
            col = "#f08fa3" if pct >= 100 else ("#e0b46a" if pct >= 85 else "#7dd3a0")
            a(f"<tr><td><strong>{html.escape(x['name'])}</strong></td>"
              f"<td>{x['drop']} mm</td><td>{x['start_km']} km</td>"
              f"<td>+{x['added_km']} km</td><td>{x['end_km']} km</td>"
              f"<td><span style='color:{col};font-weight:600'>{pct} %</span>"
              f"<div class='bar'><i style='width:{min(pct,100)}%;background:{col}'></i></div></td></tr>")
        a("</table>")
        a("<div class='info'>Seules les deux paires déjà condamnées dépassent leur "
          "durée de vie, et elles ne portent que 55 km à elles deux. "
          "<strong>Tout le reste finit la préparation avec de la marge</strong> — "
          "la Boston 13 à 72 %, la Pegasus 41 à 82 %. Aucun achat nécessaire d'ici "
          "le 1<sup>er</sup> novembre.<br><br>"
          "Une nuance sur l'Alphafly « Prototype » : tu la crois peu utilisée, elle est "
          "en réalité à <strong>238 km</strong>, contre 126 km pour la « Chicago 25 ». "
          "C'est la Chicago la plus fraîche des deux — d'où son rôle de candidate "
          "principale pour la course, et la Prototype réservée au test 10 km de "
          "septembre pour écouler ses derniers kilomètres utiles.</div>")

    a("<h3>Rodage des trois paires neuves</h3>"
      "<p>Trois paires neuves d'un coup et un tendon réactif, ça ne va pas ensemble. "
      "Introduis-les <strong>une par une, à une semaine d'intervalle</strong>, et jamais "
      "sur une séance de qualité ou une sortie longue en premier. La Hyperboost Edge en "
      "particulier a une géométrie très différente de tout ce que tu portes (45 mm de "
      "stack, talon jugé encombrant par les testeurs) : première sortie à 8-10 km "
      "maximum, sur terrain régulier.</p>")

    a("<h3>Carbone et tendon : ce que je t'ai dit trop vite</h3>")
    a("<div class='info'>Ma règle « rien en carbone avant octobre » était mal formulée, "
      "et tu as eu raison de tiquer.<br><br>"
      "<strong>D'abord, la Boston 13 n'a pas de plaque carbone</strong> : ses EnergyRods 2.0 "
      "sont en fibre de verre, plus souples et moins rigides que les tiges infusées carbone "
      "de la gamme Adios Pro. Il n'y avait donc pas de contradiction à te la donner pour "
      "les séances de qualité.<br><br>"
      "<strong>Ensuite, et c'est plus intéressant : la plaque n'est pas l'ennemi du tendon "
      "d'Achille.</strong> Une chaussure à plaque rigide et à bascule marquée réduit le "
      "travail de la cheville et déporte la charge vers le genou et la hanche — c'est même "
      "le principe des semelles à bascule utilisées en rééducation pour décharger un "
      "Achille. Ce qui compte vraiment pour ton tendon, c'est le drop, la surface et la "
      "vitesse de progression, pas le matériau de la plaque.<br><br>"
      "La vraie raison de garder les Vaporfly au placard jusqu'en octobre est donc "
      "différente et plus prosaïque : leur durée de vie utile est de 250 à 350 km, et "
      "elles sont instables en fin de sortie longue quand la fatigue dégrade la foulée.</div>")

    a("<h3>Pour la course</h3>"
      "<p>Deux candidates : l'Alphafly 3 « Chicago 25 » (126 km, rodée, tu as déjà couru "
      "un marathon avec) et la Vaporfly Next% 3 neuve. Sur un parcours vallonné comme New "
      "York, la Vaporfly est plus maniable dans les montées, l'Alphafly plus protectrice "
      "sur la durée.<br>"
      "<strong>Tranche le 11 octobre :</strong> la sortie longue signature se court avec "
      "la paire pressentie. Si elle te va sur 32 km dont 18 à allure course, c'est la bonne. "
      "Prévois 30 à 50 km de rodage sur la paire retenue avant le jour J, pas plus.</p>")

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
    a("<p>Deux régimes, la bascule se fait le <strong>2 septembre</strong> avec la reprise "
      "de la piste avec Harbat le mercredi soir.</p>")

    a("<h3>Jusqu'au 30 août — trois séances</h3>")
    a("<table><tr><th>Jour</th><th>Contenu</th><th>Pourquoi</th></tr>"
      "<tr><td><strong>Mardi</strong></td><td>Seuil</td>"
      "<td>Le meilleur rapport bénéfice/fatigue pour le marathon.</td></tr>"
      "<tr><td><strong>Jeudi</strong></td><td>Allure marathon</td>"
      "<td>Spécificité pure : le geste et l'allure du jour J, à l'état frais.</td></tr>"
      "<tr><td><strong>Dimanche</strong></td><td>Sortie longue</td>"
      "<td>Endurance et économie de course.</td></tr>"
      "<tr><td>Lun / Ven</td><td>Repos ou récup</td><td>C'est là que le progrès se fabrique.</td></tr>"
      "<tr><td>Mer / Sam</td><td>Endurance</td><td>Volume aérobie. Lent. Vraiment lent.</td></tr>"
      "</table>")

    a("<h3>À partir du 2 septembre — deux séances, espacées de 4 jours</h3>")
    a("<table><tr><th>Jour</th><th>Contenu</th><th>Pourquoi</th></tr>"
      "<tr><td>Lundi</td><td>Récup</td><td>Lendemain de sortie longue.</td></tr>"
      "<tr><td>Mardi</td><td>Endurance</td><td>Jambes fraîches pour la piste.</td></tr>"
      "<tr><td><strong>Mercredi soir</strong></td><td><strong>🏟️ Piste · Harbat</strong></td>"
      "<td>Devient le pilier qualité de la semaine.</td></tr>"
      "<tr><td>Jeudi</td><td>Récup très lente</td>"
      "<td>Seulement 12 h après la piste. L'après-midi si possible.</td></tr>"
      "<tr><td>Vendredi</td><td>Endurance</td><td>Volume.</td></tr>"
      "<tr><td>Samedi</td><td>Endurance + lignes</td><td>Volume.</td></tr>"
      "<tr><td><strong>Dimanche</strong></td><td><strong>Sortie longue + bloc allure marathon</strong></td>"
      "<td>Le travail spécifique migre ici — l'endroit où il compte le plus.</td></tr>"
      "</table>")

    a("<div class='info'><strong>Pourquoi on passe de trois séances dures à deux.</strong><br>"
      "Mardi seuil + mercredi piste + jeudi allure marathon, ce serait trois jours durs "
      "consécutifs : intenable, et c'est la recette d'une blessure d'Achille.<br><br>"
      "Le mercredi devient donc ta séance de qualité et le travail à allure marathon "
      "migre dans la sortie longue du dimanche — où il est de toute façon plus spécifique, "
      "puisqu'il s'y court en fatigue, comme le jour J. Résultat : deux séances dures "
      "espacées de 4 jours, le volume est préservé, et tu récupères mieux qu'avant.</div>")

    a("<h3>Comment piloter la séance de piste</h3>")
    a("<table><tr><th>Format du soir</th><th>Ce que tu en fais</th></tr>"
      "<tr><td><strong>Répétitions longues</strong><br><span class='d-day'>1000 m et +</span></td>"
      "<td>C'est ta séance de seuil de la semaine. Vise 3'45-3'50/km et n'accélère pas. "
      "C'est le format le plus utile pour toi — demande à Harbat s'il peut en programmer "
      "régulièrement.</td></tr>"
      "<tr><td><strong>Répétitions courtes</strong><br><span class='d-day'>200-400 m</span></td>"
      "<td>C'est du neuromusculaire : utile mais peu spécifique du marathon. Laisse le "
      "groupe partir devant sur les dernières et ajoute 10 min continues à 3'52/km "
      "en fin de séance.</td></tr>"
      "</table>")
    a("<div class='warn'><strong>Le mercredi soir est ton laboratoire de discipline d'allure.</strong><br>"
      "Un groupe tire toujours plus vite que prévu, et c'est exactement le réflexe qui t'a "
      "coûté Chicago, Paris 2025 et août 2024. Chaque mercredi où tu cours TA séance et "
      "pas celle du voisin est une répétition du kilomètre 4 à Brooklyn.<br><br>"
      "<strong>Et pour l'Achille :</strong> la piste est la surface la plus dure de ton "
      "environnement, avec des virages qui chargent le tendon en torsion. "
      "Pas de pointes — chaussures d'entraînement habituelles, drop normal. "
      "Échauffement de 20 minutes, pas 10. Et la première séance du 2 septembre se fait "
      "à la moitié du volume du groupe, quoi qu'il arrive.</div>")

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
            shoe = ""
            if d.get("shoe"):
                shoe = (f"<div class='shoe'>👟 {html.escape(d['shoe'])}"
                        f"<span class='shoe-n'> — {html.escape(d.get('shoe_note',''))}</span></div>")
            # dow peut arriver sous plusieurs formats selon la source du plan.
            # On dérive un libellé jour à partir de la date, indépendamment.
            _dt = date.fromisoformat(d['date'])
            _dow_fr = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"][_dt.weekday()]
            a(f"<tr><td class='d-day'>{_dow_fr} {_dt.day}</td>"
              f"<td><span class='badge {cls}'>{lbl}</span></td>"
              f"<td><div class='d-t'>{html.escape(d['title'])}{star}</div>"
              f"<div class='d-desc'>{md_inline(d['description'])}</div>{shoe}</td>"
              f"<td class='d-km'>{km}{pace}</td></tr>")
        a("</table></div>")

    # ---- Affûtage
    a("<h2>L'affûtage — pourquoi pas un arrêt complet</h2>")
    a("<p>Ton intuition de décharger fortement est juste, et je suis allé plus loin "
      "que la version initiale : <strong>−35 % à J-14, −59 % sur la semaine de course</strong>. "
      "Mais « décharger » et « arrêter » sont deux choses différentes, et la nuance "
      "est celle qui fait gagner ou perdre 2 minutes.</p>")
    a("<table><tr><th>Variable</th><th>Ce qu'on fait</th><th>Pourquoi</th></tr>"
      "<tr><td><strong>Volume</strong></td><td style='color:#f08fa3'>−45 % puis −60 %</td>"
      "<td>C'est le levier principal. C'est lui qui vide la fatigue résiduelle.</td></tr>"
      "<tr><td><strong>Durée des sorties</strong></td><td style='color:#f08fa3'>Divisée par deux</td>"
      "<td>16 km au lieu de 32, 6 km au lieu de 13.</td></tr>"
      "<tr><td><strong>Intensité</strong></td><td style='color:#7dd3a0'>Maintenue</td>"
      "<td>Supprimer l'intensité fait chuter l'économie de course et la sensation "
      "de vitesse. Tu arriverais frais mais émoussé.</td></tr>"
      "<tr><td><strong>Fréquence</strong></td><td style='color:#7dd3a0'>Maintenue (5-6 sorties)</td>"
      "<td>C'est le point contre-intuitif : réduire le <em>nombre</em> de sorties dégrade "
      "la performance. Le corps interprète l'arrêt comme un désentraînement.</td></tr>"
      "</table>")
    a("<div class='info'>Sur la semaine de course, tes six sorties font 6, 8, 6, 6, 5 et 4 km. "
      "<strong>Ce ne sont pas des séances, ce sont des rappels.</strong> Une sortie de 6 km "
      "à 5'20/km ne coûte rien en fraîcheur et entretient le geste, le sommeil et le moral. "
      "Total : 35 km, la semaine la plus légère de tout le plan.<br><br>"
      "Le vrai piège de l'affûtage est mental : tu vas te sentir lourd et douter vers J-7. "
      "C'est le signe normal que la charge redescend plus vite que la sensation. "
      "<strong>Ne compense jamais par une sortie supplémentaire.</strong> "
      "Aucun entraînement fait dans les 14 derniers jours ne peut plus améliorer ta course ; "
      "il ne peut que la dégrader.</div>")

    # ---- Plan de course
    a("<h2>Le plan de course — la seule chose qui décide de ton chrono</h2>")
    a("<div class='warn' style='border-left-color:#f08fa3'>"
      "<strong>Aucun kilomètre sous 4'08 avant le 30<sup>e</sup>.</strong><br>"
      "C'est la seule règle. Si tu ne retiens qu'une ligne de ce document, c'est celle-là. "
      "Elle vaut plus que les 777 km qui la précèdent.</div>")
    a("<table><tr><th>Section</th><th>Allure</th><th>Ce qui se passe</th></tr>"
      "<tr><td><strong>km 1-3</strong><br><span class='d-day'>Verrazzano</span></td>"
      "<td class='pace'>4'20-4'25</td>"
      "<td>Le pont monte pendant 2 km. Il te protège de toi-même — laisse-le faire. "
      "En descente, ne relance pas.</td></tr>"
      "<tr><td><strong>km 4-25</strong><br><span class='d-day'>Brooklyn</span></td>"
      "<td class='pace'>4'12-4'14</td>"
      "<td>Plat, roulant, foule énorme, jambes fraîches. Tu vas te sentir invincible. "
      "<strong>C'est exactement là que Chicago s'est joué.</strong> Montre à chaque kilomètre.</td></tr>"
      "<tr><td><strong>km 25-26</strong><br><span class='d-day'>Queensboro</span></td>"
      "<td class='pace'>+15 à 20 s</td>"
      "<td>Raide et silencieux, sans spectateurs. Tu perds du temps ici : c'est prévu, "
      "ne compense pas en sortant du pont.</td></tr>"
      "<tr><td><strong>km 27-32</strong><br><span class='d-day'>1<sup>re</sup> Avenue</span></td>"
      "<td class='pace'>4'10-4'12</td>"
      "<td>Le mur de bruit le plus fort du marathon mondial. Ne convertis pas "
      "l'émotion en vitesse.</td></tr>"
      "<tr><td><strong>km 33-37</strong><br><span class='d-day'>Bronx / retour</span></td>"
      "<td class='pace'>≤ 4'16</td>"
      "<td>Le vrai marathon commence. Objectif défensif.</td></tr>"
      "<tr><td><strong>km 38-42</strong><br><span class='d-day'>Central Park</span></td>"
      "<td class='pace'>libre</td>"
      "<td>Ça monte par paliers. Si tu as respecté les 37 premiers kilomètres, "
      "c'est ici que tu doubles par dizaines. Tout donner.</td></tr>"
      "</table>")

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

    a("<h2>Et Milan, dans tout ça</h2>")
    a("<p>Milan, le 4 avril 2027, c'est 22 semaines après New York — l'intervalle idéal : "
      "3 semaines de coupure, 6 semaines de reconstruction aérobie sans contrainte, "
      "puis un bloc de 12 semaines.</p>")
    a("<div class='info'><strong>C'est ce bloc-là qui vise 2h44, et il dépend "
      "directement de la façon dont tu cours New York.</strong><br><br>"
      "Un NYC maîtrisé à 2h57 en négatif, sorti d'un bloc à 777 km : tu récupères en "
      "10 jours, tu attaques décembre sur une base intacte, et le bloc de Milan peut "
      "monter à 850-900 km parce qu'il partira d'un socle solide au lieu d'un été creux.<br><br>"
      "Un NYC couru à fond, ou pire un NYC explosé comme Chicago : 4 à 6 semaines de "
      "récupération réelle, une confiance entamée, et un bloc hivernal qui démarre en retard. "
      "C'est exactement le scénario qui t'a mené de Chicago à ton juillet creux.<br><br>"
      "New York n'est pas ton objectif. C'est ta rampe de lancement — et une répétition "
      "générale grandeur nature du seul geste technique qui te sépare de 2h44 : "
      "partir juste.</div>")

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
