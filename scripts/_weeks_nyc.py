"""
_weeks_nyc.py — Définition des semaines 9 à 21 du plan NYC 2026.

Révision du 2 août 2026 après analyse rétrospective des 7 marathons de Sebastien.

Ce que dit l'historique (10 semaines précédant chaque marathon) :

  Course          Temps      Volume   Départ 5k   Moyenne   Écart   Dérive 2e moitié
  Paris 2022      3h01'35     392 km    4'12        4'16      +4 s      -4'40
  Paris 2023      2h56'13     586 km    4'00        4'08      +8 s      -3'03
  Automne 2023    2h49'40     745 km    3'54        3'59      +5 s      -1'53   <- record
  Août 2024       3h12'54     683 km    4'10        4'30     +21 s      +6'38
  Paris 2025      2h56'12     701 km    3'50        4'08     +18 s      +3'13
  Chicago 2025    2h54'35     923 km    3'47        4'05     +18 s      +5'12   <- explosion
  Paris 2026      2h50'03     626 km    3'59        4'00      +1 s      -4'27

  → Corrélation écart de départ / dérive de la 2e moitié : r = +0.97
  → Le record est sorti du 2e plus gros volume. Le volume n'est pas le facteur
    limitant ; l'allure des 5 premiers kilomètres l'est.
  → Chicago cumulait les deux : 923 km (vs 4-5 sorties/sem habituelles → 6,7)
    ET un départ 18 s/km trop rapide. La fatigue n'a pas causé l'explosion,
    elle a faussé la perception de l'effort au départ.

Décisions retenues :
  1. Volume des 10 dernières semaines ramené de 837 à 777 km — le territoire du
     record (745), pas celui de Chicago (923).
  2. Affûtage approfondi : -45 % puis -63 %, mais la FRÉQUENCE est maintenue.
     Réduire le nombre de sorties dégrade la performance (Bosquet et al. 2007) ;
     c'est le volume et la durée qui s'effondrent, pas le nombre de sorties.
  3. Discipline d'allure travaillée à l'entraînement : sur toute séance à allure
     marathon, aller plus vite que la cible compte comme une séance ratée.
"""

# (type, titre, km, key, clé_allure|None, description)
# types : rest | recovery | easy | tempo | seuil | vma | mp | long | long_mp
#         | progressive | shake | race

R = ("rest", "Repos", 0.0, False, None,
     "Repos complet. Protocole mollets/Achille : 3×15 excentriques jambe tendue "
     "+ 3×15 genou fléchi (soléaire). Mobilité cheville 5 min.")

# Rappel inséré sur chaque séance à allure marathon
DISCIPLINE = ("\n⏱️ Règle absolue : ne JAMAIS aller plus vite que la cible. "
              "Plus rapide = séance ratée, au même titre que trop lent. "
              "C'est ici que se joue ta course.")

WEEKS: dict[int, dict] = {

    # ======================= PONT — 2 semaines =======================
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
             "Objectif : réapprendre la sensation." + DISCIPLINE),
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

    # ======================= BLOC 1 — spécifique =======================
    11: {
        "phase": "specific",
        "phase_label": "Spécifique · bloc 1",
        "focus": "Début du plan définitif. Structure fixe : seuil le mardi, "
                 "allure marathon le jeudi, sortie longue le dimanche.",
        "days": [
            R,
            ("seuil", "Seuil · 5×2000 m", 15.0, True, "seuil",
             "Échauffement 4 km. 5×2000 m à 3'50/km, récup 2'30 trot. Retour 2 km.\n"
             "Séance de référence du bloc : tu la reverras en S16. Note tes sensations "
             "et ta FC moyenne sur les répétitions."),
            ("easy", "Endurance", 13.0, False, "footing",
             "13 km à 5'10-5'25/km, FC < 140. Sortie tôt."),
            ("mp", "Allure marathon · 4×8 min", 15.0, True, "mp_target",
             "Échauffement 4 km + 4×8 min à 4'10-4'12/km, récup 2 min. Retour 3 km."
             + DISCIPLINE),
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
            ("easy", "Endurance", 13.0, False, "footing", "13 km à 5'10-5'25/km."),
            ("progressive", "Moyen-long progressif", 15.0, False, "le_long",
             "15 km : 9 km à 4'55 puis 6 km à 4'20/km. Progression continue, "
             "sans à-coup."),
            ("recovery", "Récupération", 9.0, False, "recup", "9 km très lent."),
            ("easy", "Endurance + côtes", 10.0, False, "footing",
             "10 km + 8×20\" en côte modérée. Travail de force pour les ponts de NYC."),
            ("long_mp", "SL 25 km · 10 km AM", 25.0, True, "mp_target",
             "25 km : 8 km d'échauffement à 5'00, puis 10 km à 4'12/km, "
             "puis 7 km de retour au calme.\n"
             "LA séance clé de la semaine. Le bloc doit être régulier au chrono, "
             "pas en dents de scie. Ravito : gel toutes les 40 min." + DISCIPLINE),
        ],
    },

    # ===== À partir du 2 septembre : piste avec Harbat le mercredi soir =====
    # La semaine bascule sur 2 séances dures espacées de 4 jours (mercredi piste,
    # dimanche sortie longue) au lieu de 3. Le travail à allure marathon migre
    # dans la sortie longue, là où il est le plus spécifique.
    13: {
        "phase": "specific",
        "phase_label": "Spécifique · bascule piste",
        "focus": "Première semaine du nouveau rythme : la piste du mercredi soir "
                 "devient le pilier qualité, la sortie longue du dimanche l'autre. "
                 "Mardi et vendredi passent en endurance pure.",
        "days": [
            ("recovery", "Récupération", 8.0, False, "recup",
             "8 km très lent après la SL d'hier."),
            ("easy", "Endurance + lignes", 13.0, False, "footing",
             "13 km à 5'10-5'25/km + 6×20\" de lignes. Jambes fraîches pour la piste demain."),
            ("vma", "🏟️ PISTE · Harbat", 15.0, True, "10k",
             "**Première séance piste depuis mai — la plus risquée de tout le plan "
             "pour ton Achille.**\n"
             "· Échauffement 20 min minimum, pas 10. Gammes complètes.\n"
             "· **Pas de pointes.** Chaussures d'entraînement habituelles, drop normal. "
             "La piste est déjà une surface dure et les virages chargent le tendon en torsion.\n"
             "· Fais **la moitié du volume du groupe** cette première fois. "
             "Tu peux finir la séance en trottinant à côté.\n"
             "· Retour au calme 15 min.\n"
             "Le lendemain matin, teste la raideur au démarrage : c'est ton indicateur."),
            ("recovery", "Récupération", 9.0, False, "recup",
             "9 km très lent, l'après-midi si possible — la piste était hier soir, "
             "laisse 16 h au tendon. Si la raideur matinale a nettement augmenté, "
             "remplace par 30 min de vélo."),
            ("easy", "Endurance", 14.0, False, "footing", "14 km à 5'10-5'25/km."),
            ("easy", "Endurance + lignes", 11.0, False, "footing", "11 km + 8 lignes."),
            ("long", "Sortie longue", 24.0, False, "le_long",
             "24 km à 4'50-5'00/km, sans bloc rapide : la semaine change déjà de "
             "structure, on ne cumule pas."),
        ],
    },

    14: {
        "phase": "specific",
        "phase_label": "Récupération · test",
        "focus": "Semaine allégée (-25 %) puis test 10 km. Préviens le groupe que "
                 "tu fais une séance courte mercredi : tu cours dimanche.",
        "days": [
            ("recovery", "Récupération", 6.0, False, "recup", "6 km très lent."),
            ("easy", "Endurance + lignes", 11.0, False, "footing", "11 km + 6 lignes."),
            ("vma", "🏟️ PISTE · version allégée", 12.0, True, "10k",
             "Séance du groupe mais **volume réduit de moitié**, et tu t'arrêtes "
             "franchement avant la dernière série. Tu as un test dimanche.\n"
             "Toujours sans pointes."),
            ("recovery", "Récupération", 7.0, False, "recup", "7 km très lent."),
            ("easy", "Endurance", 8.0, False, "footing", "8 km facile."),
            ("easy", "Déblocage", 5.0, False, "footing",
             "5 km très facile + 4 lignes. Jambes fraîches pour demain."),
            ("race", "TEST 10 km chrono", 21.0, True, "10k",
             "Échauffement 5 km + gammes. **10 km chrono à fond** (viser 37'00-37'30). "
             "Retour au calme 5 km.\n"
             "Un dossard local est idéal ; sinon en solo sur parcours plat et roulant. "
             "Le résultat recalibre toutes les allures du bloc 2 :\n"
             "  · 37'30 → marathon ≈ 2h52 → on garde 4'12/km à NYC\n"
             "  · 36'30 → marathon ≈ 2h47 → on peut viser 4'05/km\n"
             "  · > 38'30 → on sécurise à 4'18/km\n"
             "Deuxième objectif, aussi important : t'entraîner à partir juste. "
             "Premier km à l'allure cible, pas 10 s plus vite."),
        ],
    },

    15: {
        "phase": "specific",
        "phase_label": "Spécifique · bloc 2",
        "focus": "Reprise de la charge après le test. Les allures peuvent être "
                 "ajustées selon le chrono du 10 km.",
        "days": [
            ("recovery", "Récupération", 6.0, False, "recup", "6 km très lent."),
            ("easy", "Endurance", 12.0, False, "footing", "12 km à 5'10-5'25/km."),
            ("vma", "🏟️ PISTE · Harbat", 16.0, True, "10k",
             "Séance complète du groupe.\n"
             "**Si le format est en répétitions longues (1000 m et plus)** : c'est ta "
             "séance de seuil de la semaine, vise 3'45-3'50/km et ne cours pas plus vite.\n"
             "**Si le format est court (200-400 m)** : c'est du neuromusculaire, laisse "
             "le groupe partir devant sur les dernières et ajoute 10 min à 3'52/km "
             "en fin de séance.\n"
             "⏱️ Le vrai exercice du mercredi soir n'est pas la vitesse, c'est de "
             "courir TA séance et pas celle du voisin."),
            ("recovery", "Récupération", 9.0, False, "recup", "9 km très lent."),
            ("easy", "Endurance", 12.0, False, "footing", "12 km à 5'10-5'25/km."),
            ("easy", "Endurance + côtes", 8.0, False, "footing",
             "8 km + 8×20\" en côte modérée."),
            ("long_mp", "SL 27 km · 2×6 km AM", 27.0, True, "mp_target",
             "27 km : 6 km à 5'00, puis 2×6 km à 4'12/km avec 2 km de trot entre "
             "les blocs, puis retour au calme.\n"
             "Simulation de relance en fatigue — exactement ce que demande NYC "
             "après le pont de Queensboro." + DISCIPLINE),
        ],
    },

    16: {
        "phase": "peak",
        "phase_label": "Pic · volume max",
        "focus": "Semaine la plus volumineuse du plan (98 km). C'est le plafond : "
                 "au-delà, l'historique dit que tu paies en fraîcheur le jour J.",
        "days": [
            ("recovery", "Récupération", 6.0, False, "recup", "6 km très lent."),
            ("easy", "Endurance", 14.0, False, "footing", "14 km à 5'10-5'25/km."),
            ("vma", "🏟️ PISTE · Harbat", 17.0, True, "10k",
             "Séance complète. Demande à Harbat si le format peut inclure des "
             "répétitions longues (1000-2000 m) : c'est ce dont un marathonien a besoin, "
             "bien plus que du 400 m.\n"
             "Note ta FC moyenne sur les répétitions et compare à la S13 : "
             "c'est ton marqueur de progression le plus fiable."),
            ("recovery", "Récupération", 9.0, False, "recup", "9 km très lent."),
            ("easy", "Endurance", 13.0, False, "footing", "13 km à 5'10-5'25/km."),
            ("easy", "Endurance + lignes", 10.0, False, "footing", "10 km + 8 lignes."),
            ("long_mp", "SL 29 km · 2×8 km AM", 29.0, True, "mp_target",
             "29 km : 6 km à 5'00, 2×8 km à 4'12/km (2 km de trot entre), retour au calme.\n"
             "16 km à allure course en fin de grosse semaine. Ravito complet : "
             "gel toutes les 35 min, 500 ml/h." + DISCIPLINE),
        ],
    },

    17: {
        "phase": "peak",
        "phase_label": "Récupération · assimilation",
        "focus": "Décharge nette (-27 %) pour assimiler le bloc 2 et arriver frais "
                 "sur la sortie longue signature de la semaine suivante.",
        "days": [
            R,
            ("easy", "Endurance", 12.0, False, "footing", "12 km à 5'10-5'25/km."),
            ("vma", "🏟️ PISTE · version allégée", 14.0, True, "10k",
             "Séance du groupe à volume réduit d'un tiers. Semaine de décharge : "
             "l'intensité reste, le volume descend."),
            ("recovery", "Récupération", 8.0, False, "recup", "8 km très lent."),
            ("easy", "Endurance", 11.0, False, "footing", "11 km à 5'10-5'25/km."),
            ("easy", "Endurance + lignes", 8.0, False, "footing", "8 km + 8 lignes."),
            ("long", "Sortie longue avec finish", 19.0, False, "le_long",
             "19 km : 15 km à 4'55 puis 4 km à 4'20/km."),
        ],
    },

    18: {
        "phase": "peak",
        "phase_label": "Pic · séance signature",
        "focus": "LA semaine du plan. Dimanche est prioritaire sur tout le reste — "
                 "mercredi soir, tu lèves le pied même si le groupe part fort.",
        "days": [
            ("recovery", "Récupération", 6.0, False, "recup", "6 km très lent."),
            ("easy", "Endurance", 13.0, False, "footing", "13 km à 5'10-5'25/km."),
            ("vma", "🏟️ PISTE · modérée", 15.0, True, "10k",
             "**Séance volontairement bridée : 60-70 % du volume du groupe, et tu "
             "restes 2-3 s/km en retrait sur chaque répétition.**\n"
             "La sortie longue de dimanche est le meilleur prédicteur de ta course. "
             "Arriver dessus avec des jambes fraîches vaut infiniment plus qu'une "
             "belle séance de piste le mercredi."),
            ("recovery", "Récupération", 8.0, False, "recup", "8 km très lent."),
            ("easy", "Endurance", 12.0, False, "footing", "12 km à 5'10-5'25/km."),
            ("easy", "Déblocage", 8.0, False, "footing", "8 km facile + 6 lignes."),
            ("long_mp", "🎯 SL SIGNATURE 32 km · 18 km AM", 32.0, True, "mp_target",
             "32 km : 8 km à 5'00, puis **18 km en continu à 4'12/km**, puis 6 km "
             "de retour au calme.\n"
             "Répétition générale complète : mêmes chaussures, mêmes gels, même "
             "petit-déjeuner et même horaire que le jour J.\n"
             "Deux critères de réussite, à noter :\n"
             "  1. Les 18 km tenus sans dérive de plus de 5 s/km entre le 1er et "
             "le dernier tiers.\n"
             "  2. Aucun kilomètre couru plus vite que 4'08.\n"
             "Si les deux sont validés, le sub-3h à NYC est acquis." + DISCIPLINE),
        ],
    },

    19: {
        "phase": "peak",
        "phase_label": "Dernier bloc solide",
        "focus": "Dernière semaine consistante, et dernière vraie séance de piste. "
                 "À partir de lundi prochain, tout descend jusqu'à la course.",
        "days": [
            R,
            ("easy", "Endurance", 12.0, False, "footing", "12 km à 5'10-5'25/km."),
            ("vma", "🏟️ PISTE · dernière complète", 15.0, True, "10k",
             "Dernière séance de piste à volume plein. Profite-en : à partir de la "
             "semaine prochaine, tout est raccourci."),
            ("recovery", "Récupération", 8.0, False, "recup", "8 km très lent."),
            ("easy", "Endurance", 12.0, False, "footing", "12 km à 5'10-5'25/km."),
            ("easy", "Endurance + lignes", 11.0, False, "footing", "11 km + 8 lignes."),
            ("long_mp", "SL 22 km · 8 km AM en fin", 22.0, True, "mp_target",
             "22 km : 12 km à 4'55, puis 8 km à 4'12/km, puis 2 km de retour au calme. "
             "Dernière sortie longue avec du contenu." + DISCIPLINE),
        ],
    },

    # ======================= AFFÛTAGE =======================
    20: {
        "phase": "taper",
        "phase_label": "Affûtage · J-14",
        "focus": "Volume -45 %, mais on garde 5 sorties et toute l'intensité. "
                 "Réduire le nombre de sorties dégrade la performance ; c'est la "
                 "DURÉE qui s'effondre, pas la fréquence. Ça va te sembler trop peu : "
                 "c'est exactement le but.",
        "days": [
            R,
            ("easy", "Endurance + lignes", 12.0, False, "footing",
             "12 km à 5'10-5'25/km + 6 lignes."),
            ("vma", "🏟️ PISTE · raccourcie", 11.0, True, "10k",
             "**Moitié du volume du groupe, et tu pars avant la fin.** Allure "
             "habituelle, pas plus vite.\n"
             "C'est la séance où l'ego fait le plus de dégâts : tu vas te sentir "
             "très bien (c'est l'affûtage qui commence à agir) et vouloir en faire plus. "
             "Le bénéfice est nul, le risque ne l'est pas."),
            ("recovery", "Récupération", 6.0, False, "recup", "6 km très lent."),
            ("mp", "Allure marathon · 5 km", 11.0, True, "mp_target",
             "Échauffement 4 km + 5 km en continu à 4'12/km + retour 2 km.\n"
             "Dernier vrai contact avec l'allure course. Mémorise la sensation : "
             "c'est celle que tu dois retrouver au km 5 à New York." + DISCIPLINE),
            R,
            ("long", "Dernière sortie longue", 16.0, False, "le_long",
             "16 km : 12 km à 4'55 puis 4 km à 4'20/km. Courte et tonique."),
        ],
    },

    21: {
        "phase": "race",
        "phase_label": "Semaine de course",
        "focus": "35 km d'entraînement, soit -63 % : la charge la plus basse du plan. "
                 "Quatre jours en France, vol le vendredi 30 à midi, arrivée à NYC "
                 "en fin d'après-midi. Beaucoup de sommeil.",
        "days": [
            ("recovery", "Récupération", 6.0, False, "recup",
             "6 km très lent après la sortie longue d'hier. Dernier jour où tu peux "
             "te sentir lourd sans que ce soit un signal."),
            ("mp", "Dernier réveil musculaire", 8.0, True, "mp_target",
             "Échauffement 3 km + 3×3 min à 4'10/km (récup 2 min) + retour 2 km.\n"
             "Dernière touche d'allure course. Courte, tonique, zéro fatigue. "
             "À partir de ce soir : recharge glucidique 8-10 g/kg/jour." + DISCIPLINE),
            ("easy", "Endurance + lignes", 6.0, False, "footing",
             "6 km facile + 6×20\" de lignes en souplesse.\n"
             "🏟️ **Pas de piste ce soir.** Préviens Harbat maintenant, pas mercredi : "
             "une séance de groupe à 4 jours du marathon est le meilleur moyen de "
             "gâcher 13 semaines de travail."),
            ("easy", "Dernier footing en France", 6.0, False, "footing",
             "6 km très facile. Valise le soir : chaussures de course, dossard, gels "
             "et tenue de course **dans le bagage cabine** — jamais en soute."),
            ("easy", "Déverrouillage avant le vol", 5.0, False, "recup",
             "5 km très lent au lever, avant de partir à l'aéroport. Vol à midi.\n"
             "Dans l'avion : boire beaucoup, se lever toutes les 90 min, chaussettes "
             "de compression. Cale-toi sur l'heure de New York dès l'embarquement — "
             "tu arrives en fin d'après-midi, tiens jusqu'à 22 h locales avant de dormir."),
            ("shake", "Déblocage + expo", 4.0, False, "recup",
             "4 km très lent le matin dans Central Park — la lumière du matin recale "
             "l'horloge biologique bien mieux qu'une grasse matinée.\n"
             "**Expo au Javits Center dans la foulée** : c'est le seul retrait possible "
             "du dossard, il n'y en a pas le jour de la course, et l'expo ferme le samedi "
             "en fin d'après-midi. Vas-y tôt, reste 1 h maximum, puis jambes en l'air.\n"
             "Préparation du sac, épinglage du dossard, petit-déjeuner testé. "
             "Couché tôt : départ pour Staten Island au milieu de la nuit."),
            ("race", "🏁 MARATHON DE NEW YORK", 42.2, True, "mp_target",
             "**Objectif : 2h57 — 4'12/km de moyenne, en négatif.**\n\n"
             "Tes 7 marathons disent une seule chose : quand tu pars à moins de "
             "8 s/km de ton allure moyenne finale, tu négatives et tu performes. "
             "Quand tu pars 18 s/km trop vite, tu perds 3 à 6 minutes. "
             "Sans exception, corrélation 0,97. Chicago = départ à 3'47.\n\n"
             "**La seule règle qui compte : aucun kilomètre sous 4'08 avant le 30e.**\n\n"
             "· km 1-3 (pont de Verrazzano) : 4'20-4'25 en montée. Le pont te protège "
             "de toi-même, laisse-le faire. En descente, ne pas relancer.\n"
             "· km 4-25 (Brooklyn) : 4'12-4'14. C'est plat, la foule est énorme, tu vas "
             "te sentir invincible. C'EST LE PIÈGE — c'est exactement là que Chicago "
             "s'est joué. Regarde ta montre tous les kilomètres.\n"
             "· km 25-26 (pont de Queensboro) : +15 à 20 s/km, silencieux et raide. "
             "Tu perds du temps ici, c'est prévu, ne compense pas.\n"
             "· km 27-32 (1re Avenue) : la foule pousse. Tiens 4'10-4'12. "
             "Ne convertis pas l'émotion en vitesse.\n"
             "· km 33-37 (Bronx et retour) : le vrai marathon commence. Objectif : "
             "ne pas dépasser 4'16.\n"
             "· km 38-42 (Central Park) : ça monte par paliers. Si tu as respecté "
             "les 37 premiers, c'est ici que tu doubles des dizaines de coureurs. "
             "Tout donner sur les 2 derniers.\n\n"
             "Ravitaillement : 1 gel toutes les 35-40 min à partir du km 8, "
             "boire à chaque poste."),
        ],
    },
}
