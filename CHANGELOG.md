# Journal des versions

## 0.1.0 — 15 novembre 2026
Squelette (étape 1 du plan, `docs/dossier.md` § 6), parti du socle 0.4.4.
- Nom, couleur (cyan révélateur `#4fc1c9`), icône, port 8100, image `ghcr.io/baloodusudouest/chambre-noire`.
- Mot de passe commun obligatoire (`CHAMBRE_NOIRE_PASSWORD`), cookie commun de l'Anneau accepté, mode lecture seule (`CHAMBRE_NOIRE_LECTURE_SEULE`).
- `/health` publique, sans aucun nom : version, prises en attente et photos envoyées (0 pour l'instant).
- Écran **Connexion** : Immich (version, clé, permissions utiles aux étapes suivantes, lues par `GET /api/api-keys/me`) et le service d'apprentissage d'Immich (temps de réponse). Rien n'est écrit dans Immich.
- Écran **Scanner** : annonce la prise de vue (étape 3) ; Scan Immich reste l'outil de numérisation d'ici là.
- Tests : 15 tests d'API sans réseau (faux Immich 3.x), 2 tests d'écran (PC, iPhone) par le serveur de démonstration.
- Jamais essayé contre le vrai Immich : la lecture des permissions (`/api/api-keys/me`) et leurs noms sont à confirmer sur l'installation.
