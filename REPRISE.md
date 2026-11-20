# Reprise — Chambre noire

À lire en premier ; mis à jour dans le même commit que le code.

## Ce que c'est
- **0.9.1 (20/11/2026)** : copies communes du socle 0.11.1 (titre « Pour le relier » quand le réglage est dans l'appli).
Réécriture sur le socle de « Scan Immich » (page unique servie par nginx, en service depuis le 28/10/2026) :
numériser à l'iPhone les tirages papier d'albums familiaux et les envoyer dans Immich, datés, tagués, rangés.
Dossier complet (besoin, technique, parcours, design, données, plan, écarts, avis du conseil) : `docs/dossier.md`.

## État (20/11/2026, version 0.9.0)
- **0.1.0** : squelette, déployé et vérifié sur le NAS (Connexion verte avec la vraie clé).
- **0.2.0** : zone d'attente (NAS : réception idempotente, SQLite, fichiers dans /data/attente ; iPhone : file
  d'envoi avec accusé de réception) et écran À traiter. 26 tests verts en local. Pas encore essayée sur le NAS.
- **0.3.0** : caméra et détection (code de Scan Immich repris tel quel), trois modes, prises envoyées au NAS.
  28 tests verts (dont caméra simulée). Essayée sur l'iPhone (HTTPS :8445 par tailscale serve) : détection OK.
- **0.3.1** : flash à l'écran à chaque prise.
- **0.4.0** : revue (rotation, retrait), date, envoi dans Immich (EXIF/XMP, album, tag, description, rangement),
  journal + Annuler. 38 tests verts. Jamais essayé contre le vrai Immich : faire un premier envoi en lecture
  seule coupée, sur 2 photos, et vérifier album, tag, date, description, rangement ; puis essayer Annuler.
- **0.4.1** : libellé et album des non datées réglés dans l'appli (Réglages), la stack ne donne que le départ.
- **0.6.0** (16/11/2026) : variables communes (module `app/maison.py`, copie du socle 0.5.0 : ne pas le modifier ici).
  `config.charger` lit `MAISON_PASSWORD` (repli `CHAMBRE_NOIRE_PASSWORD`) et `MAISON_LECTURE_SEULE` (`CHAMBRE_NOIRE_LECTURE_SEULE`
  l'emporte ; champ `origine_lecture_seule`, rendu par `/api/session` et `/api/services`) ; `/externe/noms` accepte
  `MAISON_JETON` / `MAISON_JETON_ANCIEN` en plus de `CHAMBRE_NOIRE_JETON_MILLESIME` (`jetons_millesime()` de `main.py`).
  Jamais essayé sur la vraie installation : les nouvelles variables ne sont pas encore dans la stack (tout passe par les anciens noms).
- **0.7.0** (16/11/2026) : réglages dans l'appli, sauvegarde et restauration ; anciens noms retirés.
  - `app/maison.py` : copie du module commun **contrat 2** (socle), non retouchée (test d'empreinte).
  - Réglages d'usage : `libelle` et `album_non_datees`, toujours dans la table `reglage` de `chambre-noire.db` (`Attente.reglage/regler`).
    `main.reprendre_reglages` (au démarrage) : une clé absente de la base prend la valeur de `CHAMBRE_NOIRE_LIBELLE` /
    `CHAMBRE_NOIRE_ALBUM_NON_DATEES` (ou vide) et est écrite : la variable n'est plus jamais lue ensuite ; ligne `reglage` au journal.
    `valider_reglages` (texte, libellé obligatoire sans « / », 80/120 caractères) sert à `PUT /api/reglages` (partiel) et à la restauration ; 400.
  - `GET /externe/sauvegarde` (jeton commun seul, `maison.sauvegarde`, `EXCLUS_SAUVEGARDE = ("millesime_vu",)`) ;
    `GET/POST /api/restaurer` (`_demander_anneau` : 400 date, 404 rien, 503 Anneau injoignable ou `MAISON_JETON` absent) ;
    tuile « Restaurer les réglages » dans `pages/Reglages.svelte` ; ligne `restauration` au journal. Faux Anneau : `ETAT["lire_anneau"]`
    (tests, `tools/demo.py`).
  - `config.charger` : `maison.mot_de_passe()` sans ancien nom ; plus de `jeton_millesime` ; `/externe/noms` : `maison.jetons()` seul.
  - Variables encore lues : `MAISON_PASSWORD`, `MAISON_JETON` (+ `MAISON_JETON_ANCIEN`), `MAISON_LECTURE_SEULE`, `MAISON_ANNEAU_URL` (facultative,
    défaut `http://anneau:8094`), `CHAMBRE_NOIRE_LECTURE_SEULE`, `CHAMBRE_NOIRE_IMMICH_CLE`, `CHAMBRE_NOIRE_IMMICH_URL`, `CHAMBRE_NOIRE_ML_URL`,
    `CHAMBRE_NOIRE_DATA` (défaut `/data`) ; `CHAMBRE_NOIRE_LIBELLE` / `CHAMBRE_NOIRE_ALBUM_NON_DATEES` au premier démarrage seulement.
  - À retirer de la stack (après le premier démarrage) : `CHAMBRE_NOIRE_PASSWORD`, `CHAMBRE_NOIRE_JETON_MILLESIME`, `CHAMBRE_NOIRE_LIBELLE`,
    `CHAMBRE_NOIRE_ALBUM_NON_DATEES`.
  - **Déploiement en deux temps** : d'abord la nouvelle image avec la stack actuelle (les réglages sont repris des anciennes variables au
    premier démarrage), vérifier Réglages, puis la nouvelle stack sans les anciennes lignes. `MAISON_PASSWORD` et `MAISON_JETON` doivent
    déjà être posés pour Chambre noire (sinon : refus de démarrer, porte de Millésime fermée). Millésime doit envoyer `MAISON_JETON`.
  - Jamais essayé sur la vraie installation (ni la reprise, ni la sauvegarde lue par l'Anneau, ni la restauration).
- **0.5.1** : vignettes de 480 px dans la revue (`Attente.vignette`), nouvel essai automatique ; image cassée signalée par Julien sur iPhone.
- **0.5.0** : `/externe/noms` (jeton `CHAMBRE_NOIRE_JETON_MILLESIME`) lu par Millésime 2.9.0 ; tuile Millésime dans Connexion.
- Sauvegarde : la zone d'attente est dans ${DOCKER_ROOT}/chambre-noire, hors du dossier personnel sauvegardé.
  Choix de Julien (18/11/2026) : la vider souvent plutôt que la sauvegarder. **0.7.6** : purge automatique des fichiers
  déjà envoyés après `purge_jours` jours (réglage, 30 par défaut), réception refusée (507) sous 1 Go libre ; plafond de
  64 Mpx lu dans l'en-tête. Jamais essayé sur la vraie installation.
- **0.8.0** (18/11/2026) : santé des tâches de fond (socle 0.9.0, `app/maison.py` copie signée non retouchée).
  Tâches dans `maison.TACHES` : `purge` (régulière 21 600 s, `boucle_purge`), `envoi-immich` (à la demande, `Envoyeur._envoyer`),
  `copie-des-bases` (régulière 86 400 s, `maison.planifier_copie` lancée dans `cycle`, annulée à l'arrêt). Copie de
  `chambre-noire.db` à 02:00 heure de Paris dans `/data/copies` (`chambre-noire-derniere.db`, `copie.json`).
  `/health` ajoute `version_socle`, `taches`, `copie_base` (messages seulement avec `MAISON_JETON` ou une session). Un seul worker uvicorn.
  Tests : `tests/test_sante.py`. Jamais essayé sur la vraie installation (ni la copie de nuit, ni une restauration depuis la copie).
- **0.9.0** (20/11/2026) : fiches « Connexion » communes (contrat 3, socle 0.11.0). Écran `$lib/services/Services.svelte`
  (copie signée du socle, ne pas la retoucher) ; `pages/Services.svelte` retiré. `main.py`, section « fiches Connexion » :
  `SERVICES` = `immich` (guide : version, libellé, clé, permissions manquantes, lu dans le dernier essai `ETAT["immich_dernier"]`),
  `immich-ml` (Visages d'Immich), `millesime` (genre maison ; essai sans réseau sur `millesime_vu`, `SERVICES.noter` dans `/externe/noms`).
  `maison.monter_services` après la garde. `ANNEAU_CLE` (facultative) ouvre `/api/maison/services`. Ancienne `GET /api/services`
  gardée, à retirer en 0.10.0. Tests : `tests/test_fiches_connexion.py`. Jamais essayé sur la vraie installation.

## Prochaine étape (plan revu par le conseil)
1. ~~Squelette~~ (fait, vérifié sur le NAS).
2. ~~Zone d'attente~~ (0.2.0).
3. ~~Caméra et détection~~ (0.3.0). Reste : banc d'images réelles des fonds difficiles (tests/images).
4. ~~Envoi~~ (0.4.0).
5. Orientation sur le NAS (ML d'Immich).
6. Bascule : rafales de Scan Immich envoyées, remplacement direct de l'adresse HTTPS (choix de Julien).

## Décisions
- Rendu final dans l'iPhone (même code que l'aperçu) ; le NAS écrit les métadonnées, envoie, range.
- Provenance : seulement le nom de l'album dans la description.
- Les noms d'album et de tag se règlent dans l'appli (0.7.0 : plus dans la stack ; aucun nom réel dans ce dépôt public). Les photos
  non datées gardent l'album et le tag que lit Millésime.

## Pièges
- Une photo renvoyée après Annuler avec une autre date est une nouvelle photo (autre date dans le fichier) ;
  l'ancienne reste dans la corbeille d'Immich. Même date : Immich répond « duplicate », l'appli la restaure.
- `exiger_ecriture` répond 409 (pas 403) en lecture seule.
- Les tests de caméra baissent les seuils de définition (`window.__reglagesCamera`, seulement avec `?essai`) :
  les caméras simulées font 1440 px. Ne pas baisser `REGLAGES.minPx` dans le code.
- `wait_for_function` de Playwright n'attend pas une promesse : interroger le NAS en Python (`_attendre`).
- `pages/Connexion.svelte` est la page du mot de passe ; l'écran « Connexion » est l'écran commun `lib/services/Services.svelte` (0.9.0).
- La caméra exige HTTPS (tailscale serve) et refuse un cadre servi en http : la tuile de l'Anneau s'ouvre à côté.
- Un seul service par port `tailscale serve` : vérifier `tailscale serve status` avant d'attribuer un port.
- La clé Immich a besoin de `queue.update` (ou `job.create`) pour lancer le rangement (erreur 403 vécue le 31/10).
