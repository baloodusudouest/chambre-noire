"""Serveur de démonstration pour les tests d'écran : vraie appli, faux Immich (aucun réseau).

python -m tools.demo  →  http://127.0.0.1:8100 , mot de passe « demonstration-12 »
DEMO_PERMISSIONS=manque : la clé n'a pas queue.update (voyant orange dans Connexion).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx
import uvicorn

from app import config as config_mod
from app import main
from tests.faux_immich import FauxImmich, TOUTES

perms = [p for p in TOUTES if p != "queue.update"] if os.environ.get("DEMO_PERMISSIONS") == "manque" else None
main.ETAT["cfg"] = config_mod.Config(password="demonstration-12", data=Path(tempfile.mkdtemp()),
                                     static=Path(main.__file__).parent / "static",
                                     immich_url="http://immich", immich_cle="cle-de-test", ml_url="http://ml",
                                     attente_connexion=False)
main.ETAT["transport"] = httpx.MockTransport(FauxImmich(permissions=perms))

if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ.get("DEMO_PORT", "8100")), log_level="warning")
