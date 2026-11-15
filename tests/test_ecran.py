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
        page.get_by_role("list", name="Services").get_by_text("Immich", exact=True).click()
        page.wait_for_selector("text=queue.update ou job.create")
        page.goto(adresse + "/#/reglages")
        page.wait_for_selector("text=Chambre noire 0.1.0")
        large = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        b.close()
    assert not erreurs, erreurs
    assert not large, "débordement horizontal"
