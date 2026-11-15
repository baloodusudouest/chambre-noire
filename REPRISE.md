# Reprise — Chambre noire

À lire en premier ; mis à jour dans le même commit que le code.

## Ce que c'est
Réécriture sur le socle de « Scan Immich » (page unique servie par nginx, en service depuis le 28/10/2026) :
numériser à l'iPhone les tirages papier d'albums familiaux et les envoyer dans Immich, datés, tagués, rangés.
Dossier complet (besoin, technique, parcours, design, données, plan, écarts, avis du conseil) : `docs/dossier.md`.

## État (15/11/2026)
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
- **0.5.1** : vignettes de 480 px dans la revue (`Attente.vignette`), nouvel essai automatique ; image cassée signalée par Julien sur iPhone.
- **0.5.0** : `/externe/noms` (jeton `CHAMBRE_NOIRE_JETON_MILLESIME`) lu par Millésime 2.9.0 ; tuile Millésime dans Connexion.
- Sauvegarde : la zone d'attente est dans ${DOCKER_ROOT}/chambre-noire, hors du dossier personnel sauvegardé :
  à ajouter à la sauvegarde (avis du conseil) ou à vider souvent en envoyant.

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
- Les noms d'album et de tag viennent de la stack (aucun nom réel dans ce dépôt public). Les photos
  non datées gardent l'album et le tag que lit Millésime.

## Pièges
- Une photo renvoyée après Annuler avec une autre date est une nouvelle photo (autre date dans le fichier) ;
  l'ancienne reste dans la corbeille d'Immich. Même date : Immich répond « duplicate », l'appli la restaure.
- `exiger_ecriture` répond 409 (pas 403) en lecture seule.
- Les tests de caméra baissent les seuils de définition (`window.__reglagesCamera`, seulement avec `?essai`) :
  les caméras simulées font 1440 px. Ne pas baisser `REGLAGES.minPx` dans le code.
- `wait_for_function` de Playwright n'attend pas une promesse : interroger le NAS en Python (`_attendre`).
- `pages/Connexion.svelte` est la page du mot de passe ; l'écran « Connexion » est `pages/Services.svelte`.
- La caméra exige HTTPS (tailscale serve) et refuse un cadre servi en http : la tuile de l'Anneau s'ouvre à côté.
- Un seul service par port `tailscale serve` : vérifier `tailscale serve status` avant d'attribuer un port.
- La clé Immich a besoin de `queue.update` (ou `job.create`) pour lancer le rangement (erreur 403 vécue le 31/10).
