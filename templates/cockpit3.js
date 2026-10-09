/* ============================================================================
   seb-metrics — cockpit3.js : MOBILITÉ

   Petits exercices de 3 à 10 minutes, qui ne font pas transpirer, faisables au
   bureau, sur le canapé, avant ou après une sortie. Chaque exercice a sa
   démonstration animée ; chaque routine se lance en mode guidé (minuteur,
   côtés gauche/droite, enchaînement automatique).

   Se branche sur :
     · l'onglet « Corps » (segment Mobilité / Renfo),
     · une carte « Mobilité du jour » sur l'accueil, qui propose la routine
       adaptée à la journée (avant la sortie, repos, soirée…).
   Dépend de cockpit.js (window.__ck) et de cockpit2.js (window.__ck2).
   ============================================================================ */
(function () {
  'use strict';
  const K = window.__ck, K2 = window.__ck2;
  if (!K || !K2) return;
  const { esc, svg, openSheet, closeSheet, toast, isoLocal, parse, TODAY, fmtDay, allDays } = K;
  const { EX, figHtml, startFigs } = K2;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  // ---------------------------------------------------------------- figures
  // Silhouettes de profil ou de face ; deux poses, interpolées en boucle.
  const FLOOR = '<line x1="10" y1="120" x2="190" y2="120" class="ck2-floor"/>';
  const WALL = '<rect x="152" y="14" width="10" height="106" rx="2" class="ck2-prop"/>' + FLOOR;
  const CHAIR = '<rect x="66" y="98" width="62" height="6" rx="2" class="ck2-prop"/><rect x="64" y="58" width="6" height="46" rx="2" class="ck2-prop"/><line x1="76" y1="104" x2="76" y2="120" class="ck2-floor"/><line x1="120" y1="104" x2="120" y2="120" class="ck2-floor"/>' + FLOOR;
  const SIDE = [['sh', 'hip', 'b'], ['hip', 'kF', 'f'], ['kF', 'aF', 'f'], ['aF', 'tF', 'f'], ['sh', 'eF', 'f'], ['eF', 'hF', 'f'],
    ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['aN', 'tN', 'n'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']];
  const FRONT = [['sh', 'hip', 'b'], ['shL', 'shR', 'n'], ['shL', 'eL', 'n'], ['eL', 'hL', 'n'], ['shR', 'eR', 'n'], ['eR', 'hR', 'n'],
    ['hip', 'kL', 'n'], ['kL', 'aL', 'n'], ['hip', 'kR', 'f'], ['kR', 'aR', 'f']];
  // Corps de profil debout, appui sur la jambe proche : base commune
  const upright = (o) => Object.assign({
    hd: [100, 32], sh: [100, 46], hip: [100, 74],
    kN: [100, 96], aN: [100, 118], tN: [111, 119],
    kF: [95, 96], aF: [95, 118], tF: [106, 119],
    eN: [103, 60], hN: [107, 72], eF: [97, 60], hF: [101, 72],
  }, o || {});

  const M = {
    leg_swing_fb: {
      name: 'Balancement de jambe avant-arrière', zone: 'Hanches · ischios', secs: 25, sides: 2, where: ['debout'], when: ['avant'],
      dose: '10 balancements par jambe', level: 'Facile', mode: 'loop', cue: 'Souple, sans forcer',
      why: "Réveille les hanches et prépare les ischios à la foulée. À faire avant de courir : ça chauffe sans fatiguer.",
      steps: ['Tiens-toi à un mur ou au dossier d\'une chaise, debout sur une jambe.', 'Balance l\'autre jambe d\'avant en arrière, comme un pendule, jambe détendue.', 'Augmente un peu l\'amplitude à chaque balancement, sans jamais forcer. Puis change de jambe.'],
      mistakes: ['Cambrer le dos quand la jambe part en arrière.', 'Balancer avec trop d\'élan, en forçant.'],
      fig: { props: FLOOR, bones: SIDE,
        A: upright({ kF: [117, 94], aF: [132, 110], tF: [140, 110], eN: [108, 58], hN: [118, 62], eF: [96, 58], hF: [90, 62] }),
        B: upright({ kF: [86, 94], aF: [70, 110], tF: [64, 108], eN: [108, 58], hN: [118, 62], eF: [96, 58], hF: [90, 62] }) },
    },
    leg_swing_side: {
      name: 'Balancement de jambe latéral', zone: 'Hanches · adducteurs', secs: 25, sides: 2, where: ['debout'], when: ['avant', 'anytime'],
      dose: '10 balancements par jambe', level: 'Facile', mode: 'loop', cue: 'Devant le mur, jambe qui croise',
      why: "Assouplit les adducteurs et les abducteurs : le côté du bassin que la course oublie. Utile vu ton historique d'aine.",
      steps: ['Face à un mur, les mains dessus, debout sur une jambe.', 'Balance l\'autre jambe de côté, puis devant l\'autre jambe, en alternant.', 'Garde le buste droit. Change de jambe.'],
      mistakes: ['Pencher le buste du côté opposé à chaque balancement.', 'Chercher l\'amplitude maximale d\'entrée.'],
      fig: { props: FLOOR, bones: FRONT,
        A: { hd: [100, 30], sh: [100, 46], shL: [86, 48], shR: [114, 48], hip: [100, 74], eL: [80, 62], hL: [78, 54], eR: [120, 62], hR: [122, 54], kL: [94, 96], aL: [94, 118], kR: [104, 96], aR: [106, 118] },
        B: { hd: [100, 30], sh: [100, 46], shL: [86, 48], shR: [114, 48], hip: [100, 74], eL: [80, 62], hL: [78, 54], eR: [120, 62], hR: [122, 54], kL: [94, 96], aL: [94, 118], kR: [118, 92], aR: [134, 108] } },
    },
    knee_hug: {
      name: 'Genou à la poitrine', zone: 'Hanches · fessiers', secs: 25, sides: 2, where: ['debout'], when: ['avant', 'anytime'],
      dose: '8 montées par jambe', level: 'Facile', mode: 'loop', cue: 'Grand sur ta jambe d\'appui',
      why: "Étire doucement le fessier et la hanche de la jambe qui monte, et active l\'équilibre sur l\'autre : exactement ce que fait la foulée.",
      steps: ['Debout, monte un genou vers la poitrine.', 'Attrape-le avec les mains, tire doucement 1 seconde.', 'Repose le pied, change de jambe : à répéter en marchant sur place.'],
      mistakes: ['Se pencher en avant au lieu de rester grand.', 'Forcer avec les bras si le genou résiste.'],
      fig: { props: FLOOR, bones: SIDE,
        A: upright(),
        B: upright({ kF: [116, 62], aF: [110, 84], tF: [120, 86], eN: [110, 56], hN: [112, 70], eF: [108, 58], hF: [112, 72] }) },
    },
    quad_stretch: {
      name: 'Étirement du quadriceps debout', zone: 'Cuisses (devant)', secs: 30, sides: 2, where: ['debout'], when: ['apres', 'anytime'],
      dose: '30 s par jambe', level: 'Facile', mode: 'hold', cue: 'Genoux serrés, bassin sous toi',
      why: "Détend l\'avant de la cuisse, qui travaille beaucoup en descente et en fin de marathon.",
      steps: ['Debout, appuie une main au mur.', 'Plie un genou et attrape le pied derrière toi, talon vers la fesse.', 'Rentre le ventre, serre les genoux l\'un contre l\'autre, tiens 30 secondes.'],
      mistakes: ['Cambrer le bas du dos : le bassin doit rester neutre.', 'Écarter le genou vers l\'extérieur.'],
      fig: { props: FLOOR, bones: SIDE,
        A: upright({ kF: [96, 96], aF: [86, 96], tF: [80, 96], eN: [106, 62], hN: [118, 60], eF: [96, 62], hF: [90, 90] }),
        B: upright({ kF: [97, 98], aF: [88, 82], tF: [82, 76], eN: [106, 62], hN: [118, 60], eF: [97, 66], hF: [89, 80] }) },
    },
    knee_to_wall: {
      name: 'Genou au mur', zone: 'Cheville · mollet', secs: 30, sides: 2, where: ['debout'], when: ['avant', 'apres', 'achille'],
      dose: '10 allers-retours par côté', level: 'Facile', mode: 'loop', cue: 'Talon collé au sol',
      why: "La souplesse de la cheville (flexion du pied) conditionne ta foulée et soulage le tendon d\'Achille. Un geste doux, pas un étirement fort.",
      steps: ['Pieds à 10 cm du mur, un pied devant, talon bien posé.', 'Pousse le genou vers le mur sans décoller le talon, puis reviens.', 'Si tu touches facilement, recule le pied de quelques centimètres.'],
      mistakes: ['Décoller le talon.', 'Forcer si ça tire au niveau de l\'insertion du tendon : tu t\'arrêtes à la première tension.'],
      fig: { props: WALL, bones: SIDE,
        A: { hd: [92, 28], sh: [96, 42], hip: [100, 70], kN: [114, 94], aN: [108, 118], tN: [120, 119], kF: [92, 94], aF: [78, 116], tF: [86, 119], eN: [112, 54], hN: [130, 58], eF: [110, 56], hF: [128, 60] },
        B: { hd: [118, 30], sh: [120, 44], hip: [122, 72], kN: [140, 96], aN: [108, 118], tN: [120, 119], kF: [108, 96], aF: [92, 116], tF: [100, 119], eN: [136, 54], hN: [148, 58], eF: [134, 56], hF: [146, 60] } },
    },
    calf_wall: {
      name: 'Mollets au mur', zone: 'Mollets', secs: 35, sides: 2, where: ['debout', 'bureau'], when: ['apres', 'anytime', 'achille'],
      dose: '35 s par jambe', level: 'Facile', mode: 'hold', cue: 'Talon arrière au sol',
      why: "Détend le mollet et soulage la chaîne arrière. À faire doucement, surtout quand le tendon d\'Achille est sensible.",
      steps: ['Les mains au mur, une jambe devant, l\'autre tendue derrière, talon au sol.', 'Avance le bassin vers le mur jusqu\'à sentir un étirement doux dans le mollet arrière.', 'Tiens 35 secondes, sans rebond. Puis plie légèrement le genou arrière pour cibler le bas du mollet.'],
      mistakes: ['Soulever le talon arrière.', 'Chercher la douleur : tu ressens une tension, jamais une douleur dans le talon.'],
      fig: { props: WALL, bones: SIDE,
        A: { hd: [126, 34], sh: [122, 48], hip: [108, 72], kN: [126, 94], aN: [124, 118], tN: [136, 119], kF: [92, 94], aF: [76, 116], tF: [84, 119], eN: [138, 52], hN: [150, 56], eF: [136, 54], hF: [149, 58] },
        B: { hd: [134, 36], sh: [130, 50], hip: [116, 74], kN: [134, 96], aN: [124, 118], tN: [136, 119], kF: [98, 94], aF: [80, 116], tF: [88, 119], eN: [142, 54], hN: [150, 56], eF: [141, 56], hF: [149, 58] } },
    },
    lunge_psoas: {
      name: 'Fente basse : avant de la hanche', zone: 'Fléchisseurs de hanche', secs: 40, sides: 2, where: ['sol', 'canape'], when: ['apres', 'anytime'],
      dose: '40 s par côté', level: 'Moyen', mode: 'loop', cue: 'Bassin vers l\'avant, dos droit',
      why: "Quand on est assis toute la journée, le muscle devant la hanche raccourcit et limite ta foulée. Celui-ci le rouvre.",
      steps: ['Un genou au sol (sur un coussin), l\'autre pied devant, genou au-dessus de la cheville.', 'Rentre le ventre, pousse doucement le bassin vers l\'avant.', 'Tu sens un étirement devant la hanche du genou posé. Tiens, puis change de côté.'],
      mistakes: ['Cambrer le bas du dos.', 'Laisser le genou avant dépasser largement le pied.'],
      fig: { props: FLOOR, bones: SIDE,
        A: { hd: [96, 34], sh: [96, 48], hip: [94, 80], kN: [120, 94], aN: [122, 118], tN: [134, 119], kF: [80, 117], aF: [58, 112], tF: [52, 118], eN: [100, 66], hN: [112, 78], eF: [98, 66], hF: [110, 80] },
        B: { hd: [108, 40], sh: [108, 54], hip: [106, 86], kN: [128, 96], aN: [124, 118], tN: [136, 119], kF: [84, 117], aF: [60, 112], tF: [54, 118], eN: [112, 70], hN: [122, 82], eF: [110, 70], hF: [120, 84] } },
    },
    cat_cow: {
      name: 'Chat-vache', zone: 'Colonne · bassin', secs: 45, sides: 1, where: ['sol', 'canape'], when: ['anytime', 'apres'],
      dose: '10 allers-retours lents', level: 'Facile', mode: 'loop', cue: 'Respire : creux à l\'inspiration',
      why: "Délie la colonne et le bassin en douceur. Idéal pour se redresser après une journée de travail assis.",
      steps: ['À quatre pattes, mains sous les épaules, genoux sous les hanches.', 'Inspire : creuse le dos et regarde devant.', 'Expire : arrondis le dos et rentre le menton. Enchaîne lentement.'],
      mistakes: ['Aller vite.', 'Plier les coudes.'],
      fig: { props: FLOOR,
        bones: [['hip', 'mid', 'b'], ['mid', 'sh', 'b'], ['sh', 'hd2', 'b'], ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['aN', 'tN', 'n'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']],
        A: { hd: [140, 92], hd2: [132, 82], hip: [70, 74], mid: [96, 64], sh: [122, 74], kN: [70, 114], aN: [44, 116], tN: [38, 119], eN: [122, 96], hN: [122, 118] },
        B: { hd: [142, 60], hd2: [134, 66], hip: [70, 80], mid: [96, 88], sh: [122, 80], kN: [70, 114], aN: [44, 116], tN: [38, 119], eN: [122, 98], hN: [122, 118] } },
    },
    seated_twist: {
      name: 'Rotation du buste assis', zone: 'Dos · thorax', secs: 30, sides: 2, where: ['bureau', 'canape'], when: ['anytime'],
      dose: '30 s par côté', level: 'Facile', mode: 'loop', cue: 'Grandis-toi, puis tourne',
      why: "Redonne de la mobilité au haut du dos, qui conditionne le balancement des bras et la respiration en course.",
      steps: ['Assis bien droit au bord de la chaise.', 'Pose une main sur le genou opposé, l\'autre derrière toi sur le dossier.', 'Grandis-toi à l\'inspiration, tourne un peu plus à chaque expiration. Change de côté.'],
      mistakes: ['Se tourner en s\'affaissant.', 'Bloquer la respiration.'],
      fig: { props: '<rect x="70" y="98" width="60" height="6" rx="2" class="ck2-prop"/>' + FLOOR, bones: FRONT,
        A: { hd: [100, 30], sh: [100, 54], shL: [80, 56], shR: [120, 56], hip: [100, 92], eL: [74, 74], hL: [82, 94], eR: [126, 74], hR: [118, 94], kL: [84, 100], aL: [84, 120], kR: [116, 100], aR: [116, 120] },
        B: { hd: [100, 30], sh: [100, 54], shL: [90, 56], shR: [112, 56], hip: [100, 92], eL: [84, 66], hL: [72, 56], eR: [100, 76], hR: [86, 98], kL: [84, 100], aL: [84, 120], kR: [116, 100], aR: [116, 120] } },
    },
    figure4: {
      name: 'Pigeon assis (cheville sur le genou)', zone: 'Fessiers · piriforme', secs: 40, sides: 2, where: ['bureau', 'canape'], when: ['apres', 'anytime'],
      dose: '40 s par côté', level: 'Facile', mode: 'loop', cue: 'Dos plat, penche-toi',
      why: "Détend le fessier profond, souvent crispé chez le coureur qui travaille assis. Se fait sur une simple chaise.",
      steps: ['Assis, pose la cheville droite sur le genou gauche.', 'Garde le dos plat et penche le buste en avant jusqu\'à sentir l\'étirement dans la fesse droite.', 'Tiens 40 secondes. Change de côté.'],
      mistakes: ['Arrondir le dos pour aller plus bas.', 'Forcer sur le genou : il doit rester détendu.'],
      fig: { props: CHAIR, bones: SIDE,
        A: { hd: [94, 44], sh: [92, 60], hip: [96, 92], kN: [124, 94], aN: [126, 118], tN: [138, 119], kF: [118, 82], aF: [128, 90], tF: [136, 92], eN: [104, 72], hN: [112, 82], eF: [102, 74], hF: [114, 86] },
        B: { hd: [114, 56], sh: [110, 68], hip: [96, 92], kN: [124, 94], aN: [126, 118], tN: [138, 119], kF: [118, 82], aF: [128, 90], tF: [136, 92], eN: [122, 82], hN: [130, 88], eF: [120, 84], hF: [128, 92] } },
    },
    supine_ham: {
      name: 'Ischios allongé, jambe levée', zone: 'Arrière de la cuisse', secs: 40, sides: 2, where: ['sol', 'canape'], when: ['apres', 'anytime'],
      dose: '40 s par jambe', level: 'Facile', mode: 'loop', cue: 'Dos au sol, jambe presque tendue',
      why: "Assouplit l\'arrière de la cuisse sans aucun effort. À faire avec une serviette ou une ceinture autour du pied.",
      steps: ['Allongé sur le dos, une jambe tendue au sol.', 'Lève l\'autre jambe et attrape-la derrière la cuisse ou avec une serviette.', 'Rapproche doucement la jambe de toi, genou presque tendu. Tiens 40 secondes.'],
      mistakes: ['Soulever la tête et les épaules.', 'Plier beaucoup le genou : tu perds l\'étirement.'],
      fig: { props: FLOOR,
        bones: [['hd', 'sh', 'b'], ['sh', 'hip', 'b'], ['hip', 'kN', 'n'], ['kN', 'aN', 'n'], ['hip', 'kF', 'f'], ['kF', 'aF', 'f'], ['sh', 'eN', 'n'], ['eN', 'hN', 'n']],
        A: { hd: [26, 114], sh: [40, 114], hip: [88, 114], kN: [118, 114], aN: [148, 114], kF: [96, 88], aF: [108, 62], eN: [64, 96], hN: [98, 80] },
        B: { hd: [26, 114], sh: [40, 114], hip: [88, 114], kN: [118, 114], aN: [148, 114], kF: [90, 88], aF: [82, 62], eN: [60, 96], hN: [88, 80] } },
    },
    butterfly: {
      name: 'Papillon', zone: 'Adducteurs · aine', secs: 45, sides: 1, where: ['sol', 'canape'], when: ['anytime', 'apres'],
      dose: '45 s', level: 'Facile', mode: 'loop', cue: 'Genoux qui tombent doucement',
      why: "Ouvre les adducteurs en douceur, la zone que tu surveilles depuis l\'hiver 2025.",
      steps: ['Assis, plantes des pieds l\'une contre l\'autre, talons près de toi.', 'Dos droit, laisse les genoux tomber vers le sol sans les pousser.', 'Respire, laisse la gravité faire. Si ça tire, rapproche les talons.'],
      mistakes: ['Pousser sur les genoux avec les mains.', 'S\'arrondir pour aller plus bas.'],
      fig: { props: FLOOR,
        bones: [['sh', 'hip', 'b'], ['shL', 'shR', 'n'], ['shL', 'eL', 'n'], ['eL', 'hL', 'n'], ['shR', 'eR', 'n'], ['eR', 'hR', 'n'], ['hip', 'kL', 'n'], ['kL', 'aL', 'n'], ['hip', 'kR', 'n'], ['kR', 'aR', 'n']],
        A: { hd: [100, 40], sh: [100, 56], shL: [84, 58], shR: [116, 58], hip: [100, 104], eL: [76, 86], hL: [92, 112], eR: [124, 86], hR: [108, 112], kL: [64, 96], aL: [94, 116], kR: [136, 96], aR: [106, 116] },
        B: { hd: [100, 42], sh: [100, 58], shL: [84, 60], shR: [116, 60], hip: [100, 104], eL: [74, 90], hL: [92, 112], eR: [126, 90], hR: [108, 112], kL: [60, 110], aL: [94, 116], kR: [140, 110], aR: [106, 116] } },
    },
    windshield: {
      name: 'Essuie-glaces (hanches 90/90)', zone: 'Hanches · rotation', secs: 45, sides: 1, where: ['sol', 'canape'], when: ['anytime'],
      dose: '10 allers-retours', level: 'Facile', mode: 'loop', cue: 'Les genoux basculent ensemble',
      why: "Entretient la rotation de hanche, qui se raidit vite quand on court beaucoup et qu\'on s\'assoit beaucoup.",
      steps: ['Assis au sol, mains en arrière, pieds posés à plat, plus larges que le bassin.', 'Fais basculer les deux genoux vers la gauche, puis vers la droite, comme des essuie-glaces.', 'Reste fluide, sans forcer l\'amplitude.'],
      mistakes: ['Basculer le buste avec les genoux.', 'Forcer vers le sol.'],
      fig: { props: FLOOR,
        bones: [['sh', 'hip', 'b'], ['shL', 'shR', 'n'], ['shL', 'hL', 'n'], ['shR', 'hR', 'n'], ['hip', 'kL', 'n'], ['kL', 'aL', 'n'], ['hip', 'kR', 'n'], ['kR', 'aR', 'n']],
        A: { hd: [100, 44], sh: [100, 60], shL: [88, 62], shR: [112, 62], hip: [100, 100], hL: [76, 104], hR: [124, 104], kL: [66, 100], aL: [70, 118], kR: [94, 92], aR: [130, 118] },
        B: { hd: [100, 44], sh: [100, 60], shL: [88, 62], shR: [112, 62], hip: [100, 100], hL: [76, 104], hR: [124, 104], kL: [106, 92], aL: [70, 118], kR: [134, 100], aR: [130, 118] } },
    },
    foot_ball: {
      name: 'Rouleau de pied (balle)', zone: 'Voûte plantaire · Achille', secs: 40, sides: 2, where: ['bureau', 'canape'], when: ['anytime', 'achille'],
      dose: '40 s par pied', level: 'Facile', mode: 'loop', cue: 'Appui léger, tu roules',
      why: "Détend la voûte plantaire, souvent liée à la tension du tendon d\'Achille. Une balle de tennis suffit.",
      steps: ['Assis, pose une balle de tennis sous le pied.', 'Roule-la lentement de l\'avant-pied jusqu\'au talon, en appui léger.', 'Ralentis sur les points sensibles. Change de pied.'],
      mistakes: ['Appuyer trop fort.', 'Rouler très vite.'],
      fig: { props: CHAIR + '<circle cx="132" cy="115" r="5" class="ck2-prop"/>', bones: SIDE,
        A: { hd: [94, 44], sh: [92, 60], hip: [96, 92], kN: [124, 94], aN: [126, 112], tN: [138, 117], kF: [120, 94], aF: [118, 118], tF: [128, 119], eN: [104, 74], hN: [112, 90], eF: [102, 74], hF: [110, 90] },
        B: { hd: [94, 44], sh: [92, 60], hip: [96, 92], kN: [124, 94], aN: [120, 112], tN: [132, 117], kF: [120, 94], aF: [118, 118], tF: [128, 119], eN: [104, 74], hN: [112, 90], eF: [102, 74], hF: [110, 90] } },
    },
    shoulder_roll: {
      name: 'Épaules et nuque', zone: 'Épaules · nuque', secs: 30, sides: 1, where: ['bureau', 'debout', 'canape'], when: ['anytime'],
      dose: '10 cercles lents', level: 'Facile', mode: 'loop', cue: 'Haut, arrière, bas',
      why: "Relâche les épaules et la nuque en dix secondes. À faire dix fois dans la journée, devant l\'ordinateur ou la télé.",
      steps: ['Assis ou debout, bras relâchés.', 'Monte les épaules vers les oreilles, recule-les, puis laisse-les tomber.', 'Fais des cercles lents, dix fois, puis dans l\'autre sens.'],
      mistakes: ['Faire des cercles trop petits et rapides.', 'Lever le menton.'],
      fig: { props: FLOOR,
        bones: [['sh', 'hip', 'b'], ['shL', 'shR', 'n'], ['shL', 'eL', 'n'], ['eL', 'hL', 'n'], ['shR', 'eR', 'n'], ['eR', 'hR', 'n'], ['hip', 'kL', 'n'], ['kL', 'aL', 'n'], ['hip', 'kR', 'n'], ['kR', 'aR', 'n']],
        A: { hd: [100, 28], sh: [100, 42], shL: [80, 42], shR: [120, 42], hip: [100, 82], eL: [76, 62], hL: [74, 84], eR: [124, 62], hR: [126, 84], kL: [92, 100], aL: [92, 119], kR: [108, 100], aR: [108, 119] },
        B: { hd: [100, 32], sh: [100, 52], shL: [78, 54], shR: [122, 54], hip: [100, 82], eL: [74, 72], hL: [72, 94], eR: [126, 72], hR: [128, 94], kL: [92, 100], aL: [92, 119], kR: [108, 100], aR: [108, 119] } },
    },
  };

  // Enregistre dans le registre commun : le moteur d'animation de cockpit2.js lit EX[id].fig
  Object.keys(M).forEach(id => { EX[id] = Object.assign({ kind: 'mobi' }, M[id]); });

  // ---------------------------------------------------------------- routines
  const WHERE = { bureau: 'Au bureau', canape: 'Canapé / télé', debout: 'Debout', sol: 'Au sol' };
  const ROUT = [
    { id: 'express', name: 'Réveil express', ico: 'timer', tone: 'var(--ck-green)', where: ['bureau', 'debout'], blurb: "3 minutes, n'importe où, pour dérouiller les épaules, le dos et les hanches.", ex: ['shoulder_roll', 'knee_hug', 'seated_twist', 'leg_swing_side'] },
    { id: 'avant', name: 'Avant la sortie', ico: 'run', tone: 'var(--ck-amber)', where: ['debout'], blurb: "Prépare les hanches et les chevilles à la foulée. Dynamique, sans transpirer. À faire juste avant de partir.", ex: ['leg_swing_fb', 'leg_swing_side', 'knee_hug', 'knee_to_wall'] },
    { id: 'bureau', name: 'Pause bureau', ico: 'layers', tone: 'var(--ck-blue)', where: ['bureau'], blurb: "Assis ou debout près de ton poste. Détend le dos, la fesse et le mollet.", ex: ['shoulder_roll', 'seated_twist', 'figure4', 'calf_wall'] },
    { id: 'apres', name: 'Après la sortie', ico: 'heart2', tone: 'var(--ck-red)', where: ['debout', 'sol'], blurb: "Retour au calme : mollets, cuisses et hanches, quand les muscles sont encore chauds.", ex: ['calf_wall', 'quad_stretch', 'lunge_psoas', 'supine_ham'] },
    { id: 'canape', name: 'Canapé / télé', ico: 'play', tone: 'var(--ck-violet)', where: ['canape', 'sol'], blurb: "8 minutes devant un épisode : hanches, adducteurs, ischios, dos et pieds. Le plus efficace sur la durée.", ex: ['windshield', 'butterfly', 'supine_ham', 'lunge_psoas', 'cat_cow', 'foot_ball'] },
    { id: 'achille', name: 'Spécial Achille', ico: 'heart', tone: 'var(--ck-amber)', where: ['bureau', 'debout'], blurb: "Cheville et voûte plantaire, en douceur. Jamais de douleur à l'insertion du tendon : à la moindre tension forte, tu t'arrêtes. À valider avec ton kiné.", ex: ['knee_to_wall', 'calf_wall', 'foot_ball'] },
  ];
  const secsOf = (r) => r.ex.reduce((a, id) => a + EX[id].secs * EX[id].sides + 6, 0);
  const minsOf = (r) => Math.max(3, Math.round(secsOf(r) / 60));

  // ---------------------------------------------------------------- journal
  const LOG = 'runlab.mobi';
  const readLog = () => { try { return JSON.parse(localStorage.getItem(LOG) || '{}'); } catch (e) { return {}; } };
  const writeLog = (o) => { try { localStorage.setItem(LOG, JSON.stringify(o)); } catch (e) {} };
  const isoDaysAgo = (n) => isoLocal(new Date(parse(TODAY).getTime() - n * 864e5));
  function streak() {
    const log = readLog(); let n = 0, i = (log[TODAY] || []).length ? 0 : 1;
    for (; i < 400; i++) { if ((log[isoDaysAgo(i)] || []).length) n++; else break; }
    return n;
  }
  function weekDots() {
    const log = readLog(), out = [];
    for (let i = 6; i >= 0; i--) { const iso = isoDaysAgo(i); out.push({ iso, n: (log[iso] || []).length, today: i === 0 }); }
    return out;
  }
  const hasBoth = (a) => a.length >= 2;

  // ---------------------------------------------------------------- suggestion du jour
  function suggest() {
    const h = new Date().getHours();
    const day = allDays().find(d => d.date === TODAY);
    const log = readLog()[TODAY] || [];
    const run = day && day.type !== 'rest' && day.km > 0;
    const done = day && day.actual;
    const time = day && day.scheduled_time;
    const sess = day ? day.title : '';
    if (run && !done && !log.includes('avant')) {
      return { id: 'avant', why: `Séance prévue${time ? ' à ' + time : ' aujourd\'hui'} : « ${sess} ». 4 minutes avant de partir.` };
    }
    if (done && !log.includes('apres')) return { id: 'apres', why: 'Séance faite : étire-toi tant que les muscles sont chauds.' };
    if (h >= 18 && !log.includes('canape')) return { id: 'canape', why: 'Ce soir, devant un épisode : 8 minutes qui changent beaucoup de choses.' };
    if (h < 12 && !log.includes('express')) return { id: 'express', why: 'Pour bien démarrer la journée : 3 minutes, n\'importe où.' };
    if (!log.includes('bureau')) return { id: 'bureau', why: 'Pause bureau : dos, fesse et mollet en 4 minutes.' };
    return { id: 'canape', why: 'Déjà bien fait aujourd\'hui. Une dernière pour la forme ?', done: true };
  }

  // ---------------------------------------------------------------- vues
  const dotsHtml = () => `<div class="ck3-dots">${weekDots().map(d => `<span class="ck3-dot${d.n ? ' on' : ''}${d.today ? ' today' : ''}" title="${esc(fmtDay(d.iso))}">${['D', 'L', 'M', 'M', 'J', 'V', 'S'][parse(d.iso).getDay()]}</span>`).join('')}</div>`;

  function renderHome() {
    const host = $('#ckMobi');
    if (!host) return;
    const s = suggest(), r = ROUT.find(x => x.id === s.id), st = streak();
    host.innerHTML = `<section class="ck-card ck3-home" style="--c:${r.tone}">
      <div class="ck-card-h"><h3>Mobilité du jour</h3><span>${st ? st + ' jour' + (st > 1 ? 's' : '') + ' de suite' : '3 à 10 min'}</span></div>
      <div class="ck3-sugg">
        <div class="ck3-sugg-ico">${svg(r.ico, 22)}</div>
        <div class="ck3-sugg-main"><b>${esc(r.name)} · ${minsOf(r)} min</b><span>${esc(s.why)}</span></div>
      </div>
      ${dotsHtml()}
      <div class="ck-actions"><button type="button" class="ck-btn ck-btn-primary" data-guide="${r.id}">${svg('play', 16)} Démarrer</button>
        <button type="button" class="ck-btn" data-goto-corps>Toutes les routines</button></div>
    </section>`;
  }

  function renderPane(host) {
    const s = suggest();
    host.innerHTML = `
      <div class="ck2-hero ck3-hero">
        <div class="ck2-hero-k">Mobilité</div>
        <p class="ck2-hero-t">3 à 10 minutes, sans transpirer. Au bureau, sur le canapé, avant la sortie. Chaque exercice a sa démonstration animée.</p>
        ${dotsHtml()}
      </div>
      <div class="ck3-now">
        <div class="ck3-now-k">Pour toi, maintenant</div>
        <div class="ck3-now-t">${esc(ROUT.find(r => r.id === s.id).name)}</div>
        <p>${esc(s.why)}</p>
        <button type="button" class="ck-btn ck-btn-primary" data-guide="${s.id}">${svg('play', 16)} Démarrer</button>
      </div>
      <div class="ck2-routines">${ROUT.map(r => `
        <div class="ck3-routine" style="--c:${r.tone}">
          <button type="button" class="ck2-routine" data-routine-m="${r.id}" style="--c:${r.tone}">
            <div class="ck2-routine-ico">${svg(r.ico, 22)}</div>
            <div class="ck2-routine-main"><b>${esc(r.name)}</b><span>${minsOf(r)} min · ${r.ex.length} exercices</span>
              <div class="ck3-tags">${r.where.map(w => `<i>${esc(WHERE[w])}</i>`).join('')}</div></div>
            ${svg('chevR', 18)}
          </button>
          <button type="button" class="ck3-play" data-guide="${r.id}" aria-label="Démarrer ${esc(r.name)}">${svg('play', 18)}</button>
        </div>`).join('')}</div>
      <div class="ck-card-h ck2-lib-h"><h3>Tous les exercices</h3><span>${Object.keys(M).length}</span></div>
      <div class="ck2-lib">${Object.keys(M).map(id => `<button type="button" class="ck2-ex" data-mx="${id}">${figHtml(id, 'ck2-fig-sm')}<b>${esc(EX[id].name)}</b><span>${esc(EX[id].zone)}</span></button>`).join('')}</div>`;
    startFigs(host);
  }

  function openMx(id) {
    const e = EX[id]; if (!e) return;
    const body = openSheet(`
      <span class="ck-sheet-tag" style="--c:var(--ck-green)">${svg('leaf', 14)} ${esc(e.zone)}</span>
      <h3 class="ck-sheet-h">${esc(e.name)}</h3>
      <div class="ck2-demo">${figHtml(id, 'ck2-fig-lg')}<div class="ck2-cue">${esc(e.cue || '')}</div></div>
      <div class="ck-facts">
        <div><span>Durée</span><b>${esc(e.dose)}</b></div>
        <div><span>Où</span><b>${esc(e.where.map(w => WHERE[w]).join(' · '))}</b></div>
        <div><span>Niveau</span><b>${esc(e.level)}</b></div>
      </div>
      <div class="ck-sheet-sec"><h4>Pourquoi, pour courir</h4><p>${esc(e.why)}</p></div>
      <div class="ck-sheet-sec"><h4>Comment faire</h4><ol class="ck2-steps">${e.steps.map(x => `<li>${esc(x)}</li>`).join('')}</ol></div>
      <div class="ck-sheet-sec"><h4>À éviter</h4><ul class="ck2-mistakes">${e.mistakes.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
      ${e.when.includes('achille') ? '<p class="ck2-warn-s">Tendon d\'Achille : un étirement doux, jamais de douleur dans le talon. À valider avec ton kiné.</p>' : ''}`);
    startFigs(body);
  }

  function openRoutine(id) {
    const r = ROUT.find(x => x.id === id); if (!r) return;
    const body = openSheet(`
      <span class="ck-sheet-tag" style="--c:${r.tone}">${svg(r.ico, 14)} ${minsOf(r)} min · ${r.ex.length} exercices</span>
      <h3 class="ck-sheet-h">${esc(r.name)}</h3>
      <p class="ck-muted">${esc(r.blurb)}</p>
      <div class="ck2-rlist">${r.ex.map((x, i) => `<button type="button" class="ck2-rex" data-mx="${x}">
        <span class="ck2-rex-n">${i + 1}</span>${figHtml(x, 'ck2-fig-xs')}
        <div><b>${esc(EX[x].name)}</b><span>${EX[x].secs} s${EX[x].sides === 2 ? ' par côté' : ''}</span></div></button>`).join('')}</div>
      <div class="ck-actions"><button class="ck-btn ck-btn-primary" data-guide="${r.id}" type="button">${svg('play', 16)} Démarrer le mode guidé</button></div>`);
    startFigs(body);
  }

  // ---------------------------------------------------------------- mode guidé
  function vibrate(ms) { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) {} }
  function openGuide(id) {
    const r = ROUT.find(x => x.id === id); if (!r) return;
    const steps = [];
    r.ex.forEach((x, i) => { for (let s = 0; s < EX[x].sides; s++) steps.push({ id: x, side: EX[x].sides === 2 ? (s === 0 ? 'Côté droit' : 'Côté gauche') : '', secs: EX[x].secs, exIndex: i }); });
    let cur = 0, left = steps[0].secs, paused = false, ended = false;
    const body = openSheet('<div class="ck3-guide" id="ck3Guide"></div>');
    const root = $('#ck3Guide', body);

    function draw() {
      const s = steps[cur], e = EX[s.id];
      const total = steps.reduce((a, x) => a + x.secs, 0), doneS = steps.slice(0, cur).reduce((a, x) => a + x.secs, 0) + (s.secs - left);
      root.innerHTML = `
        <div class="ck3-g-head"><span>${esc(r.name)}</span><span>${cur + 1} / ${steps.length}</span></div>
        <div class="ck-bar ck3-g-bar"><i style="width:${Math.round(doneS / total * 100)}%"></i></div>
        <div class="ck2-demo">${figHtml(s.id, 'ck2-fig-lg')}</div>
        <h3 class="ck3-g-name">${esc(e.name)}</h3>
        ${s.side ? `<div class="ck3-g-side">${esc(s.side)}</div>` : '<div class="ck3-g-side ck3-g-side-none">&nbsp;</div>'}
        <div class="ck3-g-time" aria-live="off">${left}<small>s</small></div>
        <p class="ck3-g-cue">${esc(e.cue || '')}</p>
        <div class="ck-actions ck3-g-actions">
          <button type="button" class="ck-btn" data-g="pause">${paused ? 'Reprendre' : 'Pause'}</button>
          <button type="button" class="ck-btn" data-g="skip">Passer</button>
          <button type="button" class="ck-btn" data-g="quit">Quitter</button>
        </div>`;
      startFigs(root);
    }
    function finish() {
      ended = true;
      const log = readLog(); log[TODAY] = log[TODAY] || []; if (!log[TODAY].includes(r.id)) log[TODAY].push(r.id); writeLog(log);
      vibrate([60, 40, 60]);
      root.innerHTML = `<div class="ck3-g-end"><div class="ck3-g-end-ico">${svg('check', 34)}</div><h3>Bien joué</h3>
        <p>${esc(r.name)} terminée${streak() > 1 ? ' · ' + streak() + ' jours de suite' : ''}.</p>${dotsHtml()}
        <div class="ck-actions"><button type="button" class="ck-btn ck-btn-primary" data-g="close">Terminer</button></div></div>`;
      renderHome(); const pane = $('#ckMobiPane'); if (pane) renderPane(pane);
    }
    function next() { cur++; if (cur >= steps.length) { finish(); return; } left = steps[cur].secs; vibrate(40); draw(); }
    const tick = setInterval(() => {
      const bk = $('.ck-sheet-bk');
      if (!root.isConnected || !bk || bk.hidden) { clearInterval(tick); return; }
      if (paused || ended) return;
      left--;
      if (left <= 0) { next(); return; }
      const t = $('.ck3-g-time', root); if (t) t.firstChild.nodeValue = left;
      const b = $('.ck3-g-bar > i', root);
      if (b) { const total = steps.reduce((a, x) => a + x.secs, 0), d = steps.slice(0, cur).reduce((a, x) => a + x.secs, 0) + (steps[cur].secs - left); b.style.width = Math.round(d / total * 100) + '%'; }
    }, 1000);
    root.addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-g]'); if (!b) return;
      const a = b.dataset.g;
      if (a === 'pause') { paused = !paused; b.textContent = paused ? 'Reprendre' : 'Pause'; }
      else if (a === 'skip') next();
      else if (a === 'quit' || a === 'close') { clearInterval(tick); closeSheet(); }
    });
    draw();
  }

  // ---------------------------------------------------------------- onglet Corps : Mobilité | Renfo
  function mountCorps() {
    const root = $('#t-renfo'); if (!root || $('#ckSeg')) return;
    const renfo = $('.ck2-renfo', root);
    const seg = document.createElement('div');
    seg.id = 'ckSeg'; seg.className = 'ck3-seg';
    seg.innerHTML = '<button type="button" data-seg="mobi" class="on">Mobilité</button><button type="button" data-seg="renfo">Renfo</button>';
    const paneM = document.createElement('div'); paneM.id = 'ckMobiPane'; paneM.className = 'ck3-pane on';
    const paneR = document.createElement('div'); paneR.id = 'ckRenfoPane'; paneR.className = 'ck3-pane';
    root.innerHTML = '';
    root.appendChild(seg); root.appendChild(paneM); root.appendChild(paneR);
    if (renfo) paneR.appendChild(renfo);
    renderPane(paneM);
    seg.addEventListener('click', (e) => {
      const b = e.target.closest('[data-seg]'); if (!b) return;
      $$('button', seg).forEach(x => x.classList.toggle('on', x === b));
      paneM.classList.toggle('on', b.dataset.seg === 'mobi'); paneR.classList.toggle('on', b.dataset.seg === 'renfo');
      if (b.dataset.seg === 'renfo') startFigs(paneR);
    });
  }

  function mount() {
    const rec = $('#ckRecos');
    if (rec && !$('#ckMobi')) rec.insertAdjacentHTML('beforebegin', '<div id="ckMobi"></div>');
    renderHome();
    mountCorps();
    document.addEventListener('click', (e) => {
      const t = e.target;
      const g = t.closest('[data-guide]'); if (g) { openGuide(g.dataset.guide); return; }
      const rt = t.closest('[data-routine-m]'); if (rt) { openRoutine(rt.dataset.routineM); return; }
      const mx = t.closest('[data-mx]'); if (mx) { openMx(mx.dataset.mx); return; }
      if (t.closest('[data-goto-corps]')) { const b = $('.tab[data-tab="renfo"]'); if (b) b.click(); const s = $('#ckSeg [data-seg="mobi"]'); if (s) s.click(); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(mount, 30));
  else setTimeout(mount, 30);
})();
