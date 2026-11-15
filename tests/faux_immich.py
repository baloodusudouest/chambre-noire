"""Faux Immich et faux service d'apprentissage, écrits d'après les réponses d'Immich 3.x :
GET /api/server/version → {major, minor, patch} ; GET /api/api-keys/me → {id, name, permissions} ;
GET /ping (apprentissage) → « pong ». Aucun réseau dans les tests."""
from __future__ import annotations

import httpx

TOUTES = ["asset.upload", "asset.read", "asset.update", "asset.delete", "album.read", "album.create",
          "albumAsset.create", "tag.read", "tag.create", "tag.asset", "queue.update"]


class FauxImmich:
    def __init__(self, permissions=None, cle_valide=True, en_panne=False, sans_api_keys_me=False):
        self.permissions = TOUTES if permissions is None else permissions
        self.cle_valide = cle_valide
        self.en_panne = en_panne
        self.sans_api_keys_me = sans_api_keys_me
        self.ecritures: list[str] = []     # toute méthode autre que GET est notée ici

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        if requete.method != "GET":
            self.ecritures.append(f"{requete.method} {requete.url.path}")
        if self.en_panne:
            raise httpx.ConnectError("faux Immich arrêté", request=requete)
        chemin = requete.url.path
        if chemin == "/ping":
            return httpx.Response(200, text="pong")
        if requete.headers.get("x-api-key") != "cle-de-test" or not self.cle_valide:
            if chemin == "/api/server/version":
                return httpx.Response(200, json={"major": 3, "minor": 4, "patch": 1})
            return httpx.Response(401, json={"message": "Invalid API key"})
        if chemin == "/api/server/version":
            return httpx.Response(200, json={"major": 3, "minor": 4, "patch": 1})
        if chemin == "/api/api-keys/me":
            if self.sans_api_keys_me:
                return httpx.Response(404, json={"message": "Not found"})
            return httpx.Response(200, json={"id": "k1", "name": "chambre-noire", "permissions": self.permissions})
        return httpx.Response(404, json={"message": "Not found"})
