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
- Sauvegarde : la zone d'attente est dans ${DOCKER_ROOT}/chambre-noire, hors du dossier personnel sauvegardé :
  à ajouter à la sauvegarde (avis du conseil) ou à vider souvent en envoyant.

## Prochaine étape (plan revu par le conseil)
1. ~~Squelette~~ (fait, vérifié sur le NAS).
2. ~~Zone d'attente~~ (0.2.0).
3. Caméra et détection : portage de `findPrint`, `findPrintNested`, `quadFromHull`, `findPrintLines` et du rendu
   (repris tels quels de Scan Immich v3.9), trois modes, banc d'images réelles des fonds difficiles.
4. Envoi : EXIF/XMP, album, tag, description (nom d'album), rangement ; journal + Annuler limité au journal.
5. Orientation sur le NAS (ML d'Immich).
6. Bascule : rafales de Scan Immich envoyées, remplacement direct de l'adresse HTTPS (choix de Julien).

## Décisions
- Rendu final dans l'iPhone (même code que l'aperçu) ; le NAS écrit les métadonnées, envoie, range.
- Provenance : seulement le nom de l'album dans la description.
- Les noms d'album et de tag viennent de la stack (aucun nom réel dans ce dépôt public). Les photos
  non datées gardent l'album et le tag que lit Millésime.

## Pièges
- `pages/Connexion.svelte` est la page du mot de passe ; l'écran « Connexion » est `pages/Services.svelte`.
- La caméra exige HTTPS (tailscale serve) et refuse un cadre servi en http : la tuile de l'Anneau s'ouvre à côté.
- Un seul service par port `tailscale serve` : vérifier `tailscale serve status` avant d'attribuer un port.
- La clé Immich a besoin de `queue.update` (ou `job.create`) pour lancer le rangement (erreur 403 vécue le 31/10).
