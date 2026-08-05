#!/usr/bin/env python3
"""Contrôle du dashboard en conditions iPhone 17 Pro, iPhone SE et desktop : erreurs console, hauteur de
l'accueil sans défilement, bascule des quatre onglets et des sept lentilles."""
import sys
import pathlib
import os
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = "file://%s/output/index.html" % ROOT

os.makedirs(str(ROOT / "output" / "captures"), exist_ok=True)
OUT = str(ROOT / "output" / "captures")

# Débordement horizontal : un élément qui dépasse la largeur de l'écran sans
# vivre dans un conteneur défilant. C'est ce qui coupe une valeur à droite.
SCAN_DEBORDE = """() => {
  const W = innerWidth, out = [];
  document.querySelectorAll('.tab-content.on *, .lens-panel.on *').forEach(e => {
    const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || r.right <= W + 1) return;
    let p = e.parentElement;
    while (p && p !== document.body) {
      const o = getComputedStyle(p).overflowX;
      if (o === 'auto' || o === 'scroll') return;
      p = p.parentElement;
    }
    out.push(e.tagName + '.' +
             (typeof e.className === 'string' ? e.className.split(' ')[0] : 'svg') +
             ' (+' + Math.round(r.right - W) + 'px)');
  });
  return [...new Set(out)].slice(0, 5);
}"""

errors, fails = [], []

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 402, "height": 874},
                        device_scale_factor=3, is_mobile=True,
                        has_touch=True, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
    # Le bac à sable n'a pas de réseau : ECharts vient d'un CDN. On le
    # remplace par une doublure pour que le reste de la page s'initialise —
    # ce qu'on vérifie ici, c'est la navigation, pas le tracé des courbes.
    ECHARTS_STUB = """
      window.echarts = {
        init(el) {
          if (el) el.dataset.chartStub = '1';
          return {setOption(){}, resize(){}, dispose(){}, on(){}, off(){},
                  getZr(){return {on(){}, off(){}};}, clear(){},
                  getWidth(){return 300;}, getHeight(){return 200;}};
        }
      };
    """
    ctx.add_init_script(ECHARTS_STUB)
    ctx.route("**/echarts*.js", lambda r: r.fulfill(status=200,
              content_type="application/javascript", body="/* stub */"))

    pg = ctx.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append("PAGEERROR " + str(e)))
    pg.goto(URL)
    pg.wait_for_timeout(3500)

    # Le bac à sable n'a pas de réseau : l'échec de chargement du CDN ECharts
    # n'est pas un défaut de l'app. Tout le reste compte.
    # `navigator.vibrate` est refusé tant que rien n'a été touché : c'est une
    # politique du navigateur, pas un défaut. Safari iOS ne l'implémente même
    # pas — le retour haptique y est simplement absent.
    IGNORE = ("ERR_EMPTY_RESPONSE", "ERR_INTERNET_DISCONNECTED",
              "ERR_NAME_NOT_RESOLVED", "net::ERR_FAILED",
              "navigator.vibrate")
    reels = [e for e in errors if not any(i in e for i in IGNORE)]

    print("=== erreurs console ===")
    print("\n".join(reels[:12]) if reels else "aucune")
    if len(errors) != len(reels):
        print("  (%d message(s) réseau ignoré(s) : pas de sortie internet ici)"
              % (len(errors) - len(reels)))
    if reels:
        fails.append("%d erreur(s) console" % len(reels))

    # --- accueil : ce qui tient au-dessus du pli
    vp = 844
    info = pg.evaluate("""() => {
      const r = e => e ? e.getBoundingClientRect() : null;
      const route = r(document.getElementById('homeRoute'));
      const ans   = r(document.getElementById('homeAnswers'));
      const tabs  = r(document.querySelector('.tabs'));
      return {
        routeBottom: route ? route.bottom : null,
        ansBottom:   ans ? ans.bottom : null,
        tabsTop:     tabs ? tabs.top : null,
        answers:     document.querySelectorAll('.answer').length,
        scrollH:     document.documentElement.scrollHeight,
      };
    }""")
    print("\n=== accueil (iPhone 17 Pro, 402x874) ===")
    for k, v in info.items():
        print("  %-12s %s" % (k, round(v, 1) if isinstance(v, float) else v))

    if info["ansBottom"] is None:
        fails.append("bloc des trois réponses absent")
    elif info["tabsTop"] and info["ansBottom"] > info["tabsTop"]:
        fails.append("les trois réponses passent sous la barre d'onglets "
                     "(%.0f > %.0f)" % (info["ansBottom"], info["tabsTop"]))
    if info["answers"] != 3:
        fails.append("attendu 3 tuiles réponse, trouvé %s" % info["answers"])

    # La bascule de thème doit rester en haut, hors de la barre d'onglets
    th = pg.evaluate("""() => {
      const t = document.getElementById('themeToggle');
      if (!t) return null;
      const r = t.getBoundingClientRect();
      const tabs = document.querySelector('.tabs').getBoundingClientRect();
      return {top: Math.round(r.top), inTabs: r.top >= tabs.top,
              isTab: !!t.closest('.tabs'),
              tabCount: document.querySelectorAll('.tabs .tab[data-tab]').length};
    }""")
    print("\nbascule de thème : haut =", th["top"], "| dans la barre :",
          th["inTabs"] or th["isTab"], "| onglets réels :", th["tabCount"])
    if th["inTabs"] or th["isTab"]:
        fails.append("la bascule de thème se lit comme un onglet")
    if th["tabCount"] != 4:
        fails.append("attendu 4 onglets, trouvé %s" % th["tabCount"])

    pg.screenshot(path=OUT + "/01-accueil.png")

    # --- en-tête : condensé au défilement, et resté collé en haut
    # (mouse.wheel ne défile pas en émulation tactile : on pilote le scroll)
    pg.evaluate("() => window.scrollTo(0, 500)")
    pg.wait_for_timeout(800)
    st = pg.evaluate("""() => ({
      scrolled: document.body.classList.contains('is-scrolled'),
      heroTop: Math.round(document.querySelector('.hero').getBoundingClientRect().top),
      heroH: Math.round(document.querySelector('.hero').getBoundingClientRect().height),
    })""")
    print("\nen-tête condensé :", st["scrolled"],
          "| collé en haut : top =", st["heroTop"], "| hauteur =", st["heroH"])
    if not st["scrolled"]:
        fails.append("l'en-tête ne se condense pas au défilement")
    if st["heroTop"] < -2:
        fails.append("l'en-tête ne reste pas collé en haut (top=%s)" % st["heroTop"])
    pg.screenshot(path=OUT + "/02-accueil-defile.png")
    pg.evaluate("() => window.scrollTo(0,0)")
    pg.wait_for_timeout(500)

    # --- quatre onglets
    print("\n=== onglets ===")
    for tab, shot in [("plan", "03-plan"), ("sess", "04-seances"), ("race", "05-courses")]:
        pg.click(f'.tab[data-tab="{tab}"]')
        pg.wait_for_timeout(1100)
        on = pg.evaluate(f"() => document.getElementById('t-{tab}').classList.contains('on')")
        h = pg.evaluate(f"() => document.getElementById('t-{tab}').getBoundingClientRect().height")
        print("  %-6s actif=%s hauteur=%.0f" % (tab, on, h))
        if not on:
            fails.append("l'onglet %s ne s'active pas" % tab)
        if h < 200:
            fails.append("l'onglet %s est vide (hauteur %.0f)" % (tab, h))
        deb = pg.evaluate(SCAN_DEBORDE)
        if deb:
            print("         déborde : " + ", ".join(deb))
            fails.append("onglet %s : déborde à droite (%s)" % (tab, deb[0]))
        pg.screenshot(path=f"{OUT}/{shot}.png")

    # --- sept lentilles
    pg.click('.tab[data-tab="sess"]')
    pg.wait_for_timeout(600)
    print("\n=== lentilles ===")
    for lens in ["drift", "balance", "charge", "effic", "vol", "prog", "list"]:
        pg.click(f'.lens[data-lens="{lens}"]')
        pg.wait_for_timeout(900)
        st = pg.evaluate(f"""() => {{
          const p = document.getElementById('l-{lens}');
          return {{on: p.classList.contains('on'), h: p.getBoundingClientRect().height,
                   others: [...document.querySelectorAll('.lens-panel.on')].length}};
        }}""")
        print("  %-8s actif=%s hauteur=%-6.0f panneaux visibles=%s"
              % (lens, st["on"], st["h"], st["others"]))
        if not st["on"]:
            fails.append("la lentille %s ne s'active pas" % lens)
        if st["others"] != 1:
            fails.append("%s panneaux visibles sur la lentille %s" % (st["others"], lens))
        if st["h"] < 150:
            fails.append("la lentille %s est vide (hauteur %.0f)" % (lens, st["h"]))
        deb = pg.evaluate(SCAN_DEBORDE)
        if deb:
            print("           déborde : " + ", ".join(deb))
            fails.append("lentille %s : déborde à droite (%s)" % (lens, deb[0]))
        if lens in ("charge", "vol", "prog", "effic"):
            pg.screenshot(path=f"{OUT}/06-lentille-{lens}.png")

    # --- desktop : coup d'œil large
    # --- iPhone SE : le petit écran est le vrai juge de « un écran »
    ctxSE = b.new_context(viewport={"width": 375, "height": 667},
                          is_mobile=True, has_touch=True)
    ctxSE.add_init_script(ECHARTS_STUB)
    pgSE = ctxSE.new_page()
    pgSE.on("pageerror", lambda e: errors.append("SE " + str(e)))
    pgSE.goto(URL)
    pgSE.wait_for_timeout(3000)
    se = pgSE.evaluate("""() => ({
      ansBottom: document.getElementById('homeAnswers').getBoundingClientRect().bottom,
      tabsTop: document.querySelector('.tabs').getBoundingClientRect().top,
    })""")
    print("\n=== iPhone SE (375x667) ===")
    print("  bas des réponses %.0f · haut des onglets %.0f · marge %.0f"
          % (se["ansBottom"], se["tabsTop"], se["tabsTop"] - se["ansBottom"]))
    if se["ansBottom"] > se["tabsTop"]:
        fails.append("SE : les trois réponses passent sous la barre d'onglets "
                     "(%.0f > %.0f)" % (se["ansBottom"], se["tabsTop"]))
    pgSE.screenshot(path=OUT + "/09-iphone-se.png")

    ctx2 = b.new_context(viewport={"width": 1440, "height": 900})
    ctx2.add_init_script(ECHARTS_STUB)
    pg2 = ctx2.new_page()
    pg2.on("pageerror", lambda e: errors.append("DESKTOP " + str(e)))
    pg2.goto(URL)
    pg2.wait_for_timeout(3000)
    pg2.screenshot(path=OUT + "/07-desktop-accueil.png")
    pg2.click('.tab[data-tab="sess"]')
    pg2.wait_for_timeout(1200)
    pg2.screenshot(path=OUT + "/08-desktop-seances.png")

    b.close()

print("\n" + "=" * 46)
if fails:
    print("ANOMALIES :")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("Aucune anomalie.")
