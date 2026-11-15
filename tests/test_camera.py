"""Caméra simulée (fichiers .y4m de Scan Immich) : la prise automatique fonctionne dans les trois modes et
les prises arrivent sur le NAS. Passé si Playwright ou les fichiers de caméra manquent."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
from tests.test_ecran import adresse  # noqa: F401,E402  (serveur de démonstration partagé)

CAMERAS = Path(os.environ.get("CN_CAMERAS", "/home/claude/e2e"))
pytestmark = pytest.mark.skipif(not (CAMERAS / "cam3.y4m").is_file(), reason="fichiers de caméra simulée absents")


def _ouvrir(p, fichier, adresse):
    b = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                f"--use-file-for-fake-video-capture={CAMERAS / fichier}"])
    ctx = b.new_context(viewport={"width": 390, "height": 844}, permissions=["camera"])
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.goto(adresse + "/?essai")
    page.fill("#mot-de-passe", "demonstration-12")
    page.click("text=Se connecter")
    page.wait_for_selector("h1:has-text('Scanner')")
    page.evaluate("Object.assign(window.__reglagesCamera, {minPx: 1000, minPxPage: 400})")   # caméras simulées en 1440 px
    return b, page, erreurs


def _sante(page):
    return page.evaluate("fetch('/health').then(r => r.json()).then(j => j.en_attente)")


def _attendre(page, condition, delai=90):
    """Interroge le NAS chaque seconde jusqu'à ce que condition(en_attente) soit vraie."""
    import time
    fin = time.time() + delai
    while time.time() < fin:
        if condition(_sante(page)):
            return
        page.wait_for_timeout(1000)
    raise AssertionError(f"délai dépassé, en attente sur le NAS : {_sante(page)}")


def test_rafale_prise_automatique(adresse):
    with pw.sync_playwright() as p:
        b, page, erreurs = _ouvrir(p, "cam3.y4m", adresse)
        depart = _sante(page)
        page.evaluate("""() => { window.__flashs = 0; new MutationObserver(m => m.forEach(x => {
            if (x.target.dataset && x.target.dataset.flash === 'oui') window.__flashs++ })).observe(document.body,
            {subtree: true, attributes: true, attributeFilter: ['data-flash']}) }""")
        page.click("text=Rafale")
        _attendre(page, lambda n: n > depart)
        page.wait_for_function("window.__fileEnvoi.etat.surIphone === 0", timeout=30000)
        statut = page.text_content("[role=status]")
        flashs = page.evaluate("window.__flashs")
        page.click("text=Terminer")
        page.wait_for_selector("h1:has-text('À traiter')")
        page.wait_for_selector("text=Rafale du")
        # l'image reçue est le tirage redressé, en pleine définition
        taille = page.evaluate("""async () => {
            const s = (await (await fetch('/api/sections')).json()).sections[0];
            const p = (await (await fetch('/api/sections/' + s.id + '/prises')).json()).prises[0];
            const img = new Image(); img.src = '/api/prises/' + p.id + '/rendu.jpg'; await img.decode();
            return [img.naturalWidth, img.naturalHeight, p.taille_source > 0];
        }""")
        # étape 4 : revue, rotation, date, envoi, puis Annuler depuis le journal
        page.locator("button", has_text="Rafale du").first.click()
        page.wait_for_selector("text=à dater")
        page.get_by_label("Tourner à droite").first.click()
        page.select_option("select[aria-label=Mois]", "5")
        page.fill("input[aria-label=Année]", "1987")
        page.wait_for_selector("text=1987-05 Numérisation Démo")
        page.click("text=Dater et envoyer")
        page.wait_for_selector("text=Rien à traiter", timeout=30000)
        page.goto(adresse + "/?essai#/reglages")
        page.wait_for_selector("text=1987-05 Numérisation Démo")
        page.click("text=Annuler l’envoi")
        page.click("text=Confirmer")
        page.wait_for_selector("text=à la corbeille d’Immich. Elles", timeout=15000)
        large = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        b.close()
    assert not erreurs, erreurs
    assert not large
    assert "change de tirage" in statut or "Pose" in statut or "Prise" in statut
    assert max(taille[:2]) >= 1000 and taille[2]
    assert flashs >= 1, "pas de flash à la prise automatique"


def test_page_d_album_quatre_tirages(adresse):
    if not (CAMERAS / "cam4.y4m").is_file():
        pytest.skip("cam4.y4m absent")
    with pw.sync_playwright() as p:
        b, page, erreurs = _ouvrir(p, "cam4.y4m", adresse)
        depart = _sante(page)
        page.click("text=Page d’album")
        _attendre(page, lambda n: n >= depart + 4)
        page.wait_for_function("window.__fileEnvoi.etat.surIphone === 0", timeout=30000)
        n = page.evaluate("""async () => {
            const s = (await (await fetch('/api/sections')).json()).sections.find(x => x.mode === 'page');
            return s.prises;
        }""")
        b.close()
    assert not erreurs, erreurs
    assert n == 4
