"""Lecture de l'état d'Immich et de son service d'apprentissage (0.1.0 : rien n'est écrit).

La vérification des permissions lit la clé elle-même (GET /api/api-keys/me). Une permission
manquante se voit dans « Connexion » avant le premier envoi : c'est ce qui a manqué à Scan Immich
le jour où Immich a exigé queue.update pour lancer le rangement du stockage.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

# Ce dont les étapes suivantes auront besoin (envoi, album, tag, description, rangement, corbeille).
# Noms des permissions d'Immich 3.x ; « all » les couvre toutes. À confirmer sur la vraie installation.
PERMISSIONS_UTILES = {
    "asset.upload": "envoyer les photos",
    "asset.read": "relire une photo envoyée",
    "asset.update": "écrire la description (nom de l'album)",
    "asset.delete": "Annuler : mettre à la corbeille (photos du journal seulement)",
    "album.read": "trouver l'album",
    "album.create": "créer l'album du mois",
    "albumAsset.create": "ranger les photos dans l'album",
    "tag.read": "trouver le tag",
    "tag.create": "créer le tag du mois",
    "tag.asset": "poser le tag sur les photos",
}
# Le lancement du rangement a changé de nom selon les versions : l'une des deux suffit.
PERMISSIONS_RANGEMENT = ("queue.update", "job.create")


@dataclass
class EtatImmich:
    ok: bool
    version: str = ""
    erreur: str = ""
    cle_nom: str = ""
    permissions: list[str] = field(default_factory=list)
    manquantes: list[dict] = field(default_factory=list)
    permissions_lues: bool = False


class Immich:
    def __init__(self, url: str, cle: str, transport: httpx.BaseTransport | None = None):
        self.url = url.rstrip("/")
        self.cle = cle
        self._client = httpx.Client(base_url=self.url, timeout=10.0, transport=transport,
                                    headers={"x-api-key": cle, "Accept": "application/json"})

    def etat(self) -> EtatImmich:
        if not self.cle:
            return EtatImmich(False, erreur="Clé d'API absente : CHAMBRE_NOIRE_IMMICH_CLE dans la stack.")
        try:
            r = self._client.get("/api/server/version")
            r.raise_for_status()
            v = r.json()
            version = f"{v.get('major')}.{v.get('minor')}.{v.get('patch')}"
        except httpx.HTTPStatusError as e:
            return EtatImmich(False, erreur=f"Immich a répondu {e.response.status_code}.")
        except (httpx.HTTPError, ValueError) as e:
            return EtatImmich(False, erreur=f"Immich injoignable ({type(e).__name__}).")
        etat = EtatImmich(True, version=version)
        try:
            r = self._client.get("/api/api-keys/me")
            if r.status_code == 401:
                return EtatImmich(False, version=version, erreur="Clé d'API refusée par Immich.")
            r.raise_for_status()
            cle = r.json()
            etat.cle_nom = str(cle.get("name", ""))
            etat.permissions = sorted(cle.get("permissions") or [])
            etat.permissions_lues = True
        except (httpx.HTTPError, ValueError):
            etat.erreur = "Permissions de la clé illisibles (version d'Immich ?) : vérifie-les dans Immich."
            return etat
        perms = set(etat.permissions)
        if "all" not in perms:
            etat.manquantes = [{"permission": p, "pour": pour}
                               for p, pour in PERMISSIONS_UTILES.items() if p not in perms]
            if not perms.intersection(PERMISSIONS_RANGEMENT):
                etat.manquantes.append({"permission": " ou ".join(PERMISSIONS_RANGEMENT),
                                        "pour": "lancer le rangement du stockage"})
        return etat


class ApprentissageImmich:
    """Service d'apprentissage d'Immich (orientation par les visages, étape 5)."""

    def __init__(self, url: str, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(base_url=url.rstrip("/"), timeout=10.0, transport=transport)

    def etat(self) -> dict:
        t = time.monotonic()
        try:
            r = self._client.get("/ping")
            r.raise_for_status()
            return {"ok": True, "ms": round((time.monotonic() - t) * 1000)}
        except httpx.HTTPError as e:
            return {"ok": False, "erreur": f"Service d'apprentissage injoignable ({type(e).__name__})."}
