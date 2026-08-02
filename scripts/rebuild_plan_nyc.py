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

R = ("rest", "Repos", 0.0, False, None,
     "Repos complet. Protocole mollets/Achille : 3×15 excentriques jambe tendue "
     "+ 3×15 genou fléchi (soléaire). Mobilité cheville 5 min.")

WEEKS: dict[int, dict] = {

    # ===================== PONT — 2 semaines =====================
    9: {
        "phase": "base",
        "phase_label": "Pont · reprise",
        "focus": "Refaire du volume propre. Zéro intensité dure : on réinstalle "
                 "l'allure facile et on charge le tendon progressivement.",
        "days": [
            R,
            ("easy", "Footing + lignes souples", 12.0, False, "footing",
             "12 km en endurance fondamentale VRAIE : 5'10-5'25/km, FC < 140. "
             "Puis 6×20\" de lignes en souplesse sur herbe, récup marche 40\". "
             "Objectif : relancer le neuromusculaire sans agresser l'Achille."),
            ("recovery", "Récupération", 10.0, False, "recup",
             "10 km très lent, 5'25-5'40/km. Sur chemin souple à Bouconne. "
             "Si raideur au démarrage : 10 min de marche avant de courir."),
            ("tempo", "Footing avec 2×10' en confort soutenu", 14.0, False, "marathon",
             "Échauffement 4 km, puis 2×10 min à 4'30-4'35/km (récup 3 min trot), "
             "retour au calme. Ce n'est PAS du seuil : allure « confortablement "
             "soutenue », tu dois pouvoir dire une phrase courte."),
            R,
            ("easy", "Footing + lignes", 11.0, False, "footing",
             "11 km à 5'10-5'25/km + 8×20\" de lignes sur herbe. "
             "Sortie avant 8h : la chaleur d'août à Mondonville plombe la FC."),
            ("long", "Sortie longue de reprise", 21.0, False, "le_long",
             "21 km à 4'55-5'10/km, sous les arbres de Bouconne. Départ 6h30-7h. "
             "Ravitaillement : 500 ml + 1 gel à mi-parcours pour réhabituer l'estomac."),
        ],
    },

    10: {
        "phase": "base",
        "phase_label": "Pont · réintroduction qualité",
        "focus": "Première vraie séance de seuil depuis le 3 mai, et premier "
                 "contact avec l'allure marathon. Tout sur sol souple.",
        "days": [
            R,
            ("seuil", "Seuil fractionné · 6×3 min", 15.0, True, "seuil",
             "Échauffement 4 km + gammes. Puis 6×3 min à 3'50-3'55/km, "
             "récup 90\" en trot. Retour au calme 3 km.\n"
             "Sur chemin roulant de Bouconne, PAS sur bitume : c'est ta première "
             "séance rapide depuis 3 mois, le tendon doit encaisser du souple."),
            ("recovery", "Récupération", 11.0, False, "recup",
             "11 km à 5'25-5'40/km. Vérifie la raideur matinale : si elle a "
             "augmenté après la séance d'hier, remplace par 30 min de vélo."),
            ("mp", "Allure marathon · 3×8 min", 15.0, True, "mp_target",
             "Échauffement 4 km, puis 3×8 min à 4'10-4'12/km (allure objectif NYC), "
             "récup 2 min trot. Retour 3 km.\n"
             "Objectif : réapprendre la sensation. Ne cherche pas plus vite."),
            R,
            ("easy", "Footing + côtes courtes", 11.0, False, "footing",
             "11 km + 6×20\" en côte modérée (5-6%), montée en souplesse, "
             "descente en marchant.\n"
             "⚠️ À faire seulement si l'Achille est silencieux au démarrage. "
             "Sinon : 8 lignes sur le plat à la place."),
            ("long", "Sortie longue avec finish", 24.0, False, "le_long",
             "24 km : 18 km à 4'55-5'05/km puis les 6 derniers à 4'20-4'25/km. "
             "Premier vrai test de fin de sortie en fatigue."),
        ],
    },

    # ===================== BLOC 1 — spécifique =====================
    11: {
        "phase": "specific",
        "phase_label": "Spécifique · bloc 1",
        "focus": "Début du plan définitif. Structure fixe : seuil le mardi, "
                 "allure marathon le jeudi, sortie longue le dimanche.",
        "days": [
            R,
            ("seuil", "Seuil · 5×2000 m", 15.0, True, "seuil",
             "Échauffement 4 km. 5×2000 m à 3'50/km, récup 2'30 trot. Retour 2 km.\n"
             "Séance de référence du bloc : tu la reverras. Note tes sensations."),
            ("easy", "Endurance", 13.0, False, "footing",
             "13 km à 5'10-5'25/km, FC < 140. Sortie tôt."),
            ("mp", "Allure marathon · 4×8 min", 15.0, True, "mp_target",
             "Échauffement 4 km + 4×8 min à 4'10-4'12/km, récup 2 min. Retour 3 km."),
            ("recovery", "Récupération", 8.0, False, "recup",
             "8 km très lent. Renforcement mollets après."),
            ("easy", "Endurance + lignes", 11.0, False, "footing",
             "11 km + 8×20\" de lignes en souplesse."),
            ("long", "Sortie longue", 22.0, False, "le_long",
             "22 km à 4'50-5'00/km. Régulier, sans accélération finale."),
        ],
    },

    12: {
        "phase": "specific",
        "phase_label": "Spécifique · bloc 1",
        "focus": "Premier gros bloc à allure marathon dans la sortie longue.",
        "days": [
            R,
            ("seuil", "Seuil long · 3×12 min", 16.0, True, "seuil",
             "Échauffement 4 km. 3×12 min à 3'52/km, récup 3 min trot. Retour 3 km.\n"
             "Allonger la durée à allure seuil : c'est le moteur du marathon."),
            ("easy", "Endurance", 14.0, False, "footing",
             "14 km à 5'10-5'25/km."),
            ("progressive", "Moyen-long progressif", 16.0, False, "le_long",
             "16 km : 10 km à 4'55 puis 6 km à 4'20/km. Progression continue."),
            ("recovery", "Récupération", 9.0, False, "recup",
             "9 km très lent."),
            ("easy", "Endurance + côtes", 11.0, False, "footing",
             "11 km + 8×20\" en côte modérée. Travail de force pour les ponts de NYC."),
            ("long_mp", "SL 26 km · 10 km AM", 26.0, True, "mp_target",
             "26 km : 8 km d'échauffement à 5'00, puis 10 km à 4'12/km (allure NYC), "
             "puis 8 km de retour au calme.\n"
             "LA séance clé de la semaine. Le bloc AM doit être régulier, pas "
             "en dents de scie. Ravito : gel toutes les 40 min."),
        ],
    },

    13: {
        "phase": "specific",
        "phase_label": "Spécifique · bloc 1",
        "focus": "Semaine la plus dure du bloc 1. Introduction du travail à "
                 "allure 10 km pour réveiller la cylindrée.",
        "days": [
            ("recovery", "Récupération", 8.0, False, "recup",
             "8 km très lent après la SL d'hier."),
            ("vma", "Allure 10 km · 8×1000 m", 16.0, True, "10k",
             "Échauffement 4 km + gammes. 8×1000 m à 3'40/km, récup 2 min trot. "
             "Retour 3 km.\n"
             "Sur chemin roulant ou piste si l'Achille est totalement silencieux."),
            ("easy", "Endurance", 14.0, False, "footing",
             "14 km à 5'10-5'25/km."),
            ("mp", "Allure marathon · 2×15 min", 17.0, True, "mp_target",
             "Échauffement 4 km + 2×15 min à 4'08-4'10/km, récup 3 min. Retour 4 km.\n"
             "On allonge les blocs : 15 min continues à allure course."),
            ("recovery", "Récupération", 9.0, False, "recup", "9 km très lent."),
            ("easy", "Endurance + lignes", 12.0, False, "footing",
             "12 km + 8×20\" de lignes."),
            ("long", "Sortie longue", 22.0, False, "le_long",
             "22 km à 4'50-5'00/km, sans bloc rapide : la semaine est déjà chargée."),
        ],
    },

    14: {
        "phase": "specific",
        "phase_label": "Récupération · test",
        "focus": "Semaine allégée (-25%) puis test 10 km pour recalibrer les "
                 "allures sur du concret plutôt que sur des estimations.",
        "days": [
            ("recovery", "Récupération", 8.0, False, "recup", "8 km très lent."),
            ("easy", "Endurance + lignes", 12.0, False, "footing",
             "12 km + 6×20\" de lignes."),
            ("easy", "Endurance", 12.0, False, "footing", "12 km à 5'10-5'25/km."),
            ("tempo", "Footing avec 20 min à allure semi", 13.0, False, "semi",
             "Échauffement 4 km + 20 min à 3'57/km + retour 3 km. Séance d'entretien."),
            R,
            ("easy", "Déblocage", 8.0, False, "footing",
             "8 km très facile + 4 lignes. Jambes fraîches pour demain."),
            ("race", "TEST 10 km chrono", 21.0, True, "10k",
             "Échauffement 5 km + gammes. **10 km chrono à fond** (viser 37'00-37'30). "
             "Retour au calme 5 km.\n"
             "Un dossard local est idéal ; sinon en solo sur parcours plat et roulant. "
             "Le résultat recalibre toutes les allures du bloc 2 :\n"
             "  · 37'30 → marathon ≈ 2h53 → on garde 4'12/km à NYC\n"
             "  · 36'30 → marathon ≈ 2h48 → on peut viser 4'05/km\n"
             "  · > 38'30 → on sécurise à 4'18/km"),
        ],
    },

    # ===================== BLOC 2 — spécifique lourd =====================
    15: {
        "phase": "specific",
        "phase_label": "Spécifique · bloc 2",
        "focus": "Reprise de la charge après le test. Les allures peuvent être "
                 "ajustées selon le chrono du 10 km.",
        "days": [
            R,
            ("seuil", "Seuil · 6×1500 m", 16.0, True, "seuil",
             "Échauffement 4 km. 6×1500 m à 3'45-3'48/km, récup 2'30. Retour 3 km."),
            ("easy", "Endurance", 14.0, False, "footing", "14 km à 5'10-5'25/km."),
            ("mp", "Allure marathon · 3×10 min", 16.0, True, "mp_target",
             "Échauffement 4 km + 3×10 min à 4'10/km, récup 2 min. Retour 3 km."),
            ("recovery", "Récupération", 9.0, False, "recup", "9 km très lent."),
            ("easy", "Endurance + côtes", 12.0, False, "footing",
             "12 km + 10×20\" en côte modérée."),
            ("long_mp", "SL 28 km · 2×6 km AM", 28.0, True, "mp_target",
             "28 km : 6 km à 5'00, puis 2×6 km à 4'12/km avec 2 km de trot entre "
             "les blocs, puis retour au calme.\n"
             "Simulation de relance en fatigue — exactement ce que demande NYC "
             "après le pont de Queensboro."),
        ],
    },

    16: {
        "phase": "peak",
        "phase_label": "Pic · volume max",
        "focus": "Semaine la plus volumineuse du plan (~106 km). Si le corps "
                 "proteste, c'est le volume qu'on coupe, pas la qualité.",
        "days": [
            ("recovery", "Récupération", 8.0, False, "recup", "8 km très lent."),
            ("seuil", "Seuil · 5×2000 m", 17.0, True, "seuil",
             "Échauffement 4 km. 5×2000 m à 3'48/km, récup 2'30. Retour 3 km.\n"
             "Même séance qu'en S11 : compare directement les sensations et la FC."),
            ("easy", "Endurance", 13.0, False, "footing", "13 km à 5'10-5'25/km."),
            ("mp", "Allure marathon · 2×20 min", 18.0, True, "mp_target",
             "Échauffement 4 km + 2×20 min à 4'10/km, récup 3 min. Retour 4 km.\n"
             "40 min cumulées à allure course : la séance la plus spécifique du bloc."),
            ("recovery", "Récupération", 9.0, False, "recup", "9 km très lent."),
            ("easy", "Endurance + lignes", 11.0, False, "footing", "11 km + 8 lignes."),
            ("long_mp", "SL 30 km · 2×8 km AM", 30.0, True, "mp_target",
             "30 km : 6 km à 5'00, 2×8 km à 4'12/km (2 km de trot entre), retour au calme.\n"
             "16 km à allure course en fin de grosse semaine. Ravito complet : "
             "gel toutes les 35 min, 500 ml/h."),
        ],
    },

    17: {
        "phase": "peak",
        "phase_label": "Récupération · assimilation",
        "focus": "Décharge nette (-30%) pour assimiler le bloc 2 et arriver frais "
                 "sur la sortie longue signature de la semaine suivante.",
        "days": [
            R,
            ("seuil", "Seuil continu · 20 min", 14.0, True, "seuil",
             "Échauffement 4 km + 20 min continues à 3'52/km + retour 4 km. "
             "Volume réduit, intensité maintenue."),
            ("easy", "Endurance", 13.0, False, "footing", "13 km à 5'10-5'25/km."),
            ("easy", "Endurance + lignes", 14.0, False, "footing",
             "14 km + 8×20\" de lignes. Pas de bloc AM cette semaine."),
            R,
            ("easy", "Endurance", 11.0, False, "footing", "11 km facile."),
            ("long", "Sortie longue avec finish", 24.0, False, "le_long",
             "24 km : 19 km à 4'55 puis 5 km à 4'20/km."),
        ],
    },

    18: {
        "phase": "peak",
        "phase_label": "Pic · séance signature",
        "focus": "LA semaine du plan. La sortie longue de dimanche est le meilleur "
                 "prédicteur de ta performance à NYC — 3 semaines avant, timing idéal.",
        "days": [
            ("recovery", "Récupération", 8.0, False, "recup", "8 km très lent."),
            ("vma", "Allure 10 km · 6×1200 m", 15.0, True, "10k",
             "Échauffement 4 km + 6×1200 m à 3'42/km, récup 2 min. Retour 3 km."),
            ("easy", "Endurance", 13.0, False, "footing", "13 km à 5'10-5'25/km."),
            ("mp", "Allure marathon · 3×10 min", 15.0, True, "mp_target",
             "Échauffement 4 km + 3×10 min à 4'10/km, récup 2 min. Retour 3 km. "
             "Séance courte : on garde le jus pour dimanche."),
            ("recovery", "Récupération", 9.0, False, "recup", "9 km très lent."),
            ("easy", "Déblocage", 10.0, False, "footing", "10 km facile + 6 lignes."),
            ("long_mp", "🎯 SL SIGNATURE 32 km · 18 km AM", 32.0, True, "mp_target",
             "32 km : 8 km à 5'00, puis **18 km en continu à 4'12/km**, puis 6 km "
             "de retour au calme.\n"
             "Répétition générale complète : mêmes chaussures, mêmes gels, même "
             "petit-déjeuner et même horaire que le jour J. Si tu tiens les 18 km "
             "sans dériver, le sub-3h à NYC est acquis."),
        ],
    },

    19: {
        "phase": "peak",
        "phase_label": "Dernier bloc solide",
        "focus": "Dernière semaine consistante. À partir de dimanche, tout "
                 "descend jusqu'à la course.",
        "days": [
            R,
            ("seuil", "Seuil · 4×1500 m", 15.0, True, "seuil",
             "Échauffement 4 km + 4×1500 m à 3'45/km, récup 2'30. Retour 3 km."),
            ("easy", "Endurance", 13.0, False, "footing", "13 km à 5'10-5'25/km."),
            ("mp", "Allure marathon · 2×12 min", 15.0, True, "mp_target",
             "Échauffement 4 km + 2×12 min à 4'10/km, récup 3 min. Retour 3 km."),
            ("recovery", "Récupération", 8.0, False, "recup", "8 km très lent."),
            ("easy", "Endurance + lignes", 11.0, False, "footing", "11 km + 8 lignes."),
            ("long_mp", "SL 24 km · 8 km AM en fin", 24.0, True, "mp_target",
             "24 km : 14 km à 4'55, puis 8 km à 4'12/km, puis 2 km de retour au calme. "
             "Dernière sortie longue avec du contenu."),
        ],
    },

    # ===================== AFFÛTAGE =====================
    20: {
        "phase": "taper",
        "phase_label": "Affûtage",
        "focus": "Volume -40 %, intensité maintenue mais raccourcie. La forme "
                 "ne se construit plus : elle se révèle. Résiste à l'envie d'en faire plus.",
        "days": [
            R,
            ("seuil", "Seuil court · 5×1000 m", 13.0, True, "seuil",
             "Échauffement 4 km + 5×1000 m à 3'45/km, récup 2 min. Retour 3 km. "
             "Ça doit sembler facile — c'est le but."),
            ("easy", "Endurance", 12.0, False, "footing", "12 km à 5'10-5'25/km."),
            ("mp", "Allure marathon · 6 km", 13.0, True, "mp_target",
             "Échauffement 4 km + 6 km en continu à 4'12/km + retour 3 km. "
             "Dernier vrai contact avec l'allure course."),
            R,
            ("easy", "Endurance + lignes", 10.0, False, "footing", "10 km + 6 lignes."),
            ("long", "Dernière sortie longue", 18.0, False, "le_long",
             "18 km : 14 km à 4'55 puis 4 km à 4'20/km. Courte et tonique."),
        ],
    },

    21: {
        "phase": "race",
        "phase_label": "Semaine de course",
        "focus": "Voyage, décalage horaire, expo. Peu de course, beaucoup de sommeil. "
                 "Recharge glucidique à partir de jeudi soir.",
        "days": [
            ("easy", "Dernier footing en France", 10.0, False, "footing",
             "10 km facile + 6×20\" de lignes. Dernière sortie avant le voyage."),
            ("rest", "Voyage", 0.0, False, None,
             "Vol vers New York. Marche, hydratation, compression si tu en as. "
             "Cale-toi sur l'heure de NY dès l'embarquement."),
            ("easy", "Déblocage à NYC", 8.0, False, "footing",
             "8 km très facile, le matin, pour caler l'horloge biologique. "
             "Central Park ou Hudson River Greenway."),
            ("mp", "Réveil musculaire", 10.0, True, "mp_target",
             "Échauffement 4 km + 3×3 min à 4'05-4'10/km (récup 2 min) + retour 3 km. "
             "Courte piqûre de rappel, aucune fatigue.\n"
             "Recharge glucidique à partir de ce soir : 8-10 g/kg/jour."),
            ("easy", "Footing court", 6.0, False, "footing",
             "6 km très facile + 4 lignes. Expo le matin, jambes en l'air l'après-midi."),
            ("shake", "Déblocage", 5.0, False, "recup",
             "5 km très lent. Préparation du sac, épinglage du dossard, "
             "petit-déjeuner testé. Couché tôt (départ à Staten Island très matinal)."),
            ("race", "🏁 MARATHON DE NEW YORK", 42.2, True, "mp_target",
             "**Objectif : 2h57 — 4'12/km de moyenne.**\n\n"
             "Plan de course :\n"
             "· km 1-3 (pont de Verrazzano) : 4'20-4'25 en montée, ne PAS courir "
             "après le chrono, puis laisser filer en descente sans forcer.\n"
             "· km 4-25 (Brooklyn) : 4'10-4'12 régulier, c'est plat et grisant — "
             "le piège est de partir à 4'02.\n"
             "· km 25-26 (pont de Queensboro) : +15 à 20\"/km, silencieux et raide. "
             "Tu perds du temps ici, c'est normal, tu le reprends sur la 1re Avenue.\n"
             "· km 27-32 (1re Avenue) : la foule pousse, tiens 4'10. Ne pas s'emballer.\n"
             "· km 33-37 (Bronx + retour) : le vrai marathon commence. Objectif : "
             "ne pas dépasser 4'18.\n"
             "· km 38-42 (Central Park) : ça monte par paliers. Tout donner sur "
             "les 2 derniers km.\n\n"
             "Ravitaillement : 1 gel toutes les 35-40 min à partir du km 8, "
             "boire à chaque poste."),
        ],
    },
}


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
    meta["plan_peak_km"] = 106.0

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
