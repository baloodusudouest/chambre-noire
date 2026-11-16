# Chambre noire — dossier

> Numériser des tirages photo papier à l'iPhone et les envoyer dans Immich, datés, rangés et tagués.
> Réécriture sur le socle commun de **Scan Immich** (v3.8, page unique servie par nginx, en service depuis le 28/10/2026).
> Statut : dossier « tel que construit » + écarts + choix (grill du 15/11/2026), **passé au conseil le 15/11/2026** (voir `chambre-noire-conseil.md`). Décidé ensuite : v3.9 de Scan Immich d'abord, puis cette réécriture. Les points marqués *(conseil)* remplacent la première version.
> Dépôt public : aucune valeur réelle ici (noms d'album et de tag, chemins, adresses) ; elles passent par les variables de la stack.

## 1. Besoin

**Pourquoi.** Des centaines à quelques milliers de tirages des années 1980-2000, rangés dans des albums familiaux, à faire entrer dans Immich avec une date utile (mois et année), bien orientés, rangés par le modèle de stockage, sans compte développeur Apple.

**Ce que fait l'app en service (Scan Immich v3.8) :**
- caméra en direct dans Safari, détection du tirage, prise automatique quand il est stable et assez défini (blocage sous un seuil de pixels) ;
- trois modes : **Rafale** (prise à la chaîne → revue → date de la section → envoi groupé), **1 photo** (aperçu, date, envoi, enchaînement), **Page d'album** (1 à 4 tirages découpés par prise, date par page) ;
- redressement de perspective, filtres de restauration (couleurs passées, argentique, N&B, sépia), éditeur des coins ;
- orientation automatique par le ML d'Immich (points de repère du visage), puis heuristique du ciel, puis continuité ;
- envoi dans Immich : date dans l'EXIF, tags XMP, album « AAAA-MM <suffixe> », tag « <parent>/AAAA-MM », lancement de la migration du modèle de stockage ;
- photos non datées : date fictive 1900-01-01 (heure UTC « murale »), album et tag communs « non datées ».

**Choix de la réécriture (grill du 15/11/2026) :**

| Sujet | Choix |
|---|---|
| Nom, couleur | **Chambre noire**, cyan révélateur `#4fc1c9` |
| Technique | Réécriture sur le socle (FastAPI + Svelte 5 + Tailwind 4), mot de passe et cookie communs |
| Prises | **Envoyées au NAS tout de suite**, dans une zone d'attente de l'app ; rien n'entre dans Immich avant la date et la validation. *(conseil)* L'iPhone garde chaque prise dans une file d'envoi et ne l'efface qu'après l'accusé de réception du NAS ; identifiant unique par prise fixé par l'iPhone (pas de doublon à la relance) |
| Rendu | *(conseil)* **Dans l'iPhone** (même code que l'aperçu) ; le NAS reçoit le JPEG rendu + la source, écrit EXIF/XMP, envoie, range |
| Provenance | Nom de l'album dans la description de chaque photo Immich |
| Orientation | **Sur le NAS après la prise**, en tâche de fond (ML d'Immich) ; plus de flèche « HAUT » pendant la prise |
| Écrans | Scanner · À traiter · Connexion · Réglages |
| Annuler | Un envoi s'annule : retrait de l'album et du tag, puis corbeille d'Immich (30 jours). Jamais de suppression définitive. *(conseil)* Seulement des photos inscrites au journal de l'app |
| Liens | Tuile dans l'Anneau ; Millésime : seules les photos **non datées (1900)** le concernent, avec le tag et l'album qu'il lit déjà ; les photos datées restent ignorées par Millésime |
| Bascule | **Remplacement direct** (maintenu par Julien contre l'avis du conseil) : Chambre noire reprend l'adresse HTTPS `:8443`, Scan Immich est retiré de la stack. Avant : envoyer toutes les rafales encore dans Scan Immich |

**Hors périmètre :** recto/verso, visages nommés à la prise, dictée de souvenirs, Home Assistant (non retenu au grill).

## 2. Technique

### Tel que construit (Scan Immich v3.8)
- `index.html` unique (~2 600 lignes, JS sans framework) + `opencv.js` 4.10 (paquet npm `@techstark/opencv-js@4.10.0-release.1`), manifeste, icônes.
- Conteneur `nginx:alpine` : relais `/api/(assets|albums|tags|jobs|queues|server/ping)` vers Immich avec la clé API injectée par `envsubst` (`limit_except GET POST PUT`), `/ml/predict` vers le ML d'Immich, le reste de `/api/` refusé ; résolveur Docker pour suivre l'IP d'Immich.
- HTTPS par `tailscale serve` (obligatoire pour `getUserMedia`), une seule tâche DSM regroupe toutes les redirections (un service par port).
- Stockage des rafales dans IndexedDB ; modes 1 photo et Page non persistés.

### Cible (Chambre noire)
- **Serveur FastAPI** (copie du socle) : mot de passe commun obligatoire, cookie `maison_session`, `/health` public (ok, version, nombres de prises en attente et de photos envoyées, sans nom), `exiger_ecriture` sur chaque route qui écrit, mode lecture seule par variable, journal des écritures.
- **Client Svelte 5** : la caméra et la **détection du tirage restent dans l'iPhone** (OpenCV.js, besoin du direct pour cadrer et déclencher). Chaque prise est recadrée dans l'iPhone puis **envoyée aussitôt** au serveur avec ses coins ; l'image source pleine définition part avec, pour pouvoir refaire le recadrage.
- **Zone d'attente** sur le NAS (`/data/attente/<section>/…`) + base SQLite : sections, prises, coins, filtre, rotation, statut, ids Immich.
- **Tâches de fond** (serveur) : orientation par le ML d'Immich (file unique, délai, pause après échec), EXIF/XMP, envoi, album, tag, migration du stockage. *(conseil)* Le rendu (perspective, rotation dans les pixels, filtre à graine fixe, JPEG) reste dans l'iPhone ; une rotation décidée par le NAS après coup déclenche un nouveau rendu dans l'iPhone à la revue.
- *(conseil)* **Connexion** : écran de connexion dans l'app (l'app d'écran d'accueil iOS n'a pas le cookie de l'Anneau) ; une 401 en pleine rafale garde les prises dans la file d'envoi.
- **Immich** : appels côté serveur avec la clé `CHAMBRE_NOIRE_IMMICH_CLE` (permissions : `asset.upload`, `asset.read`, `asset.delete`, `album.*`, `tag.*`, `queue.update` / `job.create`) ; plus de relais nginx exposé.
- Image `ghcr.io/baloodusudouest/chambre-noire`, Watchtower désactivé, port **8100** (à confirmer libre), volume `${DOCKER_ROOT}/chambre-noire`.

### Variables de la stack (aucune valeur par défaut dans le code)
`CHAMBRE_NOIRE_IMMICH_CLE`, `CHAMBRE_NOIRE_ALBUM_SUFFIXE` (« AAAA-MM <suffixe> »), `CHAMBRE_NOIRE_TAG_PARENT` (« <parent>/AAAA-MM »), `CHAMBRE_NOIRE_ALBUM_NON_DATEES`, `CHAMBRE_NOIRE_TAG_NON_DATEE` (doivent rester égales à ce que lit Millésime : `MILLESIME_TAG_PREFIXE`, `MILLESIME_ALBUM_NON_DATEES`), `CHAMBRE_NOIRE_LECTURE_SEULE`, `${CARNET_PASSWORD}` (mot de passe commun).

> État à la 0.7.0 (16/11/2026) : les noms se règlent dans l'appli (Réglages), le mot de passe est `MAISON_PASSWORD` et le jeton `MAISON_JETON` ; la liste à jour des variables est dans `docker-compose.yml`, `.env.example` et `REPRISE.md`.

## 3. Parcours des clics et des écrans

### Tel que construit
Écran des modes → caméra (compteur, définition, Auto/Manuel sauf en Rafale, bouton de mode, déclencheur, Terminer / ⌂ Accueil) → Rafale : accueil de section → Revue (grille, filtres, rotation, coins) → « Dater et envoyer » (mois, année ou « non datées ») → caméra relancée. 1 photo : aperçu → date (toujours vide) → envoi → caméra. Page : tuiles des tirages (↺ ↻ ✕) → date → envoi → caméra.

### Cible
- **Scanner** (écran d'ouverture) : trois cartes Rafale / 1 photo / Page → caméra plein écran, pilule effacée (le pouce va au déclencheur), lien en haut pour revenir. Pendant la prise : compteur « n en sécurité sur le NAS », badge de définition, mode à côté du déclencheur.
  - Rafale : Terminer → **Revue** de la section (photos déjà tournées par le NAS, douteuses marquées) → date → Envoyer → caméra relancée.
  - 1 photo : aperçu → date vide → Envoyer → caméra.
  - Page : tuiles → date → Envoyer → caméra.
- **À traiter** : tuiles avec nombre — *Sections à dater* (prises arrivées mais pas envoyées), *Orientation douteuse*, *Envois incomplets* (album, tag ou migration à relancer, bouton Relancer).
- **Connexion** : tuiles Immich (voyant, ce qui est lu : albums, tags ; ce qui est écrit : photos, albums, tags, migration) et ML d'Immich (voyant, temps de réponse). Gestes Vérifier / Synchroniser.
- **Réglages** : définition minimale, qualité JPEG, taille de sortie, filtre par défaut, délai de stabilité ; journal des envois avec **Annuler** ; version ; déconnexion.

## 4. Design

Socle : toujours sombre, neutres chauds, Inter, rail à gauche sur PC, pilule en bas sur iPhone, un seul bouton plein par bloc, couleur `--app: #4fc1c9`. **Signature** : le cadre de détection dessiné en cyan sur l'image en direct, et la photo qui « apparaît » (fondu du gris à la couleur) quand le NAS l'a reçue. Icône et manifeste propres (installation à l'écran d'accueil).

## 5. Schéma de données

- `section` : id, mode (rafale | photo | page), créée_le, annee, mois, non_datee, statut (en_cours | a_dater | envoi | envoyee | incomplete), album_id, tag_id.
- `prise` : id, section_id, ordre, chemin_source, coins (json), rotation, rotation_source (visage | ciel | suite | manuel | attente), filtre, intensite, statut (attente | rendue | envoyee | erreur), asset_id, empreinte, erreur.
- `journal` : id, quand, action (envoi | album | tag | migration | annulation), section_id, details (json : ids, valeur d'avant), annulable.
- Fichiers : `/data/attente/<section>/<prise>.jpg` (source), supprimés après envoi confirmé + 7 jours.

## 6. Plan (étapes livrables et testées)

*(ordre revu par le conseil : la chaîne de bout en bout le plus tôt possible, l'orientation en dernier)*

1. **Squelette depuis le socle** : nom, couleur, mot de passe, `/health`, Connexion (voyant Immich et ML, **vérification des permissions de la vraie clé au démarrage**), Réglages, lecture seule ; port vérifié dans Portainer ; tests API sans réseau avec un faux Immich écrit d'après le vrai (3.4.x), plus un essai contre le vrai Immich.
2. **Zone d'attente** : file d'envoi de l'iPhone avec accusé de réception, identifiant par prise, base SQLite, reprise après fermeture de l'app ; tests « une prise n'est jamais perdue » (401, coupure réseau, écran verrouillé).
3. **Caméra et détection** : portage de `findPrint` / `findPrintNested` / `quadFromHull` / `findPrintLines` et du rendu (code éprouvé, repris tel quel), trois modes ; banc d'images réelles des fonds difficiles ; tests d'écran PC et iPhone, caméra simulée (.y4m).
4. **Envoi** : EXIF/XMP (tests repris de Scan Immich : +02:00 en mai 1987, +00:00 non datées), album, tag, description (nom d'album), migration ; test qui fige ce qui est écrit chez Immich ; journal + Annuler limité au journal ; Annuler puis renvoyer testé sur 3.4.x.
5. **Orientation sur le NAS** : file ML, points de repère, ciel, continuité ; À traiter « orientation douteuse ». En attendant, rotation manuelle à la revue.
6. **Bascule** : rafales de Scan Immich envoyées ; stack (service ajouté, `immich-scan` retiré), `tailscale serve` `:8443` vers le nouveau port, tuile de l'Anneau, Atlas ; essai réel de bout en bout avec Julien.

## 7. Écarts avec le socle (Scan Immich v3.8) et ce que la réécriture en fait

| Écart | Gravité | Réécriture |
|---|---|---|
| Pas de mot de passe : quiconque atteint le port envoie dans Immich avec la clé | élevée | mot de passe commun + cookie |
| Clé API utilisée par un relais ouvert (lecture et écriture larges) | élevée | appels serveur seulement, routes précises |
| Prises perdues si iOS ferme l'app (1 photo, Page), rafales dans IndexedDB (purge Safari possible) | élevée | zone d'attente sur le NAS |
| Album/tag ratés en rafale : section vidée, pas de relance | moyenne | À traiter « Envois incomplets » |
| Pas de journal des écritures, pas d'Annuler | moyenne | journal + Annuler |
| Pas de `/health`, pas de tuile dans l'Anneau | moyenne | `/health` + tuile |
| Noms d'album et de tag réels en dur dans le code | moyenne (dépôt public) | variables de la stack |
| Pas de mode lecture seule | moyenne | variable + `exiger_ecriture` |
| Pas de dépôt, pas de CHANGELOG/REPRISE/dossier, déploiement par File Station | moyenne | dépôt, image GHCR, stack |
| Caméra figée au retour d'arrière-plan | faible | gestion `visibilitychange` |
| Habillage propre (pas Inter, pas de rail/pilule, pas de `--app`) | faible | socle |

**Ce qui se garde tel quel :** les algorithmes de détection (éprouvés sur fonds blancs, cuir bordeaux, cuir bleu, feuille sur table, pages d'album), la méthode d'orientation par points de repère, l'écriture EXIF/XMP et la règle des non datées (UTC murale), la rotation écrite dans les pixels, le grain à graine fixe.

## 8. Risques à soumettre au conseil

- La leçon du conseil « vérification des dates 2.0 » : ne pas réécrire un outil qui écrit pour la seule cohérence. Ici la réécriture corrige des écarts de sécurité et de perte de données, pas seulement l'habillage.
- Charge du J4125 : rendu final (12 Mpx, filtres) et ML d'Immich côté NAS, en même temps que Plex et la VM HA.
- Trafic Wi-Fi : une source pleine définition par prise (~3-5 Mo) pendant la rafale.
- Remplacement direct : pas d'ancienne app en secours pendant les premiers jours (l'image Scan Immich reste re-déployable).
- Immich 3.4.x : la migration du stockage par `/api/jobs` ou `/api/queues` et ses permissions ont changé au moins une fois (erreur 403 `queue.update` du 31/10).
