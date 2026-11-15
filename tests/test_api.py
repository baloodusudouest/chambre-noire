"""Tests de l'API sans réseau (faux Immich)."""
from __future__ import annotations

import importlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config as config_mod
from tests.faux_immich import FauxImmich

MDP = "mot-de-passe-de-test"


def client(tmp_path, faux=None, lecture_seule=False, cle="cle-de-test"):
    from app import main
    importlib.reload(main)
    faux = faux or FauxImmich()
    main.ETAT.clear()
    main.ETAT["cfg"] = config_mod.Config(password=MDP, data=tmp_path, static=tmp_path / "static",
                                         immich_url="http://immich", immich_cle=cle, ml_url="http://ml",
                                         attente_connexion=False, lecture_seule=lecture_seule)
    main.ETAT["transport"] = httpx.MockTransport(faux)
    return TestClient(main.app), faux


def connecter(c):
    assert c.post("/api/connexion", json={"mot_de_passe": MDP}).status_code == 200


def test_mot_de_passe_obligatoire(monkeypatch):
    monkeypatch.setenv("CHAMBRE_NOIRE_PASSWORD", "court")
    with pytest.raises(SystemExit):
        config_mod.charger()


def test_aucune_valeur_personnelle_par_defaut(monkeypatch):
    monkeypatch.setenv("CHAMBRE_NOIRE_PASSWORD", MDP)
    for v in ("IMMICH_CLE", "IMMICH_URL", "ML_URL", "DATA", "LECTURE_SEULE"):
        monkeypatch.delenv("CHAMBRE_NOIRE_" + v, raising=False)
    cfg = config_mod.charger()
    assert cfg.immich_cle == "" and cfg.immich_url == "http://immich_server:2283" and not cfg.lecture_seule


def test_health_publique_sans_nom(tmp_path):
    c, _ = client(tmp_path)
    with c:
        r = c.get("/health").json()
    from app import __version__
    assert r["ok"] and r["appli"] == "chambre-noire" and r["version"] == __version__
    assert set(r) == {"ok", "appli", "version", "en_attente", "envoyees"}


def test_api_fermee_sans_session(tmp_path):
    c, _ = client(tmp_path)
    with c:
        assert c.get("/api/services").status_code == 401
        assert c.post("/api/connexion", json={"mot_de_passe": "faux"}).status_code == 401
        assert c.get("/api/services").status_code == 401


def test_cookie_commun_de_l_anneau(tmp_path):
    from app.auth import COMMUN, Sessions
    c, _ = client(tmp_path)
    with c:
        jeton = Sessions("anneau", MDP).creer_commun()
        c.cookies.set(COMMUN, jeton)
        assert c.get("/api/services").status_code == 200


def test_services_tout_va_bien(tmp_path):
    c, faux = client(tmp_path)
    with c:
        connecter(c)
        r = c.get("/api/services").json()
    assert r["immich"]["ok"] and r["immich"]["version"] == "3.4.1"
    assert r["immich"]["permissions_lues"] and r["immich"]["manquantes"] == []
    assert r["apprentissage"]["ok"]
    assert faux.ecritures == []          # 0.1.0 : aucune écriture chez Immich


def test_permission_de_rangement_manquante(tmp_path):
    perms = [p for p in FauxImmich().permissions if p != "queue.update"]
    c, _ = client(tmp_path, FauxImmich(permissions=perms))
    with c:
        connecter(c)
        r = c.get("/api/services").json()
    manquantes = [m["permission"] for m in r["immich"]["manquantes"]]
    assert manquantes == ["queue.update ou job.create"]


def test_ancien_nom_de_permission_accepte(tmp_path):
    perms = [p for p in FauxImmich().permissions if p != "queue.update"] + ["job.create"]
    c, _ = client(tmp_path, FauxImmich(permissions=perms))
    with c:
        connecter(c)
        assert c.get("/api/services").json()["immich"]["manquantes"] == []


def test_permission_all(tmp_path):
    c, _ = client(tmp_path, FauxImmich(permissions=["all"]))
    with c:
        connecter(c)
        assert c.get("/api/services").json()["immich"]["manquantes"] == []


def test_cle_refusee(tmp_path):
    c, _ = client(tmp_path, FauxImmich(cle_valide=False))
    with c:
        connecter(c)
        r = c.get("/api/services").json()["immich"]
    assert not r["ok"] and "refusée" in r["erreur"]


def test_cle_absente(tmp_path):
    c, _ = client(tmp_path, cle="")
    with c:
        connecter(c)
        r = c.get("/api/services").json()["immich"]
    assert not r["ok"] and "CHAMBRE_NOIRE_IMMICH_CLE" in r["erreur"]


def test_immich_en_panne(tmp_path):
    c, _ = client(tmp_path, FauxImmich(en_panne=True))
    with c:
        connecter(c)
        r = c.get("/api/services").json()
    assert not r["immich"]["ok"] and "injoignable" in r["immich"]["erreur"]
    assert not r["apprentissage"]["ok"]


def test_permissions_illisibles(tmp_path):
    c, _ = client(tmp_path, FauxImmich(sans_api_keys_me=True))
    with c:
        connecter(c)
        r = c.get("/api/services").json()["immich"]
    assert r["ok"] and not r["permissions_lues"] and "illisibles" in r["erreur"]


def test_lecture_seule_annoncee(tmp_path):
    c, _ = client(tmp_path, lecture_seule=True)
    with c:
        connecter(c)
        assert c.get("/api/session").json()["lecture_seule"] is True


def test_exiger_ecriture_refuse_en_lecture_seule(tmp_path):
    from app import main
    c, _ = client(tmp_path, lecture_seule=True)
    with c:
        with pytest.raises(main.LectureSeule):
            main.exiger_ecriture("Immich")
