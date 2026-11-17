"""Envoi d'une section dans Immich (étape 4) : date et tag dans chaque JPEG, rotation dans les pixels, envoi,
album du mois, tag, description (nom de l'album), lancement du rangement du stockage.

Règles :
- les noms viennent de Réglages › Noms dans Immich (0.7.0 : plus de la stack) : album « AAAA-MM <libellé> », tag « <libellé>/AAAA-MM » ;
  non datées : album « Non datées <libellé> », tag « <libellé>/Non datée » (ceux que lit Millésime) ;
- chaque écriture est notée au journal avant de rendre la main ; Annuler n'agit que sur les photos du journal ;
- une étape ratée (album, tag, description, rangement) laisse la section « incomplète » avec un bouton Relancer :
  les photos déjà envoyées ne sont jamais renvoyées.
"""
from __future__ import annotations

import io
import threading
from datetime import datetime, timedelta

import httpx
from PIL import Image

from .attente import Attente
from .metadonnees import PARIS, date_prise, decalage, injecter

MOIS = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


class ErreurEnvoi(RuntimeError):
    pass


def feuille(annee: int, mois: int, non_datee: bool) -> str:
    return "ND" if non_datee else (f"{annee}-{mois:02d}" if mois else str(annee))


def noms(libelle: str, annee: int, mois: int, non_datee: bool, album_non_datees: str = "") -> tuple[str, str]:
    libelle = libelle.strip().replace("/", "-").replace("\\", "-")
    album = (album_non_datees or f"Non datées {libelle}") if non_datee else f"{feuille(annee, mois, False)} {libelle}"
    tag = f"{libelle}/" + ("Non datée" if non_datee else feuille(annee, mois, False))
    return album, tag


def tourner(jpeg: bytes, rotation: int, qualite: int = 92) -> bytes:
    """Rotation dans les pixels (quarts de tour, sens horaire), comme Scan Immich : aucun tag d'orientation."""
    if not rotation % 4:
        return jpeg
    im = Image.open(io.BytesIO(jpeg))
    im = im.transpose({1: Image.Transpose.ROTATE_270, 2: Image.Transpose.ROTATE_180, 3: Image.Transpose.ROTATE_90}[rotation % 4])
    sortie = io.BytesIO()
    im.save(sortie, "JPEG", quality=qualite, subsampling=0)
    return sortie.getvalue()


class ImmichEcriture:
    """Les seules écritures de Chambre noire chez Immich."""

    def __init__(self, url: str, cle: str, transport: httpx.BaseTransport | None = None):
        self._c = httpx.Client(base_url=url.rstrip("/"), timeout=120.0, transport=transport,
                               headers={"x-api-key": cle, "Accept": "application/json"})

    def _ok(self, r: httpx.Response) -> httpx.Response:
        if r.status_code >= 400:
            try:
                msg = r.json().get("message")
            except ValueError:
                msg = r.text[:200]
            raise ErreurEnvoi(f"Immich {r.status_code} : {msg}")
        return r

    def envoyer(self, contenu: bytes, nom: str, appareil_id: str, quand: str) -> tuple[str, bool]:
        r = self._ok(self._c.post("/api/assets", data={
            "deviceAssetId": appareil_id, "deviceId": "chambre-noire", "fileCreatedAt": quand, "fileModifiedAt": quand,
        }, files={"assetData": (nom, contenu, "image/jpeg")}))
        j = r.json()
        if not j.get("id"):
            raise ErreurEnvoi("Réponse d'Immich inattendue à l'envoi.")
        return j["id"], j.get("status") == "duplicate"

    def restaurer(self, ids: list[str]) -> None:
        """Photo déjà connue d'Immich (envoi annulé puis refait) : la sortir de la corbeille si elle y est."""
        # 0.7.3 : réponse contrôlée ; sinon une photo restée dans la corbeille était notée envoyée (et purgée après 30 jours)
        self._ok(self._c.post("/api/trash/restore/assets", json={"ids": ids}))

    def album(self, nom: str, ids: list[str]) -> str:
        albums = self._ok(self._c.get("/api/albums")).json()
        trouve = next((a for a in albums if a.get("albumName") == nom), None)
        if not trouve:
            return self._ok(self._c.post("/api/albums", json={"albumName": nom, "assetIds": ids})).json()["id"]
        self._ok(self._c.put(f"/api/albums/{trouve['id']}/assets", json={"ids": ids}))
        return trouve["id"]

    def tag(self, nom: str, ids: list[str]) -> str:
        tags = self._ok(self._c.put("/api/tags", json={"tags": [nom]})).json()
        t = next((x for x in tags if x.get("value") == nom), tags[-1] if tags else None)
        if not t or not t.get("id"):
            raise ErreurEnvoi("Tag introuvable après sa création.")
        self._ok(self._c.put("/api/tags/assets", json={"assetIds": ids, "tagIds": [t["id"]]}))
        return t["id"]

    def description(self, ids: list[str], texte: str) -> None:
        for i in ids:
            self._ok(self._c.put(f"/api/assets/{i}", json={"description": texte}))

    def rangement(self) -> None:
        derniere = None
        for chemin in ("/api/jobs/storageTemplateMigration", "/api/queues/storageTemplateMigration"):
            try:
                self._ok(self._c.put(chemin, json={"command": "start", "force": False}))
                return
            except ErreurEnvoi as e:
                derniere = e
        raise derniere

    # Annuler
    def retirer_album(self, album_id: str, ids: list[str]) -> None:
        self._ok(self._c.request("DELETE", f"/api/albums/{album_id}/assets", json={"ids": ids}))

    def retirer_tag(self, tag_id: str, ids: list[str]) -> None:
        self._ok(self._c.request("DELETE", f"/api/tags/{tag_id}/assets", json={"ids": ids}))

    def corbeille(self, ids: list[str]) -> None:
        self._ok(self._c.request("DELETE", "/api/assets", json={"ids": ids, "force": False}))


class Envoyeur:
    """Envoie une section à la fois, dans un fil à part ; l'état se lit dans la section (statut, progression)."""

    def __init__(self, attente: Attente, immich: ImmichEcriture, noms_actuels):
        """noms_actuels() → (libellé, album des non datées) : lus au moment de chaque envoi (écran Réglages)."""
        self.attente, self.immich, self.noms_actuels = attente, immich, noms_actuels
        self._verrou = threading.Lock()
        self._fils: dict[str, threading.Thread] = {}

    def lancer(self, sid: str, annee: int, mois: int, non_datee: bool, attendre: bool = False) -> None:
        libelle, album_non_datees = self.noms_actuels()
        if not libelle:
            raise ErreurEnvoi("Libellé des albums et des tags absent : à régler dans Réglages › Noms dans Immich.")
        s = self.attente.section(sid)
        if not s:
            raise ErreurEnvoi("Section introuvable.")
        if s["statut"] == "envoi":
            raise ErreurEnvoi("Envoi déjà en cours.")
        if s["statut"] == "incomplete":           # relance : on garde la date déjà choisie
            annee, mois, non_datee = s["annee"], s["mois"] or 0, bool(s["non_datee"])
        elif not non_datee and not (1850 <= int(annee) <= datetime.now().year and 0 <= int(mois) <= 12):
            raise ErreurEnvoi("Date invalide.")
        album, tag = noms(libelle, int(annee or 1900), int(mois or 0), bool(non_datee), album_non_datees)
        fil = threading.Thread(target=self._envoyer, args=(sid,), daemon=True)
        with self._verrou:                    # 0.7.1 : un double appui ne lance pas deux envois
            if (self.attente.section(sid) or {}).get("statut") == "envoi":
                raise ErreurEnvoi("Envoi déjà en cours.")
            self.attente.maj_section(sid, statut="envoi", annee=annee, mois=mois, non_datee=int(bool(non_datee)),
                                     album=album, tag=tag, erreur=None, progression="Préparation…")
            self._fils[sid] = fil
        fil.start()
        if attendre:
            fil.join()

    def _envoyer(self, sid: str) -> None:
        try:
            self._envoyer_les_prises(sid)
        except Exception as e:  # noqa: BLE001 — 0.7.1 : une erreur imprévue rend la section relançable
            self.attente.maj_section(sid, statut="incomplete", progression=None,
                                     erreur=f"Envoi interrompu : {type(e).__name__} : {e}"[:300])

    def _envoyer_les_prises(self, sid: str) -> None:
        s = self.attente.section(sid)
        annee, mois, nd, album, tag = s["annee"], s["mois"] or 0, bool(s["non_datee"]), s["album"], s["tag"]
        prises = self.attente.prises_a_envoyer(sid)
        # heure de la section dans la journée (ordre des séances d'un même mois), +1 s par photo
        try:
            debut = datetime.fromisoformat(prises[0]["prise_le"].replace("Z", "+00:00")).astimezone(PARIS)
            base = debut.hour * 3600 + debut.minute * 60 + debut.second
        except (ValueError, IndexError):
            base = 12 * 3600
        ids, erreurs = [], 0
        for k, p in enumerate(prises):
            if p["statut"] == "envoyee" and p["asset_id"]:
                ids.append(p["asset_id"]); continue
            self.attente.maj_section(sid, progression=f"Envoi {k + 1} / {len(prises)}")
            try:
                d = date_prise(annee, mois, nd, base + k, heure=0)
                chemin = self.attente.fichier(p["id"], "rendu")
                contenu = injecter(tourner(chemin.read_bytes(), p["rotation"]), d, tag)
                quand = d.strftime("%Y-%m-%dT%H:%M:%S.000") + decalage(d)
                nom = f"ChambreNoire_{feuille(annee, mois, nd)}_{sid[:8]}_{k + 1:03d}.jpg"
                aid, doublon = self.immich.envoyer(contenu, nom, f"chambre-noire-{p['id']}", quand)
                if doublon:
                    self.immich.restaurer([aid])
                self.attente.maj_prise(p["id"], statut="envoyee", asset_id=aid, erreur=None)
                ids.append(aid)
            except Exception as e:  # noqa: BLE001 — une photo ratée ne bloque pas les autres
                erreurs += 1
                self.attente.maj_prise(p["id"], erreur=str(e)[:300])
        etapes, details = [], {"album": album, "tag": tag, "assets": ids}
        if ids:
            self.attente.maj_section(sid, progression=f"Album « {album} »…")
            for nom_etape, faire in (("album", lambda: details.update(album_id=self.immich.album(album, ids))),
                                     ("tag", lambda: details.update(tag_id=self.immich.tag(tag, ids))),
                                     ("description", lambda: self.immich.description(ids, album)),
                                     ("rangement", self.immich.rangement)):
                try:
                    faire()
                except Exception as e:  # noqa: BLE001
                    etapes.append({"etape": nom_etape, "erreur": str(e)[:300]})
            self.attente.noter(sid, "envoi", details)
        if erreurs or etapes:
            self.attente.maj_section(sid, statut="incomplete", etapes=etapes, progression=None,
                                     erreur=f"{erreurs} photo(s) non envoyée(s)" if erreurs else None)
        else:
            self.attente.maj_section(sid, statut="envoyee", etapes=[], progression=None, erreur=None)

    def annuler(self, jid: int) -> dict:
        e = self.attente.entree(jid)
        if not e or e["action"] != "envoi":
            raise ErreurEnvoi("Envoi introuvable dans le journal.")
        if e["annule_le"]:
            raise ErreurEnvoi("Cet envoi est déjà annulé.")
        d = e["details"]
        ids = list(d.get("assets") or [])        # seulement les photos notées au journal
        if d.get("album_id"):
            self.immich.retirer_album(d["album_id"], ids)
        if d.get("tag_id"):
            self.immich.retirer_tag(d["tag_id"], ids)
        self.immich.corbeille(ids)
        self.attente.marquer_annule(jid)
        # les prises reviennent « à dater » : on peut renvoyer avec une autre date
        for p in self.attente.prises_a_envoyer(e["section_id"]):
            if p["asset_id"] in ids:
                self.attente.maj_prise(p["id"], statut="attente", asset_id=None, erreur=None)
        self.attente.maj_section(e["section_id"], statut="en_cours", etapes=[], album=None, tag=None)
        return {"ok": True, "photos": len(ids)}
