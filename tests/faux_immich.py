"""Faux Immich et faux service d'apprentissage, écrits d'après les réponses d'Immich 3.x :
GET /api/server/version → {major, minor, patch} ; GET /api/api-keys/me → {id, name, permissions} ;
GET /ping (apprentissage) → « pong ». Aucun réseau dans les tests."""
from __future__ import annotations

import httpx

TOUTES = ["asset.upload", "asset.read", "asset.update", "asset.delete", "album.read", "album.create",
          "albumAsset.create", "tag.read", "tag.create", "tag.asset", "queue.update"]


class FauxImmich:
    """Écritures d'après Immich 3.x : POST /api/assets (multipart) → {id, status: created|duplicate} ;
    GET/POST /api/albums ; PUT /api/albums/{id}/assets ; PUT /api/tags → [{id, value}] ; PUT /api/tags/assets ;
    PUT /api/assets/{id} ; PUT /api/jobs/storageTemplateMigration ; DELETE (Annuler) ; POST /api/trash/restore/assets."""

    def __init__(self, permissions=None, cle_valide=True, en_panne=False, sans_api_keys_me=False, panne_tag=False,
                 sans_jobs=False):
        self.permissions = TOUTES if permissions is None else permissions
        self.cle_valide = cle_valide
        self.en_panne = en_panne
        self.sans_api_keys_me = sans_api_keys_me
        self.panne_tag = panne_tag
        self.sans_jobs = sans_jobs
        self.ecritures: list[str] = []     # toute méthode autre que GET est notée ici
        self.assets: dict[str, dict] = {}  # id → {contenu, nom, champs, description, corbeille}
        self.par_empreinte: dict[int, str] = {}
        self.albums: dict[str, dict] = {}  # id → {albumName, assets:set}
        self.tags: dict[str, dict] = {}    # id → {value, assets:set}

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
        return self.ecrire(requete, chemin)

    def ecrire(self, requete: httpx.Request, chemin: str) -> httpx.Response:
        import json as _json
        from email.parser import BytesParser
        from email.policy import default
        m = requete.method
        corps = _json.loads(requete.content or b"null") if requete.headers.get("content-type", "").startswith("application/json") else None
        if m == "POST" and chemin == "/api/assets":
            msg = BytesParser(policy=default).parsebytes(
                b"Content-Type: " + requete.headers["content-type"].encode() + b"\r\n\r\n" + requete.content)
            champs, contenu, nom = {}, b"", ""
            for partie in msg.iter_parts():
                n = partie.get_param("name", header="content-disposition")
                if n == "assetData":
                    contenu, nom = partie.get_payload(decode=True), partie.get_filename()
                else:
                    champs[n] = partie.get_content()
            cle = hash(contenu)
            if cle in self.par_empreinte:
                return httpx.Response(200, json={"id": self.par_empreinte[cle], "status": "duplicate"})
            aid = f"asset-{len(self.assets) + 1}"
            self.assets[aid] = {"contenu": contenu, "nom": nom, "champs": champs, "description": "", "corbeille": False}
            self.par_empreinte[cle] = aid
            return httpx.Response(201, json={"id": aid, "status": "created"})
        if m == "GET" and chemin == "/api/albums":
            return httpx.Response(200, json=[{"id": i, "albumName": a["albumName"]} for i, a in self.albums.items()])
        if m == "POST" and chemin == "/api/albums":
            aid = f"album-{len(self.albums) + 1}"
            self.albums[aid] = {"albumName": corps["albumName"], "assets": set(corps.get("assetIds") or [])}
            return httpx.Response(201, json={"id": aid})
        if chemin.startswith("/api/albums/") and chemin.endswith("/assets"):
            a = self.albums[chemin.split("/")[3]]
            (a["assets"].update if m == "PUT" else a["assets"].difference_update)(corps["ids"])
            return httpx.Response(200, json=[])
        if m == "PUT" and chemin == "/api/tags":
            if self.panne_tag:
                return httpx.Response(500, json={"message": "panne simulée"})
            sortie = []
            for v in corps["tags"]:
                tid = next((i for i, t in self.tags.items() if t["value"] == v), None) or f"tag-{len(self.tags) + 1}"
                self.tags.setdefault(tid, {"value": v, "assets": set()})
                sortie.append({"id": tid, "value": v})
            return httpx.Response(200, json=sortie)
        if m == "PUT" and chemin == "/api/tags/assets":
            for t in corps["tagIds"]:
                self.tags[t]["assets"].update(corps["assetIds"])
            return httpx.Response(200, json={"count": len(corps["assetIds"])})
        if chemin.startswith("/api/tags/") and chemin.endswith("/assets") and m == "DELETE":
            self.tags[chemin.split("/")[3]]["assets"].difference_update(corps["ids"])
            return httpx.Response(200, json=[])
        if m == "PUT" and chemin.startswith("/api/assets/"):
            self.assets[chemin.split("/")[3]]["description"] = corps.get("description", "")
            return httpx.Response(200, json={})
        if m == "DELETE" and chemin == "/api/assets":
            for i in corps["ids"]:
                self.assets[i]["corbeille"] = True
            return httpx.Response(204)
        if m == "POST" and chemin == "/api/trash/restore/assets":
            for i in corps["ids"]:
                self.assets[i]["corbeille"] = False
            return httpx.Response(200, json={"count": len(corps["ids"])})
        if m == "PUT" and chemin.endswith("/storageTemplateMigration"):
            if self.sans_jobs and chemin.startswith("/api/jobs"):
                return httpx.Response(404, json={"message": "Not found"})
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"message": "Not found"})
