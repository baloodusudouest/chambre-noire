"""0.7.0 : réglages dans l'appli (reprise unique des anciennes variables), sauvegarde pour l'Anneau, restauration.
Sans réseau : l'Anneau est simulé par ETAT["lire_anneau"] (argument « lire » de maison.lire_sauvegarde)."""
from __future__ import annotations

import json
import urllib.error

import pytest

from tests.test_api import COMMUNES, client, connecter

JETON = "jeton-commun-essai"
ENTETE = {"Authorization": f"Bearer {JETON}"}


@pytest.fixture(autouse=True)
def environnement(monkeypatch):
    for v in COMMUNES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("MAISON_JETON", JETON)


def faux_anneau(sauvegardes: dict, appels: list | None = None):
    """sauvegardes : {"AAAA-MM-JJ": {clé: valeur}}. Répond comme l'Anneau (/externe/sauvegardes/chambre-noire)."""
    def lire(adresse, jeton):
        if appels is not None:
            appels.append((adresse, jeton))
        assert "/externe/sauvegardes/chambre-noire" in adresse and jeton == JETON
        if "?le=" not in adresse:
            return {"dates": sorted(sauvegardes, reverse=True)}
        le = adresse.split("?le=")[1]
        if le not in sauvegardes:
            raise urllib.error.HTTPError(adresse, 404, "Not Found", {}, None)
        return {"le": le, "version": "0.7.0", "reglages": sauvegardes[le]}
    return lire


def anneau_injoignable(adresse, jeton):
    raise urllib.error.URLError("connexion refusée")


def journal_reglages(c):
    return [e for e in c.get("/api/journal").json()["journal"] if e["action"] != "envoi"]


# ================================================================ reprise des anciennes variables

def test_reprise_au_premier_demarrage_puis_variable_ignoree(tmp_path):
    c, _ = client(tmp_path, libelle="Numérisation Stack", album_non_datees="Sans date stack")
    with c:
        connecter(c)
        assert c.get("/api/reglages").json() == {"libelle": "Numérisation Stack", "album_non_datees": "Sans date stack"}
        lignes = journal_reglages(c)
        assert sorted((e["action"], e["details"]["variable"]) for e in lignes) == [
            ("reglage", "CHAMBRE_NOIRE_ALBUM_NON_DATEES"), ("reglage", "CHAMBRE_NOIRE_LIBELLE")]
    # second démarrage, la stack a changé : la variable n'est plus lue
    c2, _ = client(tmp_path, libelle="Numérisation Autre stack", album_non_datees="Autre")
    with c2:
        connecter(c2)
        assert c2.get("/api/reglages").json() == {"libelle": "Numérisation Stack", "album_non_datees": "Sans date stack"}
        assert len(journal_reglages(c2)) == 2            # aucune nouvelle reprise


def test_variable_vide_au_premier_demarrage_puis_posee(tmp_path):
    """Rien dans la stack au premier démarrage : réglage vide, et une variable ajoutée ensuite n'est pas lue."""
    c, _ = client(tmp_path, libelle="")
    with c:
        connecter(c)
        assert c.get("/api/reglages").json()["libelle"] == ""
        assert journal_reglages(c) == []
    c2, _ = client(tmp_path, libelle="Numérisation Tardive")
    with c2:
        connecter(c2)
        assert c2.get("/api/reglages").json()["libelle"] == ""


def test_base_0_4_garde_ses_reglages(tmp_path):
    """Une base qui a déjà des réglages (0.4.1 à 0.6.0) les garde : la variable n'est pas reprise par-dessus."""
    c, _ = client(tmp_path, libelle="")
    with c:
        connecter(c)
        c.put("/api/reglages", json={"libelle": "Numérisation Réglée"})
    c2, _ = client(tmp_path, libelle="Numérisation Stack")
    with c2:
        connecter(c2)
        assert c2.get("/api/reglages").json()["libelle"] == "Numérisation Réglée"


# ================================================================ écran Réglages

def test_put_reglages_partiel_et_types(tmp_path):
    c, _ = client(tmp_path, album_non_datees="Sans date")
    with c:
        assert c.put("/api/reglages", json={"libelle": "X"}).status_code == 401      # session nécessaire
        connecter(c)
        r = c.put("/api/reglages", json={"libelle": "Numérisation Neuve"})
        assert r.status_code == 200 and r.json() == {"libelle": "Numérisation Neuve", "album_non_datees": "Sans date"}
        r = c.put("/api/reglages", json={"libelle": 12})
        assert r.status_code == 400 and "texte attendu" in r.json()["detail"]
        assert c.put("/api/reglages", json={"album_non_datees": ["a"]}).status_code == 400
        assert c.put("/api/reglages", json=["libelle"]).status_code == 400
        assert c.put("/api/reglages", json={"inconnu": 1}).json()["libelle"] == "Numérisation Neuve"


def test_reglages_permis_en_lecture_seule(tmp_path):
    c, faux = client(tmp_path, lecture_seule=True)
    with c:
        connecter(c)
        assert c.put("/api/reglages", json={"libelle": "Numérisation LS"}).status_code == 200
    assert faux.ecritures == []


# ================================================================ /externe/sauvegarde

def test_sauvegarde_jeton_requis_et_contenu(tmp_path, monkeypatch):
    c, _ = client(tmp_path, libelle="Numérisation Essai", album_non_datees="Sans date")
    with c:
        assert c.get("/externe/sauvegarde").status_code == 401
        assert c.get("/externe/sauvegarde", headers={"Authorization": "Bearer autre"}).status_code == 401
        connecter(c)
        c.get("/externe/noms", headers=ENTETE)            # écrit « millesime_vu » dans la même table
        r = c.get("/externe/sauvegarde", headers=ENTETE)
        assert r.status_code == 200
        j = r.json()
    from app import __version__
    assert j["contrat"] == 1 and j["appli"] == "chambre-noire" and j["version"] == __version__
    assert j["reglages"] == {"libelle": "Numérisation Essai", "album_non_datees": "Sans date"}
    texte = json.dumps(j)
    for interdit in ("millesime_vu", JETON, "mot-de-passe", "cle-de-test", "http://immich", "CHAMBRE_NOIRE_", str(tmp_path)):
        assert interdit not in texte
    # l'ancien jeton par paire n'ouvre pas cette porte ; MAISON_JETON vide : porte fermée
    monkeypatch.setenv("CHAMBRE_NOIRE_JETON_MILLESIME", "ancien-jeton")
    monkeypatch.delenv("MAISON_JETON")
    c, _ = client(tmp_path)
    with c:
        assert c.get("/externe/sauvegarde", headers={"Authorization": "Bearer ancien-jeton"}).status_code == 404
        assert c.get("/externe/sauvegarde", headers=ENTETE).status_code == 404


def test_sauvegarde_sans_session(tmp_path):
    """Le garde des sessions ne bloque pas /externe/… : le jeton suffit, sans cookie."""
    c, _ = client(tmp_path)
    with c:
        assert c.get("/externe/sauvegarde", headers=ENTETE).status_code == 200


# ================================================================ restaurer

def test_restaurer_dates_differences_application(tmp_path):
    from app import main
    c, faux = client(tmp_path, libelle="Numérisation Actuelle", lecture_seule=True)
    appels = []
    with c:
        main.ETAT["lire_anneau"] = faux_anneau({
            "2026-11-15": {"libelle": "Numérisation Sauvée", "album_non_datees": "", "millesime_vu": "x", "inconnu": 1},
            "2026-11-14": {"libelle": "Numérisation Actuelle", "album_non_datees": ""}}, appels)
        assert c.get("/api/restaurer").status_code == 401
        connecter(c)
        assert c.get("/api/restaurer").json() == {"dates": ["2026-11-15", "2026-11-14"]}
        r = c.get("/api/restaurer", params={"le": "2026-11-15"}).json()
        assert r["le"] == "2026-11-15" and r["version"] == "0.7.0"
        assert r["differences"] == [{"cle": "libelle", "actuel": "Numérisation Actuelle", "sauve": "Numérisation Sauvée"}]
        assert c.get("/api/restaurer", params={"le": "2026-11-14"}).json()["differences"] == []
        assert c.get("/api/restaurer", params={"le": "hier"}).status_code == 400
        assert c.get("/api/restaurer", params={"le": "2026-01-01"}).status_code == 404
        # appliquer (permis en lecture seule : réglages internes seulement)
        r = c.post("/api/restaurer", json={"le": "2026-11-15"})
        assert r.status_code == 200
        assert r.json()["appliques"] == ["libelle"]
        assert c.get("/api/reglages").json()["libelle"] == "Numérisation Sauvée"
        (ligne,) = [e for e in journal_reglages(c) if e["action"] == "restauration"]
        assert ligne["details"] == {"le": "2026-11-15", "cles": ["libelle"]}
        assert c.post("/api/restaurer", json={}).status_code == 400
    assert faux.ecritures == []
    assert all("?le=" not in a or a.endswith(("2026-11-15", "2026-11-14", "2026-01-01")) for a, _ in appels)


def test_restaurer_valeur_refusee(tmp_path):
    from app import main
    c, _ = client(tmp_path, libelle="Numérisation Actuelle")
    with c:
        main.ETAT["lire_anneau"] = faux_anneau({"2026-11-15": {"libelle": "Avec/barre"}})
        connecter(c)
        r = c.post("/api/restaurer", json={"le": "2026-11-15"})
        assert r.status_code == 400 and "/" in r.json()["detail"]
        assert c.get("/api/reglages").json()["libelle"] == "Numérisation Actuelle"


def test_restaurer_anneau_injoignable_ou_sans_jeton(tmp_path, monkeypatch):
    from app import main
    c, _ = client(tmp_path)
    with c:
        main.ETAT["lire_anneau"] = anneau_injoignable
        connecter(c)
        r = c.get("/api/restaurer")
        assert r.status_code == 503 and "Anneau ne répond pas" in r.json()["detail"]
        assert c.post("/api/restaurer", json={"le": "2026-11-15"}).status_code == 503
        main.ETAT["lire_anneau"] = faux_anneau({})
        assert c.get("/api/restaurer").json() == {"dates": []}
        r = c.get("/api/restaurer", params={"le": "2026-11-15"})
        assert r.status_code == 404 and "aucune sauvegarde" in r.json()["detail"]
        monkeypatch.delenv("MAISON_JETON")
        r = c.get("/api/restaurer")
        assert r.status_code == 503 and "MAISON_JETON" in r.json()["detail"]
