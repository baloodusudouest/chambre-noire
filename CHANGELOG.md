# Journal des versions

## 0.5.1 — 16 novembre 2026
- **Revue : toutes les photos s'affichent.** La grille chargeait le rendu complet de chaque prise (jusqu'à 4000 px, plusieurs Mo) ; sur iPhone, une partie restait en image cassée (signalé par Julien). Elle charge maintenant une vignette de 480 px (`/api/prises/{id}/vignette.jpg`), faite une fois sur le NAS à partir du rendu et gardée à côté (retirée avec la prise). L'envoi dans Immich utilise toujours le rendu complet.
- Une vignette qui ne se charge pas est redemandée seule jusqu'à 3 fois, puis laisse un bouton « toucher pour réessayer » au lieu de l'image cassée.
- Tests : vignette ≤ 480 px et retirée avec la prise ; dans le parcours caméra, toutes les vignettes de la revue chargées. 42 tests.

## 0.5.0 — 15 novembre 2026
- **Millésime suit les noms réglés ici.** Nouvelle adresse `GET /externe/noms` (jeton `CHAMBRE_NOIRE_JETON_MILLESIME`, vide : fermée, comparaison en temps constant) : libellé, album et tag des non datées. Millésime ≥ 2.9.0 la lit à chaque relecture d'Immich : le libellé ne se règle plus qu'à un endroit, Réglages › Noms dans Immich. Rien d'autre n'est donné (ni photo, ni journal).
- **Connexion : tuile Millésime** (adresse ouverte ou fermée, dernière lecture).
- Tests : adresse fermée sans jeton, jeton refusé, noms suivis après un changement dans Réglages, libellé absent. 41 tests.

## 0.4.1 — 15 novembre 2026
- **Réglages › Noms dans Immich** : le libellé des albums et des tags, et l'album des non datées, se règlent dans l'appli (gardés dans la base, `PUT /api/reglages`), avec un exemple des noms produits. Utilisés dès le prochain envoi ; rien n'est renommé dans Immich. Demandé par Julien.
- `CHAMBRE_NOIRE_LIBELLE` et `CHAMBRE_NOIRE_ALBUM_NON_DATEES` deviennent facultatives : valeur de départ seulement.
- Le libellé refuse « / » (séparateur des niveaux du tag).
- Tests : libellé réglé puis utilisé à l'envoi, gardé après redémarrage ; écran Réglages (PC, iPhone). 40 tests.

## 0.4.0 — 15 novembre 2026
Revue, date et envoi dans Immich (étape 4 du plan).
- **Revue** d'une section dans « À traiter » : vignettes, ↺ ↻ pour tourner (quart de tour), ✕ pour retirer.
- **Date** : mois (ou « Mois inconnu ») et année, ou « Photos non datées » ; aperçu de l'album et du tag avant l'envoi.
- **Envoi** (en arrière-plan, progression affichée) : rotation écrite dans les pixels, date et tag dans le JPEG (EXIF + XMP, portage exact de Scan Immich : `app/metadonnees.py`), envoi, album « AAAA-MM <libellé> », tag « <libellé>/AAAA-MM », description = nom de l'album, lancement du rangement (`/api/jobs`, puis `/api/queues`). Non datées : 1er janvier 1900 en UTC (+00:00), album et tag que lit Millésime. Heure : celle de la séance dans la journée, +1 s par photo.
- **Incomplet** : une étape ratée (album, tag, description, rangement) ou une photo refusée laisse la section « incomplète » ; Relancer garde la date et ne renvoie jamais une photo déjà envoyée.
- **Journal des envois** (Réglages) avec **Annuler** : retire de l'album et du tag puis met à la corbeille d'Immich les seules photos de cet envoi ; les prises reviennent « à dater ».
- Nouvelle variable : `CHAMBRE_NOIRE_LIBELLE` (obligatoire pour envoyer), `CHAMBRE_NOIRE_ALBUM_NON_DATEES` (facultative). Pillow ajouté (rotation).
- Tests : 10 tests d'envoi contre un faux Immich (EXIF de mai 1987 en +02:00, non datées en +00:00, année seule, tag raté puis relance sans renvoi, ancienne adresse du rangement, Annuler limité au journal, lecture seule, libellé absent, date invalide) ; parcours complet en caméra simulée jusqu'à Annuler. 38 tests en tout. Jamais essayé contre le vrai Immich : noms des routes d'écriture et de la corbeille à confirmer.

## 0.3.1 — 15 novembre 2026
- Flash blanc à l'écran au moment exact de chaque prise, automatique ou au déclencheur (avant, seulement au déclencheur). Demandé par Julien après le premier essai sur l'iPhone, où la détection fonctionne.
- Test : la rafale simulée vérifie qu'un flash a lieu.

## 0.3.0 — 15 novembre 2026
Caméra et détection (étape 3 du plan).
- Écran **Scanner** : Rafale, 1 photo, Page d'album, puis caméra plein écran (caméra arrière, plus grande définition 4:3 ou 4K).
- Détection reprise **telle quelle** de Scan Immich v3.9 (`lib/scan/detection.js` : `findPrint`, `findPrintNested`, `quadFromHull`, `findPrintLines`, `orderPts`) et rendu (`lib/scan/rendu.js` : redressement, filtre « restauration » 70 %, grain à graine fixe). OpenCV.js 4.10 servi par l'appli (`/opencv.js`), aucun appel extérieur.
- Prise automatique quand le tirage est immobile 0,9 s et assez défini (1 800 px de grand côté ; 1 200 px par tirage en mode Page), bloquée en dessous ; déclencheur toujours disponible ; bouton de mode à côté du déclencheur ; « Terminer » mène à « À traiter ».
- Chaque prise (image rendue + image source + coins) part aussitôt dans la file d'envoi ; compteur « n prises · n sur le NAS ».
- Sections : une par rafale (jusqu'à « Terminer »), une par photo en mode 1 photo, une par page en mode Page.
- La caméra exige HTTPS : ouvrir Chambre noire par son adresse Tailscale (`tailscale serve`).
- Tests : 2 tests de caméra simulée (rafale : prise automatique jusqu'au NAS ; page : 4 tirages dans une section). 28 tests en tout. Essayée sur l'iPhone le 15/11/2026 : la détection fonctionne.
- Pas encore : rotation (étape 5 pour l'automatique ; à la main à l'étape 4), choix du filtre, date et envoi dans Immich (étape 4).

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
