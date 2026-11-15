# Reprise — Chambre noire

À lire en premier ; mis à jour dans le même commit que le code.

## Ce que c'est
Réécriture sur le socle de « Scan Immich » (page unique servie par nginx, en service depuis le 28/10/2026) :
numériser à l'iPhone les tirages papier d'albums familiaux et les envoyer dans Immich, datés, tagués, rangés.
Dossier complet (besoin, technique, parcours, design, données, plan, écarts, avis du conseil) : `docs/dossier.md`.

## État (15/11/2026)
- **0.1.0** : squelette. Connexion (Immich, permissions de la clé, apprentissage), Réglages, Scanner (annonce).
  17 tests verts en local (15 API, 2 écran). Rien d'essayé sur la vraie installation.

## Prochaine étape (plan revu par le conseil)
1. ~~Squelette~~ → déployer à côté de Scan Immich (port 8100), vérifier Connexion avec la vraie clé.
2. Zone d'attente : file d'envoi de l'iPhone avec accusé de réception, identifiant par prise, SQLite, reprise.
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
