"""Tests de l'API sans réseau (faux Immich)."""
from __future__ import annotations

import importlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config as config_mod
from tests.faux_immich import FauxImmich

MDP = "mot-de-passe-de-test"


def client(tmp_path, faux=None, lecture_seule=False, cle="cle-de-test", libelle="Numérisation Essai", jeton_millesime=""):
    from app import main
    importlib.reload(main)
    faux = faux or FauxImmich()
    main.ETAT.clear()
    main.ETAT["cfg"] = config_mod.Config(password=MDP, data=tmp_path, static=tmp_path / "static",
                                         immich_url="http://immich", immich_cle=cle, ml_url="http://ml",
                                         attente_connexion=False, lecture_seule=lecture_seule, libelle=libelle,
                                         jeton_millesime=jeton_millesime)
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


def test_noms_pour_millesime(tmp_path):
    """0.5.0 : Millésime lit les noms des envois ; jeton vide = adresse fermée ; aucune session nécessaire."""
    c, _ = client(tmp_path)
    with c:
        assert c.get("/externe/noms").status_code == 404
    c, _ = client(tmp_path, jeton_millesime="jeton-millesime-essai")
    with c:
        assert c.get("/externe/noms").status_code == 401
        assert c.get("/externe/noms", headers={"Authorization": "Bearer autre"}).status_code == 401
        r = c.get("/externe/noms", headers={"Authorization": "Bearer jeton-millesime-essai"})
        assert r.status_code == 200
        j = r.json()
        assert j["regle"] and j["libelle"] == "Numérisation Essai"
        assert j["album_non_datees"] == "Non datées Numérisation Essai"
        assert j["tag_non_datee"] == "Numérisation Essai/Non datée"
        connecter(c)
        c.put("/api/reglages", json={"libelle": "Numérisation Autre", "album_non_datees": "Sans date"})
        j = c.get("/externe/noms", headers={"Authorization": "Bearer jeton-millesime-essai"}).json()
        assert (j["libelle"], j["album_non_datees"], j["tag_non_datee"]) == ("Numérisation Autre", "Sans date", "Numérisation Autre/Non datée")
        m = c.get("/api/services").json()["millesime"]
        assert m["ouvert"] and m["vu"]
    c, _ = client(tmp_path / "vide", libelle="", jeton_millesime="j")
    (tmp_path / "vide").mkdir(exist_ok=True)
    with c:
        assert c.get("/externe/noms", headers={"Authorization": "Bearer j"}).json()["regle"] is False


# ================================================================ 0.6.0 : variables communes de la maison

COMMUNES = ("MAISON_PASSWORD", "MAISON_JETON", "MAISON_JETON_ANCIEN", "MAISON_LECTURE_SEULE",
            "CHAMBRE_NOIRE_LECTURE_SEULE", "CHAMBRE_NOIRE_JETON_MILLESIME")


def test_module_commun_maison_non_retouche():
    from app import maison
    assert maison.empreinte_calculee() == maison.empreinte_ecrite()


def test_mot_de_passe_commun_puis_repli(monkeypatch):
    for v in COMMUNES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("CHAMBRE_NOIRE_PASSWORD", "ancien-mot-de-passe")
    assert config_mod.charger().password == "ancien-mot-de-passe"
    monkeypatch.setenv("MAISON_PASSWORD", "mot-de-passe-commun")
    assert config_mod.charger().password == "mot-de-passe-commun"
    monkeypatch.setenv("MAISON_PASSWORD", "court")          # le commun trop court ne laisse pas démarrer
    with pytest.raises(SystemExit, match="MAISON_PASSWORD"):
        config_mod.charger()


def test_lecture_seule_maison_et_forcage(monkeypatch):
    for v in COMMUNES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("CHAMBRE_NOIRE_PASSWORD", MDP)
    cfg = config_mod.charger()
    assert not cfg.lecture_seule and cfg.origine_lecture_seule == ""
    monkeypatch.setenv("MAISON_LECTURE_SEULE", "oui")
    cfg = config_mod.charger()
    assert cfg.lecture_seule and cfg.origine_lecture_seule == "maison"
    monkeypatch.setenv("CHAMBRE_NOIRE_LECTURE_SEULE", "non")       # Chambre noire écrit malgré la maison
    cfg = config_mod.charger()
    assert not cfg.lecture_seule and cfg.origine_lecture_seule == ""
    monkeypatch.delenv("MAISON_LECTURE_SEULE")
    monkeypatch.setenv("CHAMBRE_NOIRE_LECTURE_SEULE", "1")         # ancienne valeur acceptée
    cfg = config_mod.charger()
    assert cfg.lecture_seule and cfg.origine_lecture_seule == "appli"


def test_origine_lecture_seule_annoncee(tmp_path):
    from dataclasses import replace
    from app import main
    c, _ = client(tmp_path, lecture_seule=True)
    with c:
        connecter(c)
        assert c.get("/api/session").json()["origine_lecture_seule"] == "appli"
        main.ETAT["cfg"] = replace(main.ETAT["cfg"], origine_lecture_seule="maison")
        assert c.get("/api/session").json()["origine_lecture_seule"] == "maison"
        assert c.get("/api/services").json()["origine_lecture_seule"] == "maison"


def test_porte_millesime_jeton_commun_et_ancien(tmp_path, monkeypatch):
    for v in COMMUNES:
        monkeypatch.delenv(v, raising=False)
    # jeton commun seul : la porte s'ouvre
    monkeypatch.setenv("MAISON_JETON", "jeton-commun-essai")
    c, _ = client(tmp_path)
    with c:
        assert c.get("/externe/noms").status_code == 401
        assert c.get("/externe/noms", headers={"Authorization": "Bearer jeton-commun-essai"}).status_code == 200
        assert c.get("/externe/noms", headers={"X-Maison-Jeton": "jeton-commun-essai"}).status_code == 200
        assert c.get("/externe/noms", headers={"Authorization": "Bearer autre"}).status_code == 401
        connecter(c)
        assert c.get("/api/services").json()["millesime"]["ouvert"] is True
    # ancien jeton de la paire et jeton commun acceptés ensemble (transition), et MAISON_JETON_ANCIEN
    monkeypatch.setenv("MAISON_JETON_ANCIEN", "jeton-commun-precedent")
    c, _ = client(tmp_path, jeton_millesime="jeton-millesime-essai")
    with c:
        for j in ("jeton-millesime-essai", "jeton-commun-essai", "jeton-commun-precedent"):
            assert c.get("/externe/noms", headers={"Authorization": f"Bearer {j}"}).status_code == 200
        assert c.get("/externe/noms", headers={"Authorization": "jeton-millesime-essai"}).status_code == 200  # en-tête historique
    # aucun jeton : porte fermée
    monkeypatch.delenv("MAISON_JETON")
    monkeypatch.delenv("MAISON_JETON_ANCIEN")
    c, _ = client(tmp_path)
    with c:
        assert c.get("/externe/noms", headers={"Authorization": "Bearer "}).status_code == 404
        connecter(c)
        assert c.get("/api/services").json()["millesime"]["ouvert"] is False
