"""0.9.4 : l'ouverture de la caméra ne reste plus jamais bloquée sur « Préparation de la caméra… ».
Caméra simulée de Chromium (mire, sans fichier). Passé si Playwright ou Chromium manquent."""
from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")
from tests.test_ecran import adresse  # noqa: F401,E402  (serveur de démonstration partagé)

STATUTS_OK = ("Cherche un tirage", "Chargement de la détection", "Tirage détecté", "Pose le tirage", "Trop loin")


def _page(p, adresse, avant: str = ""):
    try:
        b = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Chromium absent : {e}")
    ctx = b.new_context(viewport={"width": 390, "height": 844}, permissions=["camera"])
    if avant:
        ctx.add_init_script(avant)
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.goto(adresse + "/?essai")
    page.fill("#mot-de-passe", "demonstration-12")
    page.click("text=Se connecter")
    page.wait_for_selector("h1:has-text('Scanner')")
    page.evaluate("Object.assign(window.__reglagesCamera, {delaiAutorisation: 2500, delaiReglage: 500, delaiImage: 2500})")
    return b, page, erreurs


def _statut_ok(page, delai=60000):
    page.wait_for_function(
        f"(() => {{ const s = document.querySelector('[role=status]'); return s && {list(STATUTS_OK)!r}.some(x => s.textContent.includes(x)) }})()",
        timeout=delai)
    return page.text_content("[role=status]")


def test_ouverture_normale(adresse):
    with pw.sync_playwright() as p:
        b, page, erreurs = _page(p, adresse)
        page.click("text=Rafale")
        statut = _statut_ok(page)
        vivante = page.evaluate("document.querySelector('video').videoWidth > 0")
        b.close()
    assert not erreurs, erreurs
    assert vivante, statut


def test_image_noire_au_premier_essai_puis_reprise(adresse):
    # la première lecture de la vidéo ne répond jamais (comme sur l'iPhone) : second essai sans ajustement
    avant = """(() => { const play = HTMLMediaElement.prototype.play; let n = 0;
        HTMLMediaElement.prototype.play = function () { n++; if (n === 1) return new Promise(() => {}); return play.call(this) } })()"""
    with pw.sync_playwright() as p:
        b, page, erreurs = _page(p, adresse, avant)
        page.click("text=1 photo")
        statut = _statut_ok(page)
        pistes = page.evaluate("document.querySelector('video').srcObject.getVideoTracks().filter(t => t.readyState === 'live').length")
        b.close()
    assert not erreurs, erreurs
    assert pistes == 1, statut


def test_camera_muette_message_au_lieu_d_attendre(adresse):
    # getUserMedia ne répond jamais : un message clair apparaît, la caméra se ferme
    avant = "navigator.mediaDevices.getUserMedia = () => new Promise(() => {})"
    with pw.sync_playwright() as p:
        b, page, erreurs = _page(p, adresse, avant)
        page.click("text=Rafale")
        page.wait_for_selector("text=Caméra inaccessible", timeout=20000)
        ouverte = page.locator("[role=dialog][aria-label=Caméra]").count()
        b.close()
    assert not erreurs, erreurs
    assert ouverte == 0


def test_retour_au_premier_plan_une_seule_camera(adresse):
    # va-et-vient arrière-plan pendant l'ouverture : une seule caméra allumée à la fin
    with pw.sync_playwright() as p:
        b, page, erreurs = _page(p, adresse)
        page.evaluate("""() => { window.__pistes = []; const gum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            navigator.mediaDevices.getUserMedia = async (c) => { const f = await gum(c); window.__pistes.push(...f.getTracks()); return f } }""")
        page.click("text=Rafale")
        page.evaluate("""() => { const d = (h) => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => h});
            document.dispatchEvent(new Event('visibilitychange')) }; d(true); d(false); d(true); d(false) }""")
        _statut_ok(page)
        page.wait_for_timeout(1500)
        vivantes = page.evaluate("window.__pistes.filter(t => t.readyState === 'live').length")
        b.close()
    assert not erreurs, erreurs
    assert vivantes == 1
