"""Chambre noire : numérisation des tirages papier à l'iPhone vers Immich (FastAPI + interface Svelte).

0.1.0 (squelette) : /health (publique, sans aucun nom), /api/session, /api/connexion, /api/deconnexion,
/api/services (état d'Immich, permissions de la clé, service d'apprentissage), puis l'interface.
0.2.0 (zone d'attente) : /api/prises (réception idempotente), /api/sections, images des prises.
0.4.0 (envoi) : rotation d'une prise, /api/sections/{id}/envoyer (date, tag, album, description, rangement),
/api/journal et Annuler (limité aux photos du journal). Seules routes qui écrivent dans Immich.
0.7.0 (réglages et sauvegarde) : réglages d'usage dans l'appli seulement (variables reprises une fois),
/externe/sauvegarde (jeton commun, lue par l'Anneau), /api/restaurer ; anciens noms de variables retirés.
"""
from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

import time

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from . import __version__, maison
from .attente import Attente, ErreurPrise
from .auth import COMMUN, DUREE, Sessions, en_https
from .config import APPLI, Config, charger
from .envoi import Envoyeur, ErreurEnvoi, ImmichEcriture, noms
from .immich import ApprentissageImmich, Immich

ETAT: dict = {}
PUBLIQUES = ("/api/connexion", "/api/session")

# ---------------------------------------------------------------- réglages d'usage (0.7.0, contrat de sauvegarde 1)
# Gardés dans la table « reglage » de la base de l'appli (depuis 0.4.1) ; tous des textes.
REGLAGES = ("libelle", "album_non_datees")
# Anciennes variables de la stack, lues UNE fois (premier démarrage) pour reprendre la valeur, puis plus jamais.
REGLAGES_VARIABLES = {"libelle": "CHAMBRE_NOIRE_LIBELLE", "album_non_datees": "CHAMBRE_NOIRE_ALBUM_NON_DATEES"}
# Clés à ne jamais sortir de l'appli, en plus de ce que maison.est_secret() écarte déjà. « millesime_vu » est dans
# la même table mais n'est pas un réglage (heure de la dernière lecture de Millésime).
EXCLUS_SAUVEGARDE: tuple[str, ...] = ("millesime_vu",)
JOUR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
    ETAT["envoyeur"] = Envoyeur(ETAT["attente"], ImmichEcriture(cfg.immich_url, cfg.immich_cle, transport), noms_actuels)
    reprendre_reglages(ETAT["attente"], cfg)
    ETAT["attente"].reprendre_envois_interrompus()          # 0.7.1 : section figée « envoi » après un redémarrage
    yield


def reprendre_reglages(attente: Attente, cfg: Config) -> list[str]:
    """0.7.0 : au premier démarrage, un réglage absent de la base prend la valeur de son ancienne variable (si elle est
    posée), sinon reste vide. Il est alors écrit dans la base : au démarrage suivant, la variable n'est plus regardée.
    Une ligne au journal par réglage repris."""
    repris = []
    for k in REGLAGES:
        if attente.reglage(k) is not None:
            continue
        valeur = str(getattr(cfg, k) or "").strip()
        attente.regler(k, valeur)
        if valeur:
            attente.noter("", "reglage", {"cle": k, "variable": REGLAGES_VARIABLES[k]})
            repris.append(k)
    return repris


app = FastAPI(title=APPLI, version=__version__, lifespan=cycle, docs_url=None, redoc_url=None)


# ================================================================ sécurité
# Le garde ne regarde que /api/… : /externe/… (portes à jeton) et /health passent sans session.

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
    """Écriture refusée : l'appli tourne en lecture seule (MAISON_LECTURE_SEULE, ou CHAMBRE_NOIRE_LECTURE_SEULE qui l'emporte)."""


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
            "en_attente": ETAT["attente"].en_attente(), "envoyees": ETAT["attente"].envoyees()}


@app.get("/externe/noms")
def noms_pour_millesime(request: Request):
    """0.5.0 : Millésime lit ici les noms qu'utilisent les envois (libellé, album et tag des non datées),
    pour suivre le réglage fait dans Chambre noire. 0.7.0 : jeton commun seul (MAISON_JETON, MAISON_JETON_ANCIEN
    pendant un changement) ; vide : adresse fermée. N'écrit rien, sauf l'heure de la lecture (montrée dans Connexion)."""
    acceptes = maison.jetons()
    if not acceptes:
        raise HTTPException(404, "Adresse fermée : MAISON_JETON n'est pas posé.")
    # « Authorization: Bearer … » (ou X-Maison-Jeton) ; l'en-tête historique acceptait aussi le jeton sans « Bearer ».
    propose = maison.jeton_propose(request.headers) or request.headers.get("authorization", "").strip()
    if not maison.jeton_valide(propose, acceptes):      # temps constant
        raise HTTPException(401, "Jeton refusé.")
    libelle, nd = noms_actuels()
    ETAT["attente"].regler("millesime_vu", time.strftime("%Y-%m-%dT%H:%M:%S"))
    if not libelle:
        return {"regle": False, "version": __version__}
    album_nd, tag_nd = noms(libelle, 0, 0, True, nd)
    return {"regle": True, "version": __version__, "libelle": libelle,
            "album_non_datees": album_nd, "tag_non_datee": tag_nd}


# ================================================================ connexion

def reglages_actuels() -> dict:
    """Réglages d'usage, lus dans la base de l'appli (seule source depuis 0.7.0)."""
    a = ETAT["attente"]
    return {k: a.reglage(k) or "" for k in REGLAGES}


def noms_actuels() -> tuple[str, str]:
    """Libellé et album des non datées (Réglages › Noms dans Immich)."""
    r = reglages_actuels()
    return r["libelle"], r["album_non_datees"]


def _origine_lecture_seule() -> str:
    """0.6.0 : « maison » (toute la maison, MAISON_LECTURE_SEULE) ou « appli » (CHAMBRE_NOIRE_LECTURE_SEULE) ; « » : écriture permise."""
    c = ETAT["cfg"]
    return (c.origine_lecture_seule or "appli") if c.lecture_seule else ""


@app.get("/api/session")
def session(request: Request):
    s = ETAT["sessions"]
    connecte = s.connecte(request.cookies)
    sortie = {"connecte": connecte, "version": __version__, "lecture_seule": ETAT["cfg"].lecture_seule,
              "origine_lecture_seule": _origine_lecture_seule()}
    if connecte:   # le libellé (nom d'album et de tag) n'est donné qu'une fois connecté
        libelle, nd = noms_actuels()
        sortie.update(libelle=libelle, album_non_datees=nd)
    return sortie


@app.post("/api/connexion")
async def connexion(request: Request, corps: dict = Body(...)):
    s = ETAT["sessions"]
    if ETAT["cfg"].attente_connexion:
        await asyncio.sleep(s.attente())
    if not s.verifier_mot_de_passe(str(corps.get("mot_de_passe", ""))):
        raise HTTPException(401, "Mot de passe incorrect.")
    r = JSONResponse({"ok": True})
    r.set_cookie(s.cookie, s.creer(), max_age=DUREE, httponly=True, samesite="strict", secure=en_https(request))
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
            "lecture_seule": ETAT["cfg"].lecture_seule, "origine_lecture_seule": _origine_lecture_seule(),
            "libelle": noms_actuels()[0],
            "millesime": {"ouvert": bool(maison.jetons()), "vu": ETAT["attente"].reglage("millesime_vu")}}


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
    chemin = ETAT["attente"].vignette(pid) if quoi == "vignette" else ETAT["attente"].fichier(pid, quoi)
    if not chemin:
        raise HTTPException(404, "Prise introuvable.")
    return FileResponse(chemin, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.patch("/api/prises/{pid}")
def modifier_prise(pid: str, corps: dict = Body(...)):
    """Rotation à la main à la revue (quarts de tour, sens horaire). N'écrit rien dans Immich."""
    if "rotation" not in corps or not ETAT["attente"].tourner(pid, int(corps["rotation"])):
        raise HTTPException(404, "Prise introuvable ou déjà envoyée.")
    return {"ok": True}


@app.post("/api/sections/{sid}/envoyer", status_code=202)
def envoyer_section(sid: str, corps: dict = Body(default={})):
    """Date la section et l'envoie dans Immich (en arrière-plan ; l'état se lit dans /api/sections).
    Une section « incomplète » est relancée avec sa date : les photos déjà envoyées ne repartent pas."""
    exiger_ecriture("Immich")
    try:
        ETAT["envoyeur"].lancer(sid, int(corps.get("annee") or 0), int(corps.get("mois") or 0), bool(corps.get("non_datee")))
    except ErreurEnvoi as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


# ================================================================ réglages (0.4.1 ; 0.7.0 : seule source)
# Réglages internes de l'appli : les changer ou les restaurer est permis même en lecture seule
# (la lecture seule ne protège qu'Immich).

def valider_reglages(valeurs: dict) -> dict:
    """Vérifie les réglages reçus (écran ou sauvegarde) ; seules les clés connues comptent. HTTPException 400 sinon."""
    propres = {}
    for k, v in valeurs.items():
        if k not in REGLAGES:
            continue
        if not isinstance(v, str):
            raise HTTPException(400, f"Valeur refusée pour « {k} » : texte attendu.")
        propres[k] = v.strip()
    if "libelle" in propres:
        libelle = propres["libelle"]
        if not libelle or len(libelle) > 80:
            raise HTTPException(400, "Libellé obligatoire (80 caractères au plus).")
        if "/" in libelle or "\\" in libelle:
            raise HTTPException(400, "Le libellé ne peut pas contenir « / » : il sépare les niveaux du tag.")
    if len(propres.get("album_non_datees", "")) > 120:
        raise HTTPException(400, "Album des non datées : 120 caractères au plus.")
    return propres


def appliquer_reglages(propres: dict) -> dict:
    for k, v in propres.items():
        ETAT["attente"].regler(k, v)
    return reglages_actuels()


@app.get("/api/reglages")
def lire_reglages():
    return reglages_actuels()


@app.put("/api/reglages")
def changer_reglages(corps=Body(...)):
    """Noms utilisés aux prochains envois (rien n'est renommé dans Immich). N'écrit que dans la base de l'appli.
    Seules les clés envoyées changent."""
    if not isinstance(corps, dict):
        raise HTTPException(400, "Réglages attendus sous la forme {clé: valeur}.")
    return appliquer_reglages(valider_reglages(corps))


# ================================================================ sauvegarde (0.7.0, contrat de sauvegarde 1)

@app.get("/externe/sauvegarde")
def externe_sauvegarde(request: Request):
    """Lue chaque nuit par l'Anneau, avec le jeton commun. Réglages publics et version seulement."""
    acceptes = maison.jetons()
    if not acceptes:
        raise HTTPException(404, "Not Found")                 # MAISON_JETON vide : porte fermée
    if not maison.jeton_valide(maison.jeton_propose(request.headers), acceptes):
        raise HTTPException(401, "Jeton commun manquant ou invalide.")
    return maison.sauvegarde(APPLI, __version__, reglages_actuels(), exclus=EXCLUS_SAUVEGARDE)


def _demander_anneau(le: str = "") -> dict:
    """Demande à l'Anneau ; ses pannes deviennent des messages clairs (404 rien à restaurer, 503 injoignable)."""
    if le and not JOUR.match(le):
        raise HTTPException(400, "Date attendue sous la forme AAAA-MM-JJ.")
    if not maison.jeton_a_envoyer():
        raise HTTPException(503, "MAISON_JETON n'est pas posé dans la stack : l'Anneau ne peut pas être interrogé.")
    try:
        reponse = maison.lire_sauvegarde(APPLI, le, lire=ETAT.get("lire_anneau"))
    except Exception as exc:                                  # noqa: BLE001 — urllib, réseau, JSON…
        if getattr(exc, "code", None) == 404:
            raise HTTPException(404, "L'Anneau n'a aucune sauvegarde de Chambre noire"
                                     f"{' le ' + le if le else ''}.") from exc
        raise HTTPException(503, "L'Anneau ne répond pas : restauration impossible pour l'instant "
                                 f"({exc.__class__.__name__}).") from exc
    if not isinstance(reponse, dict):
        raise HTTPException(503, "Réponse de l'Anneau illisible.")
    if le and not isinstance(reponse.get("reglages"), dict):
        raise HTTPException(404, f"L'Anneau n'a aucune sauvegarde de Chambre noire le {le}.")
    return reponse


@app.get("/api/restaurer")
def restaurer_voir(le: str = ""):
    if not le:
        dates = _demander_anneau().get("dates") or []
        return {"dates": [d for d in dates if isinstance(d, str)]}
    sauve = _demander_anneau(le)
    return {"le": le, "version": sauve.get("version", ""),
            "differences": maison.differences(reglages_actuels(), sauve["reglages"], EXCLUS_SAUVEGARDE)}


@app.post("/api/restaurer")
def restaurer(corps=Body(...)):
    """Applique les réglages d'une sauvegarde de l'Anneau qui diffèrent de l'actuel (réglages seulement)."""
    le = str(corps.get("le", "")) if isinstance(corps, dict) else ""
    if not le:
        raise HTTPException(400, "Choisis la date de la sauvegarde à restaurer.")
    sauve = _demander_anneau(le)
    diffs = maison.differences(reglages_actuels(), sauve["reglages"], EXCLUS_SAUVEGARDE)
    propres = valider_reglages({d["cle"]: d["sauve"] for d in diffs})
    reglages = appliquer_reglages(propres)
    if propres:
        ETAT["attente"].noter("", "restauration", {"le": le, "cles": sorted(propres)})
    return {"le": le, "appliques": sorted(propres), "reglages": reglages}


@app.get("/api/journal")
def journal():
    return {"journal": ETAT["attente"].journal()}


@app.post("/api/journal/{jid}/annuler")
def annuler_envoi(jid: int):
    """Retire de l'album et du tag, puis met à la corbeille d'Immich (30 jours), les seules photos de cet envoi."""
    exiger_ecriture("Immich")
    try:
        return ETAT["envoyeur"].annuler(jid)
    except ErreurEnvoi as e:
        raise HTTPException(409, str(e))


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
