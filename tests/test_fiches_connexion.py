"""Fiches « Connexion » communes (contrat 3, socle 0.10.0) : forme de /api/maison/services, accès par session ou
ANNEAU_CLE seulement (jamais MAISON_JETON), « Vérifier » d'un service pas relié n'essaie rien, copies non retouchées
du module commun et de l'interface commune."""
from pathlib import Path

import pytest

from app import maison
from app.config import APPLI
from tests import test_api as base
from tests.test_api import connecter

RACINE = Path(__file__).resolve().parent.parent
CLE = "cle-anneau-de-test-1234567890"
IDS = ["immich", "immich-ml", "millesime"]
CHAMPS = {"id", "nom", "genre", "cible", "etat", "lit", "ecrit", "reglage", "detail", "verifie_le", "guide",
          "derniere_ecriture", "gestes"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("MAISON_JETON", raising=False)
    monkeypatch.delenv("ANNEAU_CLE", raising=False)
    c, _ = base.client(tmp_path)
    with c:
        yield c


def test_forme_du_contrat_3(client):
    connecter(client)
    r = client.get("/api/maison/services")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    corps = r.json()
    assert corps["contrat"] == 3 and corps["appli"] == APPLI and corps["simule"] is False
    assert [s["id"] for s in corps["services"]] == IDS
    for s in corps["services"]:
        assert set(s) == CHAMPS and s["lit"] and s["ecrit"] and s["etat"] in maison.ETATS_SERVICE
        assert len(s["gestes"]) <= 1
        if s["etat"] == "pas_relie":
            assert s["reglage"]


def test_acces_session_ou_cle_anneau(client, monkeypatch):
    assert client.get("/api/maison/services").status_code == 401
    monkeypatch.setenv("MAISON_JETON", "jeton-commun-de-test-12345")
    entete = {"Authorization": "Bearer jeton-commun-de-test-12345"}
    assert client.get("/api/maison/services", headers=entete).status_code == 401
    monkeypatch.setenv("ANNEAU_CLE", CLE)
    assert client.get("/api/maison/services", headers={"Authorization": f"Bearer {CLE}"}).status_code == 200
    assert client.get("/api/maison/services", headers={"Authorization": "Bearer mauvaise"}).status_code == 401


def test_verifier_inconnu_et_pas_relie(client):
    connecter(client)
    assert client.post("/api/maison/services/inconnu/verifier").status_code == 404
    for s in client.get("/api/maison/services").json()["services"]:
        if s["etat"] == "pas_relie":
            apres = client.post(f"/api/maison/services/{s['id']}/verifier").json()
            assert apres["etat"] == "pas_relie" and apres["verifie_le"] is None


def test_copies_communes_non_retouchees():
    assert maison.CONTRAT == 3 and maison.VERSION_SOCLE == "0.11.0"
    assert maison.empreinte_calculee() == maison.empreinte_ecrite()
    for nom in maison.FICHIERS_INTERFACE:
        ecrite, calculee = maison.empreinte_interface(RACINE / "frontend" / "src" / "lib" / "services" / nom)
        assert ecrite and ecrite == calculee, nom


def test_verifier_immich_et_guide_des_permissions(tmp_path, monkeypatch):
    """Chambre noire : Vérifier lit Immich (version, clé, permissions) sans rien écrire, même en lecture seule ;
    les permissions manquantes passent dans le guide de la fiche ; Millésime : pas relié sans MAISON_JETON."""
    from tests.faux_immich import TOUTES, FauxImmich
    monkeypatch.delenv("MAISON_JETON", raising=False)
    faux = FauxImmich(permissions=[p for p in TOUTES if p != "queue.update"])
    c, _ = base.client(tmp_path, faux=faux, lecture_seule=True)
    with c:
        connecter(c)
        avant = {s["id"]: s for s in c.get("/api/maison/services").json()["services"]}
        assert avant["immich"]["etat"] == "relie" and avant["immich-ml"]["etat"] == "relie"
        assert avant["millesime"]["etat"] == "pas_relie" and avant["millesime"]["reglage"].startswith("MAISON_JETON")
        fiche = c.post("/api/maison/services/immich/verifier").json()
        assert fiche["etat"] == "repond" and "manquante" in fiche["detail"] and fiche["verifie_le"]
        signes = [p["signe"] for p in fiche["guide"]["pannes"]]
        assert signes and "permission" in signes[0]
        assert any("queue.update ou job.create" in x for x in fiche["guide"]["pannes"][0]["faire"])
        assert {"nom": "Libellé", "valeur": "« Numérisation Essai »"} in fiche["guide"]["reglages"]
        assert faux.ecritures == []


def test_millesime_relie_par_le_jeton_commun(tmp_path, monkeypatch):
    monkeypatch.setenv("MAISON_JETON", "jeton-commun-de-test-12345")
    c, _ = base.client(tmp_path)
    with c:
        connecter(c)
        assert c.post("/api/maison/services/millesime/verifier").json()["etat"] == "ne_repond_pas"
        assert c.get("/externe/noms", headers={"Authorization": "Bearer jeton-commun-de-test-12345"}).status_code == 200
        fiche = {s["id"]: s for s in c.get("/api/maison/services").json()["services"]}["millesime"]
        assert fiche["etat"] == "repond" and fiche["detail"].startswith("Dernière lecture")
