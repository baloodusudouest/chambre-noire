# Journal des versions

## 0.2.0 — 15 novembre 2026
Zone d'attente (étape 2 du plan).
- **NAS** : `POST /api/prises` reçoit chaque prise (image rendue + source + coins, rotation, filtre) dès qu'elle est faite. Identifiant fixé par l'iPhone : un renvoi répond « déjà reçue », jamais de doublon. Fichiers écrits en entier puis renommés ; base SQLite `chambre-noire.db` dans `/data`. Prises consultables et retirables tant qu'elles ne sont pas envoyées.
- **iPhone** : file d'envoi (`lib/fileEnvoi.js`). Chaque prise est d'abord gardée dans le stockage de l'iPhone et n'en est effacée qu'après l'accusé de réception du NAS. Réseau coupé : nouvel essai de 2 s à 30 s ; session expirée : la file attend la connexion puis repart ; prise refusée : gardée et montrée.
- Écran **À traiter** : prises encore sur l'iPhone, prises refusées, sections reçues à dater (avec leurs vignettes).
- `/health` compte les prises en attente.
- Tests : 8 tests de la zone d'attente (renvoi sans doublon, entrées refusées, redémarrage), 1 test d'écran de la file (hors ligne puis appli fermée, session perdue). Rien n'est écrit dans Immich.
- Pas encore de caméra : les prises arriveront de l'écran Scanner à l'étape 3.

## 0.1.0 — essai réel
- Déployée sur le NAS le 15/11/2026 : écran Connexion vert avec la vraie clé (Immich 3.4.1), selon Julien.

## 0.1.0 — 15 novembre 2026
Squelette (étape 1 du plan, `docs/dossier.md` § 6), parti du socle 0.4.4.
- Nom, couleur (cyan révélateur `#4fc1c9`), icône, port 8100, image `ghcr.io/baloodusudouest/chambre-noire`.
- Mot de passe commun obligatoire (`CHAMBRE_NOIRE_PASSWORD`), cookie commun de l'Anneau accepté, mode lecture seule (`CHAMBRE_NOIRE_LECTURE_SEULE`).
- `/health` publique, sans aucun nom : version, prises en attente et photos envoyées (0 pour l'instant).
- Écran **Connexion** : Immich (version, clé, permissions utiles aux étapes suivantes, lues par `GET /api/api-keys/me`) et le service d'apprentissage d'Immich (temps de réponse). Rien n'est écrit dans Immich.
- Écran **Scanner** : annonce la prise de vue (étape 3) ; Scan Immich reste l'outil de numérisation d'ici là.
- Tests : 15 tests d'API sans réseau (faux Immich 3.x), 2 tests d'écran (PC, iPhone) par le serveur de démonstration.
- Jamais essayé contre le vrai Immich : la lecture des permissions (`/api/api-keys/me`) et leurs noms sont à confirmer sur l'installation.
