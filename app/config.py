"""Réglages lus dans l'environnement du conteneur. Aucune valeur personnelle dans le code :
les noms d'album et de tag, les adresses et la clé viennent des variables de la stack."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import maison

APPLI = "chambre-noire"
PREFIXE = "CHAMBRE_NOIRE_"


def _env(nom: str, defaut: str = "") -> str:
    return os.environ.get(PREFIXE + nom, defaut).strip()


@dataclass(frozen=True)
class Config:
    password: str
    data: Path
    static: Path
    immich_url: str = "http://immich_server:2283"
    immich_cle: str = ""
    ml_url: str = "http://immich_machine_learning:3003"
    attente_connexion: bool = True   # délai anti-essais ; coupé dans les tests
    lecture_seule: bool = False      # l'appli lit tout mais n'écrit rien dans Immich
    # Valeurs de départ seulement (0.4.1) : le libellé et l'album des non datées se règlent dans l'appli (Réglages).
    libelle: str = ""                # « Numérisation X » : album « AAAA-MM <libellé> », tag « <libellé>/AAAA-MM »
    album_non_datees: str = ""       # vide : « Non datées <libellé> » (doit rester celui que lit Millésime)
    jeton_millesime: str = ""        # 0.5.0 : Millésime lit /externe/noms avec ce jeton ; vide : adresse fermée
    origine_lecture_seule: str = ""  # 0.6.0 : « maison » (MAISON_LECTURE_SEULE), « appli » (variable propre) ou « »


def charger() -> Config:
    mot_de_passe = maison.mot_de_passe(PREFIXE + "PASSWORD")      # 0.6.0 : MAISON_PASSWORD, repli sur l'ancien nom
    if len(mot_de_passe) < 12:
        raise SystemExit("MAISON_PASSWORD (ou CHAMBRE_NOIRE_PASSWORD) est absent ou trop court (12 caractères au moins) : "
                         "Chambre noire ne démarre pas.")
    return Config(
        password=mot_de_passe,
        data=Path(_env("DATA", "/data")),
        static=Path(__file__).parent / "static",
        immich_url=_env("IMMICH_URL", "http://immich_server:2283").rstrip("/"),
        immich_cle=_env("IMMICH_CLE"),
        ml_url=_env("ML_URL", "http://immich_machine_learning:3003").rstrip("/"),
        # 0.6.0 : MAISON_LECTURE_SEULE pour toute la maison ; CHAMBRE_NOIRE_LECTURE_SEULE (oui/non) l'emporte
        lecture_seule=maison.lecture_seule(PREFIXE + "LECTURE_SEULE"),
        origine_lecture_seule=maison.origine_lecture_seule(PREFIXE + "LECTURE_SEULE"),
        libelle=_env("LIBELLE"),
        album_non_datees=_env("ALBUM_NON_DATEES"),
        jeton_millesime=_env("JETON_MILLESIME"),   # ancien jeton propre ; MAISON_JETON est lu à chaque demande (main.py)
    )
