"""Tests d'écran sur PC et sur iPhone, par le serveur de démonstration (tools/demo.py).
Passés si Playwright n'est pas installé (CI de l'API) ; à lancer en local avant chaque livraison."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
RACINE = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (RACINE / "app/static/index.html").is_file(), reason="interface non compilée")


@pytest.fixture(scope="module")
def adresse():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = dict(os.environ, DEMO_PORT=str(port), DEMO_PERMISSIONS="manque")
    proc = subprocess.Popen([sys.executable, "-m", "tools.demo"], cwd=RACINE, env=env)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()


@pytest.mark.parametrize("taille", [(1280, 800), (390, 844)], ids=["pc", "iphone"])
def test_parcours(adresse, taille):
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": taille[0], "height": taille[1]})
        erreurs = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.goto(adresse)
        page.fill("#mot-de-passe", "demonstration-12")
        page.click("text=Se connecter")
        page.wait_for_selector("h1:has-text('Scanner')")
        page.goto(adresse + "/#/connexion")
        page.wait_for_selector("h1:has-text('Connexion')")
        # 0.9.0 : écran commun (3 services : fiches dépliées) ; Vérifier sur Immich, permissions dans le guide
        immich = page.get_by_role("article", name="Immich", exact=True)
        immich.get_by_role("button", name="Vérifier").click()
        immich.get_by_text("1 permission manquante à la clé").click()
        page.wait_for_selector("text=queue.update ou job.create")
        page.get_by_role("article", name="Millésime").get_by_role("heading", name="Millésime").wait_for()
        page.goto(adresse + "/#/reglages")
        page.fill("input[placeholder='Numérisation …']", f"Numérisation Écran {taille[0]}")
        page.click("text=Enregistrer")
        page.wait_for_selector("text=utilisé dès le prochain envoi")
        page.wait_for_selector(f"text=Numérisation Écran {taille[0]}/1987-05")
        # 0.7.0 : Restaurer les réglages (faux Anneau de tools/demo.py)
        restaurer = page.get_by_role("region", name="Restaurer les réglages")
        restaurer.locator("select").select_option("2026-11-15")
        restaurer.get_by_text("Numérisation Sauvée").wait_for()
        restaurer.get_by_role("button", name="Restaurer ces réglages").click()
        restaurer.get_by_role("button", name="Confirmer la restauration").click()
        restaurer.get_by_text("Réglages restaurés depuis la sauvegarde").wait_for()
        assert page.input_value("input[placeholder='Numérisation …']") == "Numérisation Sauvée"
        page.get_by_role("region", name="Journal", exact=True).get_by_text("Réglages restaurés (sauvegarde du").first.wait_for()
        from app import __version__
        page.wait_for_selector(f"text=Chambre noire {__version__}")
        large = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        b.close()
    assert not erreurs, erreurs
    assert not large, "débordement horizontal"


def _jpeg(page):
    """Ajoute à la file une prise faite d'une vraie image JPEG (canvas)."""
    return page.evaluate("""async () => {
        const c = document.createElement('canvas'); c.width = 64; c.height = 48;
        const x = c.getContext('2d'); x.fillStyle = '#4fc1c9'; x.fillRect(0, 0, 64, 48);
        const b = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.9));
        return window.__fileEnvoi.ajouter({section: 'section-essai-01', mode: 'rafale', ordre: Date.now() % 1000}, b, b);
    }""")


def test_file_d_envoi_ne_perd_rien(adresse):
    """Prise faite hors ligne → gardée sur l'iPhone, même après fermeture ; repart au retour du réseau.
    Session expirée → la file attend la connexion puis repart."""
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        erreurs = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.goto(adresse + "/?essai")
        page.fill("#mot-de-passe", "demonstration-12")
        page.click("text=Se connecter")
        page.wait_for_selector("h1:has-text('Scanner')")
        sante = lambda: page.evaluate("fetch('/health').then(r => r.json()).then(j => j.en_attente)")
        depart = sante()

        # 1. en ligne : reçue tout de suite, effacée de l'iPhone
        _jpeg(page)
        page.wait_for_function("window.__fileEnvoi.etat.surIphone === 0")
        assert sante() == depart + 1

        # 2. hors ligne : gardée, et toujours là après fermeture de l'appli
        ctx.set_offline(True)
        _jpeg(page)
        page.wait_for_function("window.__fileEnvoi.etat.surIphone === 1 && window.__fileEnvoi.etat.horsLigne")
        page.close()
        page = ctx.new_page()
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        ctx.set_offline(False)
        page.goto(adresse + "/?essai")
        page.wait_for_function("window.__fileEnvoi && window.__fileEnvoi.etat.surIphone === 0", timeout=15000)
        assert page.evaluate("fetch('/health').then(r => r.json()).then(j => j.en_attente)") == depart + 2

        # 3. session perdue : la file attend, l'écran de connexion revient, puis tout part
        ctx.clear_cookies()
        page.evaluate("window.__fileEnvoi.ajouter({section: 'section-essai-01', mode: 'rafale', ordre: 999}, new Blob([new Uint8Array([255,216,255,224,1,2,3])], {type: 'image/jpeg'}))")
        page.wait_for_selector("#mot-de-passe")
        assert page.evaluate("window.__fileEnvoi.etat.surIphone") == 1
        page.fill("#mot-de-passe", "demonstration-12")
        page.click("text=Se connecter")
        page.wait_for_function("window.__fileEnvoi.etat.surIphone === 0", timeout=15000)
        assert page.evaluate("fetch('/health').then(r => r.json()).then(j => j.en_attente)") == depart + 3

        # 4. À traiter montre la section reçue
        page.goto(adresse + "/?essai#/a-traiter")
        page.wait_for_selector("text=à dater")
        large = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        b.close()
    assert not erreurs, erreurs
    assert not large
