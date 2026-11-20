"""0.8.0 (socle 0.9.0) : santé des tâches de fond dans /health et copie cohérente de la base."""
from __future__ import annotations

import sqlite3
import time

import pytest

from app import maison
from tests.test_api import client, connecter
from tests.test_envoi import attendre_fin, remplir

JETON = "jeton-commun-essai"


@pytest.fixture(autouse=True)
def registre_neuf(monkeypatch):
    """Registre de tâches propre à chaque test (le vrai vit le temps du processus)."""
    monkeypatch.setattr(maison, "TACHES", maison.Taches())
    monkeypatch.setenv("MAISON_JETON", JETON)


def attendre(condition, delai=5):
    fin = time.time() + delai
    while time.time() < fin:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("délai dépassé")


def par_nom(sante):
    return {t["nom"]: t for t in sante["taches"]}


def test_health_porte_la_sante_sans_message_sans_jeton(tmp_path):
    c, _ = client(tmp_path)
    with c:
        r = c.get("/health").json()
        assert r["version_socle"] == "0.11.1"
        taches = par_nom(r)
        assert {"purge", "envoi-immich", "copie-des-bases"} <= set(taches)
        assert taches["purge"]["type"] == "reguliere" and taches["purge"]["periode_s"] == 6 * 3600
        assert taches["envoi-immich"]["type"] == "demande"
        assert taches["copie-des-bases"]["periode_s"] == 86400
        assert all("message" not in t for t in r["taches"])
        assert r["copie_base"] == {"le": None, "ok": False, "bases": ["chambre-noire.db"], "taille": 0}
        attendre(lambda: par_nom(c.get("/health").json())["purge"]["etat"] == "ok")   # purge du démarrage
        # avec le jeton commun, puis avec une session : messages présents
        avec = c.get("/health", headers={"Authorization": f"Bearer {JETON}"}).json()
        assert all("message" in t for t in avec["taches"])
        assert all("message" not in t for t in c.get("/health", headers={"Authorization": "Bearer faux"}).json()["taches"])
        connecter(c)
        assert all("message" in t for t in c.get("/health").json()["taches"])


def test_purge_ratee_passe_en_retard(tmp_path):
    c, _ = client(tmp_path)
    from app import main

    def purge_cassee():
        raise OSError("disque plein")
    main.purger = purge_cassee
    with c:
        attendre(lambda: par_nom(c.get("/health").json())["purge"]["dernier_essai"] is not None)
        attendre(lambda: par_nom(c.get("/health").json())["purge"]["derniere_erreur"] is not None)
        t = par_nom(c.get("/health", headers={"Authorization": f"Bearer {JETON}"}).json())["purge"]
        assert t["etat"] == "en_retard" and t["message"] == "OSError: disque plein"


def test_envoi_qui_casse_passe_en_erreur(tmp_path, monkeypatch):
    from app.envoi import Envoyeur

    def casse(self, sid):
        raise RuntimeError("Immich a disparu")
    monkeypatch.setattr(Envoyeur, "_envoyer_les_prises", casse)
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        remplir(c, n=1)
        assert c.post("/api/sections/section-01/envoyer", json={"annee": 1987, "mois": 5}).status_code == 202
        assert attendre_fin(c)["statut"] == "incomplete"            # comportement d'avant : section relançable
        assert par_nom(c.get("/health").json())["envoi-immich"]["etat"] == "erreur"


def test_copie_de_la_base(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        remplir(c, n=2)
        r = maison.copier_bases([tmp_path / "chambre-noire.db"], tmp_path / "copies")
        assert r["ok"] and r["bases"] == ["chambre-noire.db"] and r["taille"] > 0
        assert c.get("/health").json()["copie_base"]["ok"] is True
    copie = sqlite3.connect(tmp_path / "copies" / "chambre-noire-derniere.db")
    try:
        assert copie.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        copie.close()
