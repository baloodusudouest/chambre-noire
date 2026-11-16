"""Étape 4 : date, tag, album, description, rangement ; incomplet puis relance ; Annuler limité au journal."""
from __future__ import annotations

import io
import time

from PIL import Image

from app.metadonnees import date_prise, injecter
from tests.faux_immich import FauxImmich
from tests.test_api import client, connecter
from tests.test_attente import envoyer


def jpeg(couleur="red", taille=(60, 40)):
    b = io.BytesIO()
    Image.new("RGB", taille, couleur).save(b, "JPEG")
    return b.getvalue()


def remplir(c, n=3, section="section-01"):
    for i, coul in zip(range(n), ["red", "green", "blue", "yellow", "white"]):
        assert envoyer(c, pid=(f"prise-000{i}" if section == "section-01" else f"{section}-p{i}"), section=section, rendu=jpeg(coul), ordre=i,
                       prise_le="2026-11-15T20:30:00+01:00").status_code == 201


def attendre_fin(c, section="section-01", delai=10):
    fin = time.time() + delai
    while time.time() < fin:
        s = next((x for x in c.get("/api/sections").json()["sections"] if x["id"] == section), None)
        if not s or s["statut"] in ("envoyee", "incomplete"):
            return s
        time.sleep(0.05)
    raise AssertionError("envoi trop long")


def exif(contenu):
    im = Image.open(io.BytesIO(contenu))
    e = im.getexif()
    return e.get_ifd(0x8769), im.size


def test_envoi_complet(tmp_path):
    faux = FauxImmich()
    c, _ = client(tmp_path, faux)
    with c:
        connecter(c)
        remplir(c)
        assert c.patch("/api/prises/prise-0001", json={"rotation": 1}).status_code == 200
        r = c.post("/api/sections/section-01/envoyer", json={"annee": 1987, "mois": 5})
        assert r.status_code == 202
        assert attendre_fin(c) is None                     # section envoyée : plus rien à traiter
        assert c.get("/health").json()["envoyees"] == 3 and c.get("/health").json()["en_attente"] == 0
        j = c.get("/api/journal").json()["journal"]
    assert len(faux.assets) == 3
    a1 = faux.assets["asset-1"]
    ex, _ = exif(a1["contenu"])
    assert ex[0x9003] == "1987:05:01 20:30:00" and ex[0x9011] == "+02:00"
    assert b"Num\xc3\xa9risation Essai|1987-05" in a1["contenu"]
    assert a1["champs"]["fileCreatedAt"] == "1987-05-01T20:30:00.000+02:00"
    assert a1["champs"]["deviceAssetId"] == "chambre-noire-prise-0000"
    assert a1["description"] == "1987-05 Numérisation Essai"
    # rotation d'un quart de tour écrite dans les pixels (60×40 → 40×60)
    assert exif(faux.assets["asset-2"]["contenu"])[1] == (40, 60)
    assert exif(faux.assets["asset-2"]["contenu"])[0][0x9003] == "1987:05:01 20:30:01"
    (album,) = faux.albums.values()
    assert album["albumName"] == "1987-05 Numérisation Essai" and album["assets"] == set(faux.assets)
    (tag,) = faux.tags.values()
    assert tag["value"] == "Numérisation Essai/1987-05" and tag["assets"] == set(faux.assets)
    assert "PUT /api/jobs/storageTemplateMigration" in faux.ecritures
    assert j[0]["action"] == "envoi" and sorted(j[0]["details"]["assets"]) == sorted(faux.assets)


def test_non_datees_pour_millesime(tmp_path):
    faux = FauxImmich()
    c, _ = client(tmp_path, faux)
    with c:
        connecter(c)
        remplir(c, 1)
        c.post("/api/sections/section-01/envoyer", json={"non_datee": True})
        attendre_fin(c)
    a = faux.assets["asset-1"]
    ex, _ = exif(a["contenu"])
    assert ex[0x9003] == "1900:01:01 20:30:00" and ex[0x9011] == "+00:00"
    assert [x["albumName"] for x in faux.albums.values()] == ["Non datées Numérisation Essai"]
    assert [t["value"] for t in faux.tags.values()] == ["Numérisation Essai/Non datée"]


def test_annee_seule(tmp_path):
    faux = FauxImmich()
    c, _ = client(tmp_path, faux)
    with c:
        connecter(c)
        remplir(c, 1)
        c.post("/api/sections/section-01/envoyer", json={"annee": 1992, "mois": 0})
        attendre_fin(c)
    assert [x["albumName"] for x in faux.albums.values()] == ["1992 Numérisation Essai"]
    assert exif(faux.assets["asset-1"]["contenu"])[0][0x9003] == "1992:01:01 20:30:00"


def test_tag_rate_puis_relance_sans_renvoyer(tmp_path):
    faux = FauxImmich(panne_tag=True)
    c, _ = client(tmp_path, faux)
    with c:
        connecter(c)
        remplir(c, 2)
        c.post("/api/sections/section-01/envoyer", json={"annee": 1990, "mois": 7})
        s = attendre_fin(c)
        assert s["statut"] == "incomplete" and [e["etape"] for e in s["etapes"]] == ["tag"]
        assert len(faux.assets) == 2 and len(faux.albums) == 1
        faux.panne_tag = False
        c.post("/api/sections/section-01/envoyer", json={})          # Relancer : garde la date
        assert attendre_fin(c) is None
    assert len(faux.assets) == 2                                      # rien n'est renvoyé
    assert [t["value"] for t in faux.tags.values()] == ["Numérisation Essai/1990-07"]


def test_rangement_par_ancienne_adresse(tmp_path):
    faux = FauxImmich(sans_jobs=True)
    c, _ = client(tmp_path, faux)
    with c:
        connecter(c)
        remplir(c, 1)
        c.post("/api/sections/section-01/envoyer", json={"annee": 1990, "mois": 1})
        assert attendre_fin(c) is None
    assert "PUT /api/queues/storageTemplateMigration" in faux.ecritures


def test_annuler_limite_au_journal(tmp_path):
    faux = FauxImmich()
    c, _ = client(tmp_path, faux)
    with c:
        connecter(c)
        remplir(c, 2)
        c.post("/api/sections/section-01/envoyer", json={"annee": 1985, "mois": 3})
        attendre_fin(c)
        faux.assets["asset-autre"] = {"contenu": b"", "nom": "", "champs": {}, "description": "", "corbeille": False}
        jid = c.get("/api/journal").json()["journal"][0]["id"]
        r = c.post(f"/api/journal/{jid}/annuler")
        assert r.status_code == 200 and r.json()["photos"] == 2
        assert c.post(f"/api/journal/{jid}/annuler").status_code == 409
        # les prises reviennent à dater ; renvoyées avec une autre date, ce sont de nouvelles photos
        assert c.get("/health").json()["en_attente"] == 2
        c.post("/api/sections/section-01/envoyer", json={"annee": 1986, "mois": 3})
        attendre_fin(c)
    assert faux.assets["asset-autre"]["corbeille"] is False           # jamais touchée
    assert faux.assets["asset-1"]["corbeille"] and faux.assets["asset-2"]["corbeille"]   # l'envoi annulé, à la corbeille
    nouvelles = [a for k, a in faux.assets.items() if k not in ("asset-1", "asset-2", "asset-autre")]
    assert len(nouvelles) == 2 and not any(a["corbeille"] for a in nouvelles)
    (album,) = [a for a in faux.albums.values() if a["albumName"] == "1985-03 Numérisation Essai"]
    assert album["assets"] == set()


def test_lecture_seule_n_ecrit_rien(tmp_path):
    faux = FauxImmich()
    c, _ = client(tmp_path, faux, lecture_seule=True)
    with c:
        connecter(c)
        remplir(c, 1)
        r = c.post("/api/sections/section-01/envoyer", json={"annee": 1990})
        assert r.status_code == 409 and "lecture seule" in r.json()["detail"].lower()
    assert faux.ecritures == []


def test_sans_libelle_refuse(tmp_path):
    faux = FauxImmich()
    c, _ = client(tmp_path, faux, libelle="")
    with c:
        connecter(c)
        remplir(c, 1)
        r = c.post("/api/sections/section-01/envoyer", json={"annee": 1990})
        assert r.status_code == 409 and "Réglages" in r.json()["detail"]
    assert faux.ecritures == []


def test_date_invalide(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        remplir(c, 1)
        assert c.post("/api/sections/section-01/envoyer", json={"annee": 1700}).status_code == 409


def test_metadonnees_identiques_a_scan_immich():
    """Mêmes octets d'EXIF que Scan Immich v3.9 (logiciel mis à part) : date de mai 1987 à Paris."""
    d = date_prise(1987, 5, False, 12 * 3600 + 3, heure=0)
    out = injecter(jpeg(), d, "Num/1987-05")
    ex, _ = exif(out)
    assert ex[0x9003] == "1987:05:01 12:00:03" and ex[0x9010] == "+02:00"


def test_libelle_regle_dans_l_appli(tmp_path):
    """0.4.1 : le libellé vient de Réglages ; la stack ne donne que la valeur de départ."""
    faux = FauxImmich()
    c, _ = client(tmp_path, faux, libelle="")
    with c:
        connecter(c)
        assert c.get("/api/reglages").json() == {"libelle": "", "album_non_datees": ""}
        assert c.put("/api/reglages", json={"libelle": "Avec/barre"}).status_code == 400
        assert c.put("/api/reglages", json={"libelle": ""}).status_code == 400
        r = c.put("/api/reglages", json={"libelle": "Numérisation Réglée", "album_non_datees": "Sans date"})
        assert r.status_code == 200
        assert c.get("/api/session").json()["libelle"] == "Numérisation Réglée"
        remplir(c, 2)
        c.post("/api/sections/section-01/envoyer", json={"annee": 1991, "mois": 2})
        attendre_fin(c)
        remplir(c, 1, section="section-02")
        c.post("/api/sections/section-02/envoyer", json={"non_datee": True})
        attendre_fin(c, "section-02")
    assert sorted(a["albumName"] for a in faux.albums.values()) == ["1991-02 Numérisation Réglée", "Sans date"]
    assert sorted(t["value"] for t in faux.tags.values()) == ["Numérisation Réglée/1991-02", "Numérisation Réglée/Non datée"]


def test_reglage_garde_apres_redemarrage(tmp_path):
    c, _ = client(tmp_path, libelle="Valeur de la stack")
    with c:
        connecter(c)
        assert c.get("/api/reglages").json()["libelle"] == "Valeur de la stack"
        c.put("/api/reglages", json={"libelle": "Valeur de l'appli"})
    c2, _ = client(tmp_path, libelle="Valeur de la stack")
    with c2:
        connecter(c2)
        assert c2.get("/api/reglages").json()["libelle"] == "Valeur de l'appli"
