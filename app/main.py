"""Chambre noire : numérisation des tirages papier à l'iPhone vers Immich (FastAPI + interface Svelte).

0.1.0 (squelette) : /health (publique, sans aucun nom), /api/session, /api/connexion, /api/deconnexion,
/api/services (état d'Immich, permissions de la clé, service d'apprentissage), puis l'interface.
0.2.0 (zone d'attente) : /api/prises (réception idempotente), /api/sections, images des prises.
0.4.0 (envoi) : rotation d'une prise, /api/sections/{id}/envoyer (date, tag, album, description, rangement),
/api/journal et Annuler (limité aux photos du journal). Seules routes qui écrivent dans Immich.
0.7.0 (réglages et sauvegarde) : réglages d'usage dans l'appli seulement (variables reprises une fois),
/externe/sauvegarde (jeton commun, lue par l'Anneau), /api/restaurer ; anciens noms de variables retirés.
0.7.6 (audit, M33 et M35) : purge des fichiers déjà envoyés après « purge_jours » jours, réception refusée sous 1 Go
libre ; taille et pixels contrôlés à la réception, avant de lire l'image en entier.
0.8.0 (santé des tâches de fond, socle 0.9.0) : tâches suivies dans maison.TACHES (« purge » toutes les 6 h,
« envoi-immich » à la demande), copie cohérente de chambre-noire.db chaque nuit à 02:00 (heure de Paris) dans
/data/copies ; /health ajoute version_socle, taches et copie_base. Un seul worker uvicorn (registre en mémoire).
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
from .attente import TAILLE_MAX, Attente, ErreurEspace, ErreurPrise
from .auth import COMMUN, DUREE, Sessions, en_https
from .config import APPLI, Config, charger
from .envoi import Envoyeur, ErreurEnvoi, ImmichEcriture, noms
from .immich import ApprentissageImmich, Immich

ETAT: dict = {}
PUBLIQUES = ("/api/connexion", "/api/session")

# ---------------------------------------------------------------- réglages d'usage (0.7.0, contrat de sauvegarde 1)
# Gardés dans la table « reglage » de la base de l'appli (depuis 0.4.1) ; tous des textes.
REGLAGES = ("libelle", "album_non_datees", "purge_jours")
# 0.7.6 (M33) : réglages sans ancienne variable, avec leur valeur de départ. « purge_jours » : les fichiers d'une prise
# envoyée dans Immich sont effacés de la zone d'attente après ce nombre de jours (entier, 1 à 365).
DEFAUTS = {"purge_jours": 30}
PURGE_MAX = 365
PURGE_TOUTES = 6 * 3600                  # la purge passe au démarrage puis toutes les 6 heures
# 0.8.0 (socle 0.9.0) : noms des tâches suivies dans maison.TACHES (lus par /health et la veille de l'Anneau)
TACHE_PURGE = "purge"                    # régulière, toutes les PURGE_TOUTES secondes
TACHE_ENVOI = "envoi-immich"             # à la demande (bouton Envoyer d'une section)
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
    maison.TACHES.declarer(TACHE_PURGE, PURGE_TOUTES)
    maison.TACHES.declarer(TACHE_ENVOI, type="demande")
    taches = [asyncio.create_task(boucle_purge()),
              # 0.8.0 : copie cohérente de la base chaque nuit (heure de Paris), dans /data/copies
              asyncio.create_task(maison.planifier_copie(APPLI, [cfg.data / "chambre-noire.db"], cfg.data / "copies",
                                                         maison.HEURES_COPIE[APPLI]))]
    try:
        yield
    finally:
        for tache in taches:
            tache.cancel()


def purger() -> int:
    """0.7.6 (M33) : efface les fichiers des prises envoyées depuis plus de « purge_jours » jours."""
    return ETAT["attente"].purger(reglages_actuels()["purge_jours"])


async def boucle_purge() -> None:
    while True:
        try:
            async with maison.TACHES.tour_async(TACHE_PURGE):     # 0.8.0 : un tour suivi (réussite ou erreur)
                await asyncio.to_thread(purger)
        except Exception:  # noqa: BLE001 — une purge ratée n'arrête pas l'appli ; nouvel essai au tour suivant
            pass
        await asyncio.sleep(PURGE_TOUTES)


def reprendre_reglages(attente: Attente, cfg: Config) -> list[str]:
    """0.7.0 : au premier démarrage, un réglage absent de la base prend la valeur de son ancienne variable (si elle est
    posée), sinon reste vide. Il est alors écrit dans la base : au démarrage suivant, la variable n'est plus regardée.
    Une ligne au journal par réglage repris."""
    repris = []
    for k in REGLAGES:
        if attente.reglage(k) is not None:
            continue
        if k in DEFAUTS:                     # pas d'ancienne variable : valeur de départ
            attente.regler(k, str(DEFAUTS[k]))
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
        # 0.7.6 (M35) : une prise annoncée plus lourde que deux fichiers au plafond est refusée avant d'être reçue
        if chemin == "/api/prises" and request.method == "POST":
            try:
                annonce = int(request.headers.get("content-length") or 0)
            except ValueError:
                annonce = 0
            if annonce > 2 * TAILLE_MAX + 1024 * 1024:
                return JSONResponse({"detail": "Prise trop lourde."}, status_code=422)
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
def sante(request: Request):
    # Pour la tuile de l'Anneau : des nombres, jamais de nom. Prises en attente et photos envoyées
    # arrivent avec la zone d'attente (étape 2) et l'envoi (étape 4).
    # 0.8.0 : + version_socle, taches, copie_base (messages d'erreur seulement avec le jeton commun ou une session).
    return {"ok": True, "appli": APPLI, "version": __version__,
            "en_attente": ETAT["attente"].en_attente(), "envoyees": ETAT["attente"].envoyees(),
            **maison.sante(request, jeton_commun=maison.jetons(),
                           session_ok=ETAT["sessions"].connecte(request.cookies))}


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
    sortie = {k: a.reglage(k) or "" for k in REGLAGES}
    try:
        sortie["purge_jours"] = int(sortie["purge_jours"])
    except ValueError:
        sortie["purge_jours"] = DEFAUTS["purge_jours"]
    return sortie


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
        corps_rendu = await _lire_plafonne(rendu, "rendu")
        corps_source = await _lire_plafonne(source, "source") if source else None
        return await asyncio.to_thread(ETAT["attente"].recevoir, donnees, corps_rendu, corps_source)
    except ErreurEspace as e:                # 507 : l'iPhone garde la prise et réessaie plus tard
        raise HTTPException(507, str(e))
    except (ErreurPrise, json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(422, str(e) or "Prise illisible.")


async def _lire_plafonne(fichier: UploadFile, nom: str) -> bytes:
    """0.7.6 (M35) : jamais plus de TAILLE_MAX + 1 octets en mémoire ; taille annoncée vérifiée avant toute lecture.
    Les pixels (PIXELS_MAX) sont lus dans l'en-tête par Attente.recevoir, sans décoder l'image."""
    if fichier.size is not None and fichier.size > TAILLE_MAX:
        raise ErreurPrise(f"Fichier {nom} trop lourd.")
    contenu = await fichier.read(TAILLE_MAX + 1)
    if len(contenu) > TAILLE_MAX:
        raise ErreurPrise(f"Fichier {nom} trop lourd.")
    return contenu


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
        if k not in REGLAGES or k in DEFAUTS:      # « purge_jours » (entier) est vérifié plus bas
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
    if "purge_jours" in valeurs:
        v = valeurs["purge_jours"]
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= PURGE_MAX:
            raise HTTPException(400, f"Purge de la zone d'attente : nombre entier de jours, de 1 à {PURGE_MAX}.")
        propres["purge_jours"] = v
    if len(propres.get("album_non_datees", "")) > 120:
        raise HTTPException(400, "Album des non datées : 120 caractères au plus.")
    return propres


def appliquer_reglages(propres: dict) -> dict:
    for k, v in propres.items():
        ETAT["attente"].regler(k, str(v))
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
