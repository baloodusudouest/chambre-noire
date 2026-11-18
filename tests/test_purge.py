"""0.7.6 (audit du 17/11/2026, M33 et M35) : la zone d'attente se vide d'elle-même et refuse ce qu'elle ne peut pas garder."""
from __future__ import annotations

import io
import time
from datetime import datetime, timedelta

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from app import attente as attente_mod
from app.attente import Attente, ErreurEspace, ErreurPrise
from tests.test_api import client, connecter
from tests.test_attente import envoyer
from tests.test_envoi import attendre_fin, jpeg, remplir


def meta(pid, section="section-01"):
    return {"id": pid, "section": section, "mode": "photo", "ordre": 0}


def jpeg_annonce(largeur, hauteur):
    """Petit JPEG dont l'en-tête annonce d'autres dimensions (rien de gros en mémoire)."""
    b = bytearray(jpeg())
    i = b.index(b"\xff\xc0")                   # bloc SOF0 : longueur(2), précision(1), hauteur(2), largeur(2)
    b[i + 5:i + 7] = hauteur.to_bytes(2, "big")
    b[i + 7:i + 9] = largeur.to_bytes(2, "big")
    return bytes(b)


# ---------------------------------------------------------------- M33 : purge
def test_purge_des_fichiers_envoyes_apres_n_jours(tmp_path):
    a = Attente(tmp_path)
    for pid in ("prise-ancienne", "prise-recente", "prise-a-traiter"):
        a.recevoir(meta(pid), jpeg(), jpeg())
    maintenant = datetime.now().astimezone()
    vieux = (maintenant - timedelta(days=31)).isoformat(timespec="seconds")
    a.maj_prise("prise-ancienne", statut="envoyee", asset_id="asset-1", envoyee_le=vieux)
    a.maj_prise("prise-recente", statut="envoyee", asset_id="asset-2",
                envoyee_le=(maintenant - timedelta(days=2)).isoformat(timespec="seconds"))
    assert a.vignette("prise-ancienne")
    assert a.purger(30) == 1
    dossier = tmp_path / "attente" / "section-01"
    assert not list(dossier.glob("prise-ancienne-*"))                   # rendu, source et vignette partis
    assert (dossier / "prise-recente-rendu.jpg").is_file()              # envoyée il y a 2 jours : gardée
    assert (dossier / "prise-a-traiter-rendu.jpg").is_file()            # jamais envoyée : jamais purgée
    assert a.purger(30) == 0                                            # déjà purgée
    assert a.purger(1) == 1                                             # réglage plus court : la récente part aussi
    assert a.envoyees() == 2                                            # les lignes restent (journal, Annuler)


def test_reglage_purge_jours(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        assert c.get("/api/reglages").json()["purge_jours"] == 30          # valeur de départ
        assert c.put("/api/reglages", json={"purge_jours": 7}).json()["purge_jours"] == 7
        for mauvais in (0, 366, "7", True, 2.5):
            assert c.put("/api/reglages", json={"purge_jours": mauvais}).status_code == 400
    c2, _ = client(tmp_path)
    with c2:
        connecter(c2)
        assert c2.get("/api/reglages").json()["purge_jours"] == 7          # gardé dans la base de l'appli


def test_purge_au_demarrage_avec_le_reglage(tmp_path):
    a = Attente(tmp_path)
    a.recevoir(meta("prise-0001"), jpeg(), None)
    a.maj_prise("prise-0001", statut="envoyee", asset_id="asset-1",
                envoyee_le=(datetime.now().astimezone() - timedelta(days=10)).isoformat(timespec="seconds"))
    a.regler("purge_jours", "5")
    c, _ = client(tmp_path)
    with c:                                    # la purge passe au démarrage
        connecter(c)
        for _ in range(100):
            if not (tmp_path / "attente/section-01/prise-0001-rendu.jpg").exists():
                break
            time.sleep(0.02)
        assert not (tmp_path / "attente/section-01/prise-0001-rendu.jpg").exists()


def test_annuler_apres_purge(tmp_path):
    c, faux = client(tmp_path)
    with c:
        connecter(c)
        remplir(c, 2)
        c.post("/api/sections/section-01/envoyer", json={"annee": 1985, "mois": 3})
        attendre_fin(c)
        from app import main
        assert main.ETAT["attente"].purger(0, datetime.now().astimezone() + timedelta(seconds=5)) == 2
        jid = c.get("/api/journal").json()["journal"][0]["id"]
        r = c.post(f"/api/journal/{jid}/annuler")
        assert r.status_code == 200 and r.json()["photos"] == 2 and r.json()["purgees"] == 2
        assert c.get("/health").json()["en_attente"] == 0                 # rien de cassé dans « À traiter »
        assert c.get("/api/sections").json()["sections"] == []
    assert faux.assets["asset-1"]["corbeille"] and faux.assets["asset-2"]["corbeille"]


def test_disque_presque_plein_refuse(tmp_path, monkeypatch):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        assert envoyer(c, pid="prise-0001").status_code == 201
        monkeypatch.setattr(attente_mod, "espace_libre", lambda _d: 500 * 1024 ** 2)
        r = envoyer(c, pid="prise-0002")
        assert r.status_code == 507 and "1 Go" in r.json()["detail"]   # l'iPhone garde la prise et réessaie
        assert not list((tmp_path / "attente/section-01").glob("prise-0002*"))
        assert envoyer(c, pid="prise-0001").status_code == 201            # renvoi d'une prise déjà reçue : accusé
    a = Attente(tmp_path / "autre")
    monkeypatch.setattr(attente_mod, "espace_libre", lambda _d: 1024 ** 3)
    with pytest.raises(ErreurEspace):                                     # la prise elle-même compte
        a.recevoir(meta("prise-0003"), jpeg(), None)


# ---------------------------------------------------------------- M35 : plafonds à la réception
def test_plafond_de_pixels(tmp_path):
    a = Attente(tmp_path)
    with pytest.raises(ErreurPrise, match="trop grande"):
        a.recevoir(meta("prise-geante"), jpeg_annonce(10000, 10000), None)
    with pytest.raises(ErreurPrise, match="source trop grande"):
        a.recevoir(meta("prise-geante"), jpeg(), jpeg_annonce(60000, 60000))
    assert not (tmp_path / "attente" / "section-01").exists()
    a.recevoir(meta("prise-iphone"), jpeg_annonce(8064, 6048), None)    # 48 Mpx : accepté
    assert Image.open(io.BytesIO(jpeg_annonce(8064, 6048))).size == (8064, 6048)


def test_plafond_de_pixels_par_l_api(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        r = envoyer(c, rendu=jpeg_annonce(12000, 12000), source=None)
        assert r.status_code == 422 and "trop grande" in r.json()["detail"]


class Flux(io.BytesIO):
    plus_grande_lecture = 0

    def read(self, n=-1):
        Flux.plus_grande_lecture = max(Flux.plus_grande_lecture, len(super().getvalue()) if n in (-1, None) else n)
        return super().read(n)


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_lecture_plafonnee(monkeypatch, anyio_backend):
    from app import main
    monkeypatch.setattr(main, "TAILLE_MAX", 1000)
    Flux.plus_grande_lecture = 0
    with pytest.raises(ErreurPrise, match="trop lourd"):
        await main._lire_plafonne(UploadFile(Flux(b"\xff\xd8\xff" + b"x" * 50_000)), "rendu")   # taille inconnue
    assert Flux.plus_grande_lecture <= 1001                              # jamais tout en mémoire
    Flux.plus_grande_lecture = 0
    with pytest.raises(ErreurPrise, match="trop lourd"):
        await main._lire_plafonne(UploadFile(Flux(b"x" * 50_000), size=50_000), "rendu")
    assert Flux.plus_grande_lecture == 0                                 # taille annoncée : refus sans lire


def test_prise_annoncee_trop_lourde_refusee_avant_reception(tmp_path, monkeypatch):
    monkeypatch.setattr(attente_mod, "TAILLE_MAX", 1000)
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        r = envoyer(c, rendu=b"\xff\xd8\xff" + b"x" * 1_200_000, source=None)
        assert r.status_code == 422 and r.json()["detail"] == "Prise trop lourde."
