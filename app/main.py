"""Chambre noire : numérisation des tirages papier à l'iPhone vers Immich (FastAPI + interface Svelte).

0.1.0 (squelette) : /health (publique, sans aucun nom), /api/session, /api/connexion, /api/deconnexion,
/api/services (état d'Immich, permissions de la clé, service d'apprentissage), puis l'interface.
0.2.0 (zone d'attente) : /api/prises (réception idempotente), /api/sections, images des prises.
Rien n'est encore écrit dans Immich.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from . import __version__
from .attente import Attente, ErreurPrise
from .auth import COMMUN, DUREE, Sessions
from .config import APPLI, Config, charger
from .immich import ApprentissageImmich, Immich

ETAT: dict = {}
PUBLIQUES = ("/api/connexion", "/api/session")


def _fichier_generation(cfg: Config) -> Path:
    return cfg.data / "session_generation"


def _lire_generation(cfg: Config) -> int:
    try:
        return int(_fichier_generation(cfg).read_text().strip())
    except (OSError, ValueError):
        return 0


@asynccontextmanager
async def cycle(app: FastAPI):
    cfg = ETAT.get("cfg") or charger()
    cfg.data.mkdir(parents=True, exist_ok=True)
    transport = ETAT.get("transport")        # faux Immich dans les tests
    ETAT.update(cfg=cfg, sessions=Sessions(APPLI, cfg.password, _lire_generation(cfg)),
                immich=Immich(cfg.immich_url, cfg.immich_cle, transport), attente=Attente(cfg.data),
                apprentissage=ApprentissageImmich(cfg.ml_url, transport))
    yield


app = FastAPI(title=APPLI, version=__version__, lifespan=cycle, docs_url=None, redoc_url=None)


# ================================================================ sécurité

@app.middleware("http")
async def garde(request: Request, appel):
    chemin = request.url.path
    if chemin.startswith("/api/"):
        if chemin not in PUBLIQUES and not ETAT["sessions"].connecte(request.cookies):
            return JSONResponse({"detail": "Connexion nécessaire."}, status_code=401)
    reponse = await appel(request)
    if chemin.startswith("/api/"):
        reponse.headers["Cache-Control"] = "no-store"
    return reponse


class LectureSeule(Exception):
    """Écriture refusée : l'appli tourne en lecture seule (CHAMBRE_NOIRE_LECTURE_SEULE)."""


def exiger_ecriture(quoi: str = "") -> None:
    """À appeler en tête de toute route, et de toute fonction, qui écrit chez un service extérieur
    (ici Immich). Le refus arrive avant toute trace dans un journal."""
    if ETAT["cfg"].lecture_seule:
        raise LectureSeule(f"Mode lecture seule : rien n'est écrit{' dans ' + quoi if quoi else ''}.")


@app.exception_handler(LectureSeule)
async def _lecture_seule(_: Request, exc: LectureSeule):
    return JSONResponse({"detail": str(exc)}, status_code=409)


# ================================================================ public

@app.get("/health")
def sante():
    # Pour la tuile de l'Anneau : des nombres, jamais de nom. Prises en attente et photos envoyées
    # arrivent avec la zone d'attente (étape 2) et l'envoi (étape 4).
    return {"ok": True, "appli": APPLI, "version": __version__,
            "en_attente": ETAT["attente"].en_attente(), "envoyees": 0}


# ================================================================ connexion

@app.get("/api/session")
def session(request: Request):
    s = ETAT["sessions"]
    return {"connecte": s.connecte(request.cookies), "version": __version__,
            "lecture_seule": ETAT["cfg"].lecture_seule}


@app.post("/api/connexion")
async def connexion(corps: dict = Body(...)):
    s = ETAT["sessions"]
    if ETAT["cfg"].attente_connexion:
        await asyncio.sleep(s.attente())
    if not s.verifier_mot_de_passe(str(corps.get("mot_de_passe", ""))):
        raise HTTPException(401, "Mot de passe incorrect.")
    r = JSONResponse({"ok": True})
    r.set_cookie(s.cookie, s.creer(), max_age=DUREE, httponly=True, samesite="strict")
    return r


@app.post("/api/deconnexion")
def deconnexion():
    s = ETAT["sessions"]
    s.generation += 1
    try:
        _fichier_generation(ETAT["cfg"]).write_text(str(s.generation))
    except OSError:
        pass  # volume en lecture seule : la déconnexion vaut jusqu'au prochain redémarrage
    r = JSONResponse({"ok": True})
    r.delete_cookie(s.cookie)
    r.delete_cookie(COMMUN)      # « Se déconnecter » ferme aussi la connexion commune
    return r


# ================================================================ services (écran « Connexion »)

@app.get("/api/services")
def services():
    """Lit l'état d'Immich (version, clé, permissions) et du service d'apprentissage. N'écrit rien."""
    return {"immich": asdict(ETAT["immich"].etat()), "apprentissage": ETAT["apprentissage"].etat(),
            "lecture_seule": ETAT["cfg"].lecture_seule}


# ================================================================ zone d'attente (étape 2)

@app.post("/api/prises", status_code=201)
async def recevoir_prise(meta: str = Form(...), rendu: UploadFile = File(...), source: UploadFile | None = File(None)):
    """Reçoit une prise de l'iPhone. Réponse 201 = prise en sécurité sur le NAS (l'iPhone peut l'effacer
    de sa file). Un renvoi du même identifiant répond aussi 201, avec « deja »."""
    try:
        donnees = json.loads(meta)
        corps_rendu = await rendu.read()
        corps_source = await source.read() if source else None
        return await asyncio.to_thread(ETAT["attente"].recevoir, donnees, corps_rendu, corps_source)
    except (ErreurPrise, json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(422, str(e) or "Prise illisible.")


@app.get("/api/sections")
def sections():
    return {"sections": ETAT["attente"].sections()}


@app.get("/api/sections/{section}/prises")
def prises_de_section(section: str):
    return {"prises": ETAT["attente"].prises(section)}


@app.get("/api/prises/{pid}/{quoi}.jpg")
def image_de_prise(pid: str, quoi: str):
    chemin = ETAT["attente"].fichier(pid, quoi)
    if not chemin:
        raise HTTPException(404, "Prise introuvable.")
    return FileResponse(chemin, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.delete("/api/prises/{pid}")
def retirer_prise(pid: str):
    """Retire une prise pas encore envoyée (ratée, en double). N'écrit rien dans Immich."""
    if not ETAT["attente"].retirer(pid):
        raise HTTPException(404, "Prise introuvable ou déjà envoyée.")
    return {"ok": True}


# ================================================================ interface

@app.get("/{chemin:path}")
def interface(chemin: str):
    statique = ETAT["cfg"].static
    fichier = (statique / chemin).resolve() if chemin else None
    if fichier and fichier.is_file() and statique.resolve() in fichier.parents:
        return FileResponse(fichier)
    index = statique / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "Interface non compilée."}, status_code=404)
