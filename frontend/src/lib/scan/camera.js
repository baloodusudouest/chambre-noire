// Prise de vue en direct : caméra arrière, détection à ~6 images/s, prise automatique quand le tirage est
// stable et assez défini. Logique reprise de Scan Immich v3.9 (camLoop, pageCamStep, captureLive, capturePage).
// Chaque prise est rendue dans l'iPhone (redressement + filtre), puis confiée à la file d'envoi :
// elle n'est effacée de l'iPhone qu'une fois reçue par le NAS.
import { findPrint, findPrintNested } from './detection.js'
import { newCanvas, release, toBlob, warp, applyFilter } from './rendu.js'
import { chargerOpenCV } from './opencv.js'
import { ajouter, nouvelId } from '../fileEnvoi.js'

export const REGLAGES = {
  minPx: 1800,        // grand côté minimal d'un tirage seul dans l'image (pixels de la caméra) : prise bloquée en dessous
  minPxPage: 1200,    // idem, par tirage, en mode Page
  stableMs: 900,      // immobilité demandée avant la prise automatique
  tailleMax: 4000,    // grand côté de l'image rendue
  qualite: 0.92,      // JPEG
  filtre: 'restore',  // restauration douce des couleurs passées
  intensite: 70,
  delaiAutorisation: 20000,   // ms : réponse de la caméra (iOS peut d'abord demander l'autorisation)
  delaiReglage: 3000,         // ms : chaque ajustement de définition (abandonné au-delà, on garde la définition reçue)
  delaiImage: 8000,           // ms : première image visible
}

/** Ouverture dépassée par une autre, ou caméra fermée pendant l'ouverture : rien à signaler. */
export class Depasse extends Error { constructor() { super('Ouverture remplacée.'); this.name = 'Depasse' } }

const attendreMs = (ms) => new Promise((ok) => setTimeout(ok, ms))
/** promesse, ou erreur(message) si elle n'a pas abouti en ms. */
function delai(promesse, ms, message) {
  let t
  return Promise.race([promesse, new Promise((_, ko) => { t = setTimeout(() => ko(new Error(message)), ms) })]).finally(() => clearTimeout(t))
}
/** Attend une promesse au plus ms ; refus ou dépassement ignorés. */
const essayer = (promesse, ms) => delai(promesse, ms, '').catch(() => {})
/** Résolue quand la vidéo a une vraie image (dimensions connues et une image décodée). */
function imagePrete(v) {
  return new Promise((ok) => {
    const debut = Date.now()
    const t = setInterval(voir, 200)
    function voir() {
      const prete = v.videoWidth > 0 && v.readyState >= 2
      if (prete || Date.now() - debut > 30000) {
        clearInterval(t); v.removeEventListener('loadeddata', voir); v.removeEventListener('resize', voir)
        if (prete) ok()
      }
    }
    v.addEventListener('loadeddata', voir); v.addEventListener('resize', voir)
    voir()
  })
}

// banc d'essai (?essai) : les tests baissent les seuils pour leurs caméras simulées de faible définition
if (typeof window !== 'undefined' && new URLSearchParams(location.search).has('essai')) window.__reglagesCamera = REGLAGES

const diag = (q) => Math.hypot(q[2].x - q[0].x, q[2].y - q[0].y)
const ecart = (a, b) => { let m = 0; for (let i = 0; i < 4; i++) m = Math.max(m, Math.hypot(a[i].x - b[i].x, a[i].y - b[i].y)); return m }
const grandCote = (q) => Math.round(Math.max(
  Math.hypot(q[1].x - q[0].x, q[1].y - q[0].y), Math.hypot(q[2].x - q[3].x, q[2].y - q[3].y),
  Math.hypot(q[3].x - q[0].x, q[3].y - q[0].y), Math.hypot(q[2].x - q[1].x, q[2].y - q[1].y)))

export class Camera {
  /** video : <video>, signaler(etat) : appelé à chaque image avec {quads, bon, petits, statut, px, prises} */
  constructor(video, signaler) {
    this.video = video
    this.signaler = signaler
    this.mode = 'rafale'
    this.cv = null
    this.flux = null
    this.marche = false
    this.gen = 0           // numéro de l'ouverture en cours (0.9.4)
    this.etape = null      // etape(texte) : étape de l'ouverture, affichée à l'écran
    this.surInterruption = null   // appelé quand iOS coupe la caméra pendant la prise de vue
    this.petite = null
    this.reinit()
    this.section = null
    this.prises = 0
    this.surPrise = null   // appelé au moment exact de la prise (flash à l'écran), automatique ou déclencheur
  }

  reinit() {
    Object.assign(this, { dernierT: 0, arme: true, manque: 0, occupe: false, quads: [], stableDepuis: 0, derniere: null })
  }

  /**
   * Ouverture de la caméra, étape par étape, chacune avec un délai maximal (0.9.4) : sur l'iPhone, surtout depuis
   * l'icône d'accueil, iOS peut couper la caméra pendant qu'elle s'ouvre (demande d'autorisation, passage en
   * arrière-plan) ; une promesse restait alors en attente pour toujours (« Préparation de la caméra… » sans fin).
   * Une seule ouverture à la fois : chaque appel porte un numéro (`gen`) ; une ouverture dépassée par une autre
   * (ou par fermer()) rend sa caméra et s'arrête sans rien toucher. En cas d'image noire, un second essai part
   * sans ajustement de définition. `etape(texte)` : appelé à chaque étape (affichée à l'écran).
   */
  async ouvrir() {
    const gen = ++this.gen
    this.marche = false
    this.arreterFlux()
    try {
      await this.ouvrirUneFois(gen, true)
    } catch (e) {
      if (e instanceof Depasse || e.name === 'NotAllowedError' || e.name === 'NotFoundError' || e.name === 'NotReadableError') throw e
      if (gen !== this.gen) throw new Depasse()
      // second essai, plus simple : caméra rendue, pas d'ajustement de définition
      this.arreterFlux()
      this.etape?.('Nouvel essai…')
      await attendreMs(400)
      if (gen !== this.gen) throw new Depasse()
      await this.ouvrirUneFois(gen, false)
    }
  }

  async ouvrirUneFois(gen, ajuster) {
    const verifier = (flux) => { if (gen !== this.gen) { if (flux) flux.getTracks().forEach((t) => t.stop()); throw new Depasse() } }
    this.etape?.('Ouverture de la caméra…')
    const demande = navigator.mediaDevices.getUserMedia({
      audio: false,
      video: ajuster
        ? { facingMode: { ideal: 'environment' }, width: { ideal: 4032 }, height: { ideal: 3024 } }
        : { facingMode: { ideal: 'environment' }, width: { ideal: 3840 }, height: { ideal: 2160 } },
    })
    // caméra accordée trop tard (délai dépassé, ou ouverture remplacée) : rendue aussitôt, jamais laissée allumée
    let abandon = false
    demande.then((f) => { if (abandon || gen !== this.gen) f.getTracks().forEach((t) => t.stop()) }, () => {})
    let flux
    try { flux = await delai(demande, REGLAGES.delaiAutorisation, 'La caméra ne répond pas (autorisation ?).') }
    catch (e) { abandon = true; throw e }
    verifier(flux)
    this.flux = flux
    const piste = flux.getVideoTracks()[0]
    if (ajuster) {
      // garde la plus grande définition entre 4:3 (4032×3024) et 4K 16:9 (3840×2160)
      this.etape?.('Réglage de la définition…')
      const px = () => { const s = piste.getSettings(); return (s.width || 0) * (s.height || 0) }
      if (px() < 3840 * 2160) {
        const avant = px()
        await essayer(piste.applyConstraints({ width: { ideal: 3840 }, height: { ideal: 2160 } }), REGLAGES.delaiReglage)
        verifier()
        if (px() < avant) { await essayer(piste.applyConstraints({ width: { ideal: 4032 }, height: { ideal: 3024 } }), REGLAGES.delaiReglage); verifier() }
      }
    }
    // iOS coupe la piste (appel, autre appli, contrôle) : relance automatique
    piste.onended = () => this.interrompue(gen)
    piste.onmute = () => this.interrompue(gen)

    this.etape?.('Démarrage de l’image…')
    const v = this.video
    v.muted = true; v.setAttribute('muted', ''); v.setAttribute('playsinline', ''); v.setAttribute('autoplay', '')
    v.srcObject = flux
    await delai(Promise.all([v.play(), imagePrete(v)]), REGLAGES.delaiImage, 'L’image de la caméra reste noire.')
    verifier()

    if (!this.cv) {
      this.etape?.('Chargement de la détection…')
      this.cv = await chargerOpenCV()
      verifier()
    }
    this.reinit()
    this.marche = true
    requestAnimationFrame((t) => this.boucle(t))
  }

  /** Piste coupée par iOS pendant la prise de vue : on rouvre (une fois par seconde au plus). */
  interrompue(gen) {
    if (gen !== this.gen || !this.marche || !this.surInterruption) return
    const t = Date.now()
    if (t - (this.derniereInterruption || 0) < 1000) return
    this.derniereInterruption = t
    this.surInterruption()
  }

  arreterFlux() {
    if (this.flux) this.flux.getTracks().forEach((t) => { t.onended = null; t.onmute = null; t.stop() })
    this.flux = null
    if (this.video) this.video.srcObject = null
  }

  fermer() {
    this.gen++            // toute ouverture en cours s'arrête d'elle-même
    this.marche = false
    this.arreterFlux()
    release(this.petite); this.petite = null
  }

  changerMode(mode) {
    this.mode = mode
    this.section = null      // une nouvelle section commence
    this.reinit()
  }

  /** Rafale : « Terminer » ferme la section en cours (la suivante en ouvrira une autre). */
  terminerSection() { this.section = null }

  detecter(f) {
    let r = null, mat = null
    try {
      mat = this.cv.imread(this.petite)
      if (this.mode === 'page') {
        r = findPrint(this.cv, mat, true)
        return (r ? r.prints : []).filter((p) => p.fill > 0.88).map((p) => p.pts.map((q) => ({ x: q.x / f, y: q.y / f })))
      }
      r = findPrintNested(this.cv, mat)
      return r && r.fill > 0.88 ? [r.pts.map((p) => ({ x: p.x / f, y: p.y / f }))] : []
    } catch { return [] } finally { if (mat) mat.delete() }
  }

  boucle(t) {
    if (!this.marche) return
    requestAnimationFrame((u) => this.boucle(u))
    const v = this.video
    if (this.occupe || !this.cv || v.readyState < 2 || t - this.dernierT < 160) return
    this.dernierT = t
    const vw = v.videoWidth, vh = v.videoHeight
    if (!vw || !vh) return
    const f = 420 / Math.max(vw, vh), sw = Math.round(vw * f), sh = Math.round(vh * f)
    if (!this.petite) this.petite = document.createElement('canvas')
    if (this.petite.width !== sw || this.petite.height !== sh) { this.petite.width = sw; this.petite.height = sh }
    this.petite.getContext('2d', { willReadFrequently: true }).drawImage(v, 0, 0, sw, sh)

    const quads = this.detecter(f)
    const maintenant = performance.now()
    if (!quads.length) {
      this.manque++; this.stableDepuis = 0
      if (!this.arme && this.manque >= 3) this.arme = true
    } else {
      this.manque = 0
      const meme = this.quads.length === quads.length && quads.every((q, i) => ecart(this.quads[i], q) < diag(q) * 0.018)
      if (meme) { if (!this.stableDepuis) this.stableDepuis = maintenant } else this.stableDepuis = 0
      // tirage changé (ou page tournée) : la prise suivante est permise
      if (!this.arme && this.derniere && (this.derniere.length !== quads.length ||
          quads.some((q, i) => ecart(this.derniere[i], q) > diag(q) * 0.15))) this.arme = true
    }
    this.quads = quads
    const seuil = this.mode === 'page' ? REGLAGES.minPxPage : REGLAGES.minPx
    const pxs = quads.map(grandCote)
    const petits = pxs.map((p) => p < seuil)
    const tropPetit = petits.some(Boolean)
    const stable = quads.length && this.stableDepuis && maintenant - this.stableDepuis >= REGLAGES.stableMs
    const n = quads.length
    let statut
    if (!n) statut = this.arme ? (this.mode === 'page' ? 'Cherche les tirages de la page…' : 'Cherche un tirage…') : (this.mode === 'page' ? 'Tourne la page' : 'Pose le tirage suivant')
    else if (!this.arme) statut = this.mode === 'page' ? 'Page prise ✓ — tourne la page' : 'Photo prise ✓ — change de tirage'
    else if (tropPetit) statut = 'Trop loin — rapproche le téléphone'
    else if (!stable) statut = (this.mode === 'page' ? `${n} tirage${n > 1 ? 's' : ''} — ` : 'Tirage détecté — ') + 'ne bouge plus…'
    else statut = 'Prise…'
    this.signaler({ quads, bon: !!stable && this.arme && !tropPetit, petits, statut, px: pxs.length ? Math.min(...pxs) : 0, tropPetit })
    if (stable && this.arme && !tropPetit) this.prendre(quads)
  }

  /** Prise (automatique, ou déclencheur). Renvoie le nombre de tirages pris. */
  async prendre(quads = this.quads) {
    if (this.occupe || !quads.length) return 0
    this.occupe = true
    const v = this.video
    const image = newCanvas(v.videoWidth, v.videoHeight)
    image.getContext('2d').drawImage(v, 0, 0, image.width, image.height)
    try { this.surPrise?.(quads.length) } catch { /* l'affichage ne doit jamais bloquer la prise */ }
    this.arme = false; this.derniere = quads; this.stableDepuis = 0; this.manque = 0
    try {
      if (this.mode !== 'rafale' || !this.section) this.section = nouvelId()   // 1 photo et Page : une section par prise
      const source = await toBlob(image, 'image/jpeg', REGLAGES.qualite)
      for (const q of quads) {
        const redresse = warp(this.cv, image, q, REGLAGES.tailleMax)
        const filtre = applyFilter(redresse, REGLAGES.filtre, REGLAGES.intensite)
        const rendu = await toBlob(filtre, 'image/jpeg', REGLAGES.qualite)
        if (filtre !== redresse) release(filtre)
        release(redresse)
        this.prises++
        await ajouter({ section: this.section, mode: this.mode, ordre: this.prises,
                        coins: q.map((p) => [Math.round(p.x), Math.round(p.y)]), rotation: 0,
                        filtre: REGLAGES.filtre, intensite: REGLAGES.intensite }, rendu, source)
      }
      return quads.length
    } finally {
      release(image)
      this.occupe = false
    }
  }
}
