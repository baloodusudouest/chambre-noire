# Journal des versions

## 0.8.0 — 18 novembre 2026 (santé des tâches de fond)
- **Tâches suivies** (module commun `maison.TACHES`, lues dans `/health` et par la veille de l'Anneau) : `purge` (régulière, toutes les 6 heures : 21 600 s), `envoi-immich` (à la demande : bouton Envoyer d'une section ; « erreur » si l'envoi s'arrête sur une erreur imprévue), `copie-des-bases` (régulière, 86 400 s). Le comportement de l'appli ne change pas (une purge ratée réessaie toujours au tour suivant, un envoi interrompu rend toujours la section relançable).
- **Copie des bases** : chaque nuit à 02:00 (heure de Paris, quel que soit le fuseau du conteneur), copie cohérente de `chambre-noire.db` (API de sauvegarde de SQLite, contrôle d'intégrité) dans `/data/copies/chambre-noire-derniere.db`, écrasée chaque nuit (Hyper Backup tient l'historique) ; résultat dans `/data/copies/copie.json`.
- **`/health`** : ajoute `version_socle`, `taches` et `copie_base` ; rien d'existant ne change. Les messages d'erreur des tâches n'apparaissent qu'avec le jeton commun (`Authorization: Bearer MAISON_JETON`) ou une session valide.
- `maison.py` du socle 0.9.1. Un seul worker uvicorn (le registre des tâches vit en mémoire).

## 0.7.6 — 18 novembre 2026 (constats moyens de l'audit)
- **M33** : les fichiers des photos déjà envoyées dans Immich sont effacés de la zone d'attente après `purge_jours` jours (nouveau réglage d'usage, 30 par défaut, de 1 à 365, dans Réglages › Zone d'attente, sauvegardé par l'Anneau) ; la purge passe au démarrage puis toutes les 6 heures. Le NAS refuse une nouvelle prise s'il resterait moins de 1 Go libre (réponse 507 : la prise attend sur l'iPhone et repart plus tard). Annuler un envoi dont les fichiers sont déjà purgés met toujours les photos à la corbeille d'Immich, mais ne les ramène plus dans « À traiter ».
- **M35** : à la réception, la taille de chaque fichier est contrôlée avant de le lire en entier (taille annoncée, lecture plafonnée à 30 Mo, requête trop lourde refusée d'emblée) et ses pixels sont lus dans l'en-tête du JPEG, sans le décoder : au-delà de 64 millions de pixels, la prise est refusée.
- `maison.py` du socle 0.8.2 (audit M3) : réglages secrets reconnus par mots, adresse avec identifiant écartée, champ `ecartes` dans la sauvegarde (noms seulement).

## 0.7.5 — 18 novembre 2026 (cookies Secure)
- **Cookies `Secure` en https** (audit du 17/11/2026, même correctif dans toutes les applis maison) : ouverte en https (directement, derrière Tailscale Serve qui le dit par `X-Forwarded-Proto`, ou d'après l'origine de la page), l'appli pose ses cookies de session avec l'attribut `Secure` : ils ne partent jamais en clair. En http (adresse locale), rien ne change.
- `entrypoint.sh` refuse de lancer l'appli en root quand `/data` appartient à root (dossier créé par Docker) et dit le remède ; dépannage seulement : `MAISON_ROOT_ACCEPTE=oui`.

## 0.7.4 — 18 novembre 2026 (révocation du cookie commun)
- **« Se déconnecter » dans l'Anneau ferme vraiment la connexion commune** (audit du 17/11/2026, même correctif dans toutes les applis maison) : le cookie commun `maison_session` porte maintenant la génération tenue par l'Anneau (« génération.expiration.signature ») ; « Se déconnecter » l'augmente, et chaque appli la lit dans l'annuaire de l'Anneau (`/externe/services`, au plus une minute de retard) : un cookie commun d'avant la déconnexion ne vaut plus nulle part. Si l'Anneau ne répond pas, le cookie reste accepté comme avant (rien ne se bloque). **Toutes les applis doivent être à jour ensemble** ; une seule reconnexion est demandée après la mise à jour.
- Module commun `maison.py` (socle 0.8.0) : `generation_commune()`, `definir_generation_commune()` ; l'annuaire lit aussi `generation_commune` (une ancienne réponse de l'Anneau, liste seule, reste lue).

## 0.7.3 — 17 novembre 2026 (corrections de l'audit, suite)
- Photo déjà connue d'Immich (renvoyée après Annuler) : sa sortie de la corbeille est maintenant contrôlée. Si Immich la refuse, la prise reste en erreur (à relancer) au lieu d'être notée envoyée alors que la photo restait dans la corbeille, purgée après 30 jours.

## 0.7.2 — 17 novembre 2026 (connexion plus sûre)
- **Connexion plus sûre** (audit du 17/11/2026, même correctif dans toutes les applis maison) :
  - un cookie portant un caractère non ASCII donnait une erreur 500 sur toute l'API ; il est maintenant simplement refusé ;
  - les clés qui signent les cookies (celui de l'appli et le cookie commun `maison_session` posé par l'Anneau) sont tirées du mot de passe par PBKDF2 : un cookie capté sur le réseau local ne permet plus de chercher le mot de passe à grande vitesse. **Toutes les applis doivent être à jour ensemble** ; une seule reconnexion est demandée après la mise à jour ;
  - des essais de mot de passe lancés en parallèle ne contournent plus le délai : au-delà de 30 essais en 5 minutes, tout est refusé sans comparer.
- Module commun `maison.py` (socle 0.7.0) : l'annuaire de l'Anneau est relu 30 s après un échec (avant : 10 min sans adresses après un redémarrage de la stack) ; un réglage `nan` ou infini est refusé ; un `reglages.json` abîmé est mis de côté (`.corrompu`) au lieu d'être écrasé.

## 0.7.1 — 17 novembre 2026 (corrections de l'audit)
- **Bug** : un redémarrage du conteneur pendant un envoi laissait la section figée « envoi en cours », sans bouton pour relancer, et l'API refusait tout nouvel envoi. Au démarrage, une telle section redevient « incomplète » (« Envoi interrompu par un redémarrage : relancer ») ; les photos déjà envoyées ne sont pas renvoyées. Une erreur imprévue pendant l'envoi fait de même au lieu de laisser la section bloquée.
- Un double appui sur « Envoyer » ne lance plus deux envois.
- Intégration continue : l'image n'est plus publiée si les tests échouent (`docker.yml` appelle `tests.yml` avant de construire).

## 0.7.0 — 16 novembre 2026
- **Les réglages vivent dans l'appli.** Le libellé des albums et des tags et l'album des non datées (Réglages › Noms dans Immich, depuis 0.4.1) ne sont plus jamais relus dans la stack : au premier démarrage de la 0.7.0, s'ils ne sont pas déjà dans la base, ils sont repris une fois de `CHAMBRE_NOIRE_LIBELLE` et `CHAMBRE_NOIRE_ALBUM_NON_DATEES` (une ligne au journal par réglage repris), puis seul l'écran Réglages fait foi. `PUT /api/reglages` ne change que les clés envoyées ; une valeur du mauvais type, ou refusée, répond 400 avec un message clair (avant : 422).
- **Sauvegarde par l'Anneau** : nouvelle porte `GET /externe/sauvegarde` (jeton commun `MAISON_JETON` ; vide : fermée). Elle rend seulement la version et les deux réglages, jamais de variable, de clé, de chemin ni de secret (contrat de sauvegarde 1).
- **Restaurer les réglages** (nouvelle tuile dans Réglages) : choisir une date de sauvegarde gardée par l'Anneau, voir ce qui changerait (avant → sauvegardé), confirmer. Ne touche que les réglages de l'appli, donc permis même en lecture seule ; une ligne au journal. Anneau injoignable, `MAISON_JETON` absent ou rien à restaurer : un message clair, pas d'erreur.
- Le journal de Réglages (« Journal ») montre aussi les réglages repris et les restaurations.
- **Anciens noms retirés** : le mot de passe est `MAISON_PASSWORD` seul (`CHAMBRE_NOIRE_PASSWORD` ne suffit plus : l'appli refuse de démarrer) ; `/externe/noms` (Millésime) n'accepte plus que le jeton commun (`MAISON_JETON`, `MAISON_JETON_ANCIEN` pendant un changement) : `CHAMBRE_NOIRE_JETON_MILLESIME` n'ouvre plus la porte. `CHAMBRE_NOIRE_LECTURE_SEULE` reste (forçage pour cette appli seule).
- Tests : mot de passe commun seul, ancien jeton refusé, reprise au premier démarrage puis variable ignorée, réglages par l'écran et mauvais types, sauvegarde (jeton, aucun secret, contrat 1), restauration (dates, différences, application, Anneau injoignable) ; écran Réglages avec la restauration sur PC et iPhone. 55 tests (2 de caméra passés sans fichiers de caméra simulée).

## 0.6.0 — 16 novembre 2026
- **Variables communes de la maison** (module `app/maison.py` du socle 0.5.0, copié tel quel) :
  - mot de passe : `MAISON_PASSWORD`, repli sur `CHAMBRE_NOIRE_PASSWORD` (toujours 12 caractères au moins) ;
  - lecture seule : `MAISON_LECTURE_SEULE` pour toute la maison ; `CHAMBRE_NOIRE_LECTURE_SEULE`, si elle dit oui ou non, l'emporte. Le bandeau et Réglages disent d'où vient la lecture seule (« toute la maison » ou « cette appli ») ;
  - jeton commun `MAISON_JETON` (et `MAISON_JETON_ANCIEN` pendant un changement) accepté sur `/externe/noms`, en plus de l'ancien `CHAMBRE_NOIRE_JETON_MILLESIME` ; aucun des deux : adresse fermée. Comparaison en temps constant ; même en-tête qu'avant (`Authorization: Bearer …`). Connexion › Millésime compte la porte ouverte avec l'un ou l'autre.
- Rien ne change tant que la stack n'a pas les nouvelles variables : chaque ancien nom reste lu. La clé Immich ne change pas. Chambre noire ne donne au navigateur l'adresse d'aucune autre appli : pas d'annuaire.
- Tests : copie du module non retouchée, mot de passe commun puis repli, lecture seule de la maison et forçage par l'appli, porte de Millésime ouverte par `MAISON_JETON`, `MAISON_JETON_ANCIEN` et toujours par l'ancien jeton. 47 tests.

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
