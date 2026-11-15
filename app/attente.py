"""Zone d'attente (étape 2) : chaque prise est envoyée par l'iPhone dès qu'elle est faite, et gardée ici
jusqu'à l'envoi dans Immich. Rien n'entre dans Immich depuis ce module.

- L'identifiant de chaque prise est fixé par l'iPhone : un renvoi (réseau coupé, réponse perdue,
  appli rouverte) retrouve la prise déjà reçue au lieu d'en créer une seconde.
- Les fichiers sont écrits en entier dans un fichier temporaire, puis renommés : une coupure ne laisse
  jamais une image à moitié écrite. La prise n'existe dans la base qu'une fois ses fichiers en place ;
  l'iPhone ne l'efface de sa file qu'après cette réponse (accusé de réception).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MODES = ("rafale", "photo", "page")
TAILLE_MAX = 30 * 1024 * 1024        # par fichier
JPEG = b"\xff\xd8\xff"


class ErreurPrise(ValueError):
    pass


class Attente:
    def __init__(self, dossier: Path):
        self.dossier = dossier
        (dossier / "attente").mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()
        self._db = sqlite3.connect(dossier / "chambre-noire.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS section (
                id TEXT PRIMARY KEY, mode TEXT NOT NULL, creee_le TEXT NOT NULL,
                statut TEXT NOT NULL DEFAULT 'en_cours');
            CREATE TABLE IF NOT EXISTS prise (
                id TEXT PRIMARY KEY, section_id TEXT NOT NULL REFERENCES section(id),
                ordre INTEGER NOT NULL, prise_le TEXT NOT NULL, recue_le TEXT NOT NULL,
                coins TEXT, rotation INTEGER NOT NULL DEFAULT 0, filtre TEXT, intensite INTEGER,
                taille_rendu INTEGER NOT NULL, taille_source INTEGER NOT NULL DEFAULT 0,
                statut TEXT NOT NULL DEFAULT 'attente');
            CREATE TABLE IF NOT EXISTS reglage (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT, quand TEXT NOT NULL, section_id TEXT NOT NULL,
                action TEXT NOT NULL, details TEXT NOT NULL, annule_le TEXT);
        """)
        # 0.4.0 : colonnes de l'envoi (ajoutées à une base 0.2/0.3 existante)
        for table, colonne, defn in (
            ("prise", "asset_id", "TEXT"), ("prise", "erreur", "TEXT"),
            ("section", "annee", "INTEGER"), ("section", "mois", "INTEGER"), ("section", "non_datee", "INTEGER"),
            ("section", "album", "TEXT"), ("section", "tag", "TEXT"), ("section", "etapes", "TEXT"),
            ("section", "progression", "TEXT"), ("section", "erreur", "TEXT")):
            if colonne not in [c[1] for c in self._db.execute(f"PRAGMA table_info({table})")]:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {defn}")
        self._db.commit()

    # ------------------------------------------------------------------ réception
    def recevoir(self, meta: dict, rendu: bytes, source: bytes | None) -> dict:
        pid, sid = str(meta.get("id", "")), str(meta.get("section", ""))
        if not ID.match(pid) or not ID.match(sid):
            raise ErreurPrise("Identifiant de prise ou de section invalide.")
        mode = meta.get("mode")
        if mode not in MODES:
            raise ErreurPrise("Mode inconnu.")
        for nom, contenu in (("rendu", rendu), ("source", source)):
            if contenu is None:
                continue
            if len(contenu) > TAILLE_MAX:
                raise ErreurPrise(f"Fichier {nom} trop lourd.")
            if not contenu.startswith(JPEG):
                raise ErreurPrise(f"Le fichier {nom} n'est pas un JPEG.")
        if not rendu:
            raise ErreurPrise("Image rendue absente.")
        with self._verrou:
            deja = self._db.execute("SELECT taille_rendu FROM prise WHERE id=?", (pid,)).fetchone()
            if deja:
                if deja["taille_rendu"] != len(rendu):
                    raise ErreurPrise("Cet identifiant de prise est déjà pris par une autre image.")
                return {"ok": True, "id": pid, "deja": True}
            dossier = self.dossier / "attente" / sid
            dossier.mkdir(parents=True, exist_ok=True)
            self._ecrire(dossier / f"{pid}-rendu.jpg", rendu)
            if source:
                self._ecrire(dossier / f"{pid}-source.jpg", source)
            maintenant = datetime.now().astimezone().isoformat(timespec="seconds")
            self._db.execute("INSERT OR IGNORE INTO section(id, mode, creee_le) VALUES (?,?,?)", (sid, mode, maintenant))
            self._db.execute(
                "INSERT INTO prise(id, section_id, ordre, prise_le, recue_le, coins, rotation, filtre, intensite,"
                " taille_rendu, taille_source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, sid, int(meta.get("ordre", 0)), str(meta.get("prise_le") or maintenant), maintenant,
                 json.dumps(meta.get("coins")) if meta.get("coins") is not None else None,
                 int(meta.get("rotation", 0)) % 4, meta.get("filtre"), meta.get("intensite"),
                 len(rendu), len(source or b"")))
            self._db.commit()
        return {"ok": True, "id": pid, "deja": False}

    @staticmethod
    def _ecrire(chemin: Path, contenu: bytes) -> None:
        tmp = chemin.with_suffix(".part")
        with open(tmp, "wb") as f:
            f.write(contenu)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, chemin)

    # ------------------------------------------------------------------ lecture
    def sections(self) -> list[dict]:
        """Sections à traiter : prises encore en attente, envoi en cours ou envoi incomplet."""
        lignes = self._db.execute("""
            SELECT s.id, s.mode, s.creee_le, s.statut, s.album, s.tag, s.progression, s.erreur, s.etapes,
                   SUM(p.statut = 'attente') AS prises, SUM(p.statut = 'envoyee') AS envoyees,
                   SUM(p.erreur IS NOT NULL AND p.statut = 'attente') AS en_erreur, MAX(p.recue_le) AS derniere
            FROM section s JOIN prise p ON p.section_id = s.id
            GROUP BY s.id HAVING prises > 0 OR s.statut IN ('envoi', 'incomplete')
            ORDER BY s.creee_le DESC""").fetchall()
        sortie = []
        for l in lignes:
            d = dict(l)
            d["etapes"] = json.loads(d["etapes"]) if d["etapes"] else []
            sortie.append(d)
        return sortie

    def section(self, sid: str) -> dict | None:
        l = self._db.execute("SELECT * FROM section WHERE id=?", (sid,)).fetchone()
        return dict(l) if l else None

    def prises_a_envoyer(self, sid: str) -> list[dict]:
        lignes = self._db.execute(
            "SELECT * FROM prise WHERE section_id=? AND statut IN ('attente', 'envoyee') ORDER BY ordre, prise_le",
            (sid,)).fetchall()
        return [dict(l) for l in lignes]

    def maj_section(self, sid: str, **champs) -> None:
        if "etapes" in champs and not isinstance(champs["etapes"], (str, type(None))):
            champs["etapes"] = json.dumps(champs["etapes"])
        cles = ", ".join(f"{k}=?" for k in champs)
        with self._verrou:
            self._db.execute(f"UPDATE section SET {cles} WHERE id=?", (*champs.values(), sid))
            self._db.commit()

    def maj_prise(self, pid: str, **champs) -> None:
        cles = ", ".join(f"{k}=?" for k in champs)
        with self._verrou:
            self._db.execute(f"UPDATE prise SET {cles} WHERE id=?", (*champs.values(), pid))
            self._db.commit()

    def tourner(self, pid: str, rotation: int) -> bool:
        with self._verrou:
            n = self._db.execute("UPDATE prise SET rotation=? WHERE id=? AND statut='attente'", (int(rotation) % 4, pid)).rowcount
            self._db.commit()
        return n > 0

    def envoyees(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM prise WHERE statut='envoyee'").fetchone()[0]

    # ------------------------------------------------------------------ réglages (écran Réglages)
    def reglage(self, cle: str) -> str | None:
        l = self._db.execute("SELECT valeur FROM reglage WHERE cle=?", (cle,)).fetchone()
        return l["valeur"] if l else None

    def regler(self, cle: str, valeur: str) -> None:
        with self._verrou:
            self._db.execute("INSERT INTO reglage(cle, valeur) VALUES (?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur",
                             (cle, valeur))
            self._db.commit()

    # ------------------------------------------------------------------ journal des écritures
    def noter(self, sid: str, action: str, details: dict) -> int:
        quand = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._verrou:
            c = self._db.execute("INSERT INTO journal(quand, section_id, action, details) VALUES (?,?,?,?)",
                                 (quand, sid, action, json.dumps(details, ensure_ascii=False)))
            self._db.commit()
            return c.lastrowid

    def journal(self, limite: int = 50) -> list[dict]:
        lignes = self._db.execute("SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(l, details=json.loads(l["details"])) for l in lignes]

    def entree(self, jid: int) -> dict | None:
        l = self._db.execute("SELECT * FROM journal WHERE id=?", (jid,)).fetchone()
        return dict(l, details=json.loads(l["details"])) if l else None

    def marquer_annule(self, jid: int) -> None:
        quand = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._verrou:
            self._db.execute("UPDATE journal SET annule_le=? WHERE id=?", (quand, jid))
            self._db.commit()

    def prises(self, section: str) -> list[dict]:
        lignes = self._db.execute(
            "SELECT id, ordre, prise_le, rotation, filtre, taille_rendu, taille_source, erreur FROM prise"
            " WHERE section_id=? AND statut='attente' ORDER BY ordre, prise_le", (section,)).fetchall()
        return [dict(l) for l in lignes]

    def fichier(self, pid: str, quoi: str = "rendu") -> Path | None:
        if not ID.match(pid) or quoi not in ("rendu", "source"):
            return None
        ligne = self._db.execute("SELECT section_id FROM prise WHERE id=?", (pid,)).fetchone()
        if not ligne:
            return None
        chemin = self.dossier / "attente" / ligne["section_id"] / f"{pid}-{quoi}.jpg"
        return chemin if chemin.is_file() else None

    def vignette(self, pid: str, cote: int = 480) -> Path | None:
        """0.5.1 : petite image pour la revue (la grille chargeait les rendus de 4000 px, que Safari sur iPhone
        n'arrive pas toujours à afficher en nombre). Faite une fois, gardée à côté du rendu."""
        rendu = self.fichier(pid, "rendu")
        if not rendu:
            return None
        chemin = rendu.with_name(f"{pid}-vignette.jpg")
        if not chemin.is_file():
            import io
            from PIL import Image
            with Image.open(rendu) as im:
                im.draft("RGB", (cote, cote))          # décodage réduit : rapide, peu de mémoire
                im = im.convert("RGB")
                im.thumbnail((cote, cote))
                tampon = io.BytesIO()
                im.save(tampon, "JPEG", quality=80)
            self._ecrire(chemin, tampon.getvalue())
        return chemin

    def en_attente(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM prise WHERE statut='attente'").fetchone()[0]

    # ------------------------------------------------------------------ abandon (avant tout envoi)
    def retirer(self, pid: str) -> bool:
        with self._verrou:
            ligne = self._db.execute("SELECT section_id, statut FROM prise WHERE id=?", (pid,)).fetchone()
            if not ligne or ligne["statut"] != "attente":
                return False
            for quoi in ("rendu", "source", "vignette"):
                (self.dossier / "attente" / ligne["section_id"] / f"{pid}-{quoi}.jpg").unlink(missing_ok=True)
            self._db.execute("DELETE FROM prise WHERE id=?", (pid,))
            self._db.commit()
            return True
