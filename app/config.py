"""Réglages lus dans l'environnement du conteneur. Aucune valeur personnelle dans le code :
les adresses et la clé viennent des variables de la stack ; les noms d'album et de tag se règlent dans l'appli
(0.7.0 : les anciennes variables ne sont reprises qu'au premier démarrage)."""
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
    # 0.7.0 : reprises UNE fois, au premier démarrage, dans les réglages de l'appli (Réglages › Noms dans Immich) ;
    # ensuite ces variables ne sont plus lues : seul l'écran Réglages fait foi.
    libelle: str = ""                # « Numérisation X » : album « AAAA-MM <libellé> », tag « <libellé>/AAAA-MM »
    album_non_datees: str = ""       # vide : « Non datées <libellé> » (doit rester celui que lit Millésime)
    origine_lecture_seule: str = ""  # 0.6.0 : « maison » (MAISON_LECTURE_SEULE), « appli » (variable propre) ou « »


def charger() -> Config:
    mot_de_passe = maison.mot_de_passe()      # 0.7.0 : MAISON_PASSWORD seul (l'ancien nom n'est plus lu)
    if len(mot_de_passe) < 12:
        raise SystemExit("MAISON_PASSWORD est absent ou trop court (12 caractères au moins) : "
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
        libelle=_env("LIBELLE"),                   # reprise au premier démarrage seulement (main.reprendre_reglages)
        album_non_datees=_env("ALBUM_NON_DATEES"),
    )
