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
        """)

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
        lignes = self._db.execute("""
            SELECT s.id, s.mode, s.creee_le, s.statut, COUNT(p.id) AS prises, MAX(p.recue_le) AS derniere
            FROM section s LEFT JOIN prise p ON p.section_id = s.id AND p.statut = 'attente'
            GROUP BY s.id HAVING prises > 0 ORDER BY s.creee_le DESC""").fetchall()
        return [dict(l) for l in lignes]

    def prises(self, section: str) -> list[dict]:
        lignes = self._db.execute(
            "SELECT id, ordre, prise_le, rotation, filtre, taille_rendu, taille_source FROM prise"
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

    def en_attente(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM prise WHERE statut='attente'").fetchone()[0]

    # ------------------------------------------------------------------ abandon (avant tout envoi)
    def retirer(self, pid: str) -> bool:
        with self._verrou:
            ligne = self._db.execute("SELECT section_id, statut FROM prise WHERE id=?", (pid,)).fetchone()
            if not ligne or ligne["statut"] != "attente":
                return False
            for quoi in ("rendu", "source"):
                (self.dossier / "attente" / ligne["section_id"] / f"{pid}-{quoi}.jpg").unlink(missing_ok=True)
            self._db.execute("DELETE FROM prise WHERE id=?", (pid,))
            self._db.commit()
            return True
