# Chambre noire

Numériser à l'iPhone des tirages photo papier et les envoyer dans [Immich](https://immich.app), datés, tagués et rangés.
Appli maison auto-hébergée (FastAPI + Svelte 5 + Tailwind 4), partie du socle commun.

- Déploiement : service de `docker-compose.yml` dans la stack, variables de `.env.example`.
- Caméra : l'appli doit être ouverte en HTTPS (par exemple `tailscale serve`).
- Développement : `pip install -r requirements-dev.txt && python -m pytest -q` ; interface : `cd frontend && npm ci && npx vite build` ;
  démonstration avec un faux Immich : `python -m tools.demo`.
- À lire : `REPRISE.md`, `CHANGELOG.md`, `docs/dossier.md`.
