"""Zone d'attente : une prise reçue n'est jamais perdue, ni reçue deux fois."""
from __future__ import annotations

import json

from tests.test_api import client, connecter

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 2000
SOURCE = b"\xff\xd8\xff\xe1" + b"y" * 5000


def envoyer(c, pid="prise-0001", section="section-01", rendu=JPEG, source=SOURCE, mode="rafale", **meta):
    m = {"id": pid, "section": section, "mode": mode, "ordre": meta.pop("ordre", 0),
         "coins": [[0, 0], [1, 0], [1, 1], [0, 1]], "rotation": 1, **meta}
    fichiers = {"rendu": ("r.jpg", rendu, "image/jpeg")}
    if source is not None:
        fichiers["source"] = ("s.jpg", source, "image/jpeg")
    return c.post("/api/prises", data={"meta": json.dumps(m)}, files=fichiers)


def test_reception_et_accuse(tmp_path):
    c, faux = client(tmp_path)
    with c:
        connecter(c)
        r = envoyer(c)
        assert r.status_code == 201 and r.json() == {"ok": True, "id": "prise-0001", "deja": False}
        assert (tmp_path / "attente/section-01/prise-0001-rendu.jpg").read_bytes() == JPEG
        assert (tmp_path / "attente/section-01/prise-0001-source.jpg").read_bytes() == SOURCE
        assert c.get("/health").json()["en_attente"] == 1
        s = c.get("/api/sections").json()["sections"]
        assert [(x["id"], x["mode"], x["prises"]) for x in s] == [("section-01", "rafale", 1)]
        assert c.get("/api/prises/prise-0001/rendu.jpg").content == JPEG
    assert faux.ecritures == []          # rien chez Immich


def test_renvoi_sans_doublon(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        envoyer(c)
        r = envoyer(c)                   # réponse perdue : l'iPhone renvoie
        assert r.status_code == 201 and r.json()["deja"] is True
        assert c.get("/health").json()["en_attente"] == 1


def test_meme_identifiant_autre_image_refuse(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        envoyer(c)
        assert envoyer(c, rendu=JPEG + b"zz").status_code == 422


def test_entrees_refusees(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        assert envoyer(c, pid="../../etc").status_code == 422
        assert envoyer(c, rendu=b"pas une image").status_code == 422
        assert envoyer(c, mode="autre").status_code == 422
        assert c.post("/api/prises", data={"meta": "{pas du json"}, files={"rendu": ("r.jpg", JPEG)}).status_code == 422
        assert c.get("/health").json()["en_attente"] == 0
        assert not any((tmp_path / "attente").rglob("*.part"))


def test_sans_source(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        assert envoyer(c, source=None).status_code == 201
        assert c.get("/api/prises/prise-0001/source.jpg").status_code == 404


def test_fermee_sans_session(tmp_path):
    c, _ = client(tmp_path)
    with c:
        assert envoyer(c).status_code == 401
        assert c.get("/api/sections").status_code == 401


def test_survit_au_redemarrage(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        for i in range(3):
            envoyer(c, pid=f"prise-000{i}", ordre=i)
    c2, _ = client(tmp_path)             # nouveau processus, même dossier de données
    with c2:
        connecter(c2)
        assert c2.get("/health").json()["en_attente"] == 3
        assert [p["id"] for p in c2.get("/api/sections/section-01/prises").json()["prises"]] == \
               ["prise-0000", "prise-0001", "prise-0002"]


def test_retirer_une_prise(tmp_path):
    c, _ = client(tmp_path)
    with c:
        connecter(c)
        envoyer(c)
        assert c.delete("/api/prises/prise-0001").status_code == 200
        assert c.delete("/api/prises/prise-0001").status_code == 404
        assert not (tmp_path / "attente/section-01/prise-0001-rendu.jpg").exists()
        assert c.get("/api/sections").json()["sections"] == []


def test_vignette_de_revue(tmp_path):
    """0.5.1 : la revue montre une vignette de 480 px faite une fois depuis le rendu ; retirée avec la prise."""
    import io
    from PIL import Image
    from app.attente import Attente
    a = Attente(tmp_path)
    tampon = io.BytesIO()
    Image.new("RGB", (4000, 3000), (120, 80, 40)).save(tampon, "JPEG")
    a.recevoir({"id": "prise-v1", "section": "section-v", "mode": "rafale", "ordre": 1,
                "prise_le": "2026-11-15T20:00:00Z"}, tampon.getvalue(), None)
    v = a.vignette("prise-v1")
    assert v and v.is_file()
    with Image.open(v) as im:
        assert max(im.size) <= 480
    assert a.vignette("prise-inconnue") is None
    assert a.retirer("prise-v1") and not v.exists()
