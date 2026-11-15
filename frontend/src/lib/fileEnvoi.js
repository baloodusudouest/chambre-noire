// File d'envoi de l'iPhone (étape 2). Chaque prise est d'abord écrite dans le stockage de l'iPhone
// (IndexedDB), puis envoyée au NAS. Elle n'est effacée de l'iPhone qu'après la réponse 201 du NAS
// (accusé de réception). Ce qui peut arriver pendant une rafale :
//  - réseau coupé, Tailscale qui décroche, NAS lent : nouvel essai, de plus en plus espacé (2 s → 30 s) ;
//  - session expirée (401) : la file s'arrête et demande la connexion, puis repart toute seule ;
//  - prise refusée (422, image illisible) : gardée sur l'iPhone, montrée dans « À traiter » ;
//  - appli fermée ou écran verrouillé : la file repart à la réouverture (rien n'est perdu).
// L'identifiant de chaque prise est fixé ici : un renvoi ne crée jamais de doublon sur le NAS.

const BASE = 'chambre-noire'
const MAGASIN = 'file'
const PAUSES = [2000, 5000, 15000, 30000]

let base = null
let enCours = false
let minuterie = 0
let echecs = 0
const abonnes = new Set()
export const etat = { surIphone: 0, refusees: 0, envoi: false, connexion: false, horsLigne: false, erreur: '' }

function ouvrir() {
  if (base) return base
  base = new Promise((ok, ko) => {
    const r = indexedDB.open(BASE, 1)
    r.onupgradeneeded = () => r.result.createObjectStore(MAGASIN, { keyPath: 'id' })
    r.onsuccess = () => ok(r.result)
    r.onerror = () => { base = null; ko(r.error) }
  })
  return base
}

async function transaction(mode, faire) {
  const db = await ouvrir()
  return new Promise((ok, ko) => {
    const tx = db.transaction(MAGASIN, mode)
    const resultat = faire(tx.objectStore(MAGASIN))
    tx.oncomplete = () => ok(resultat?.result)
    tx.onerror = () => ko(tx.error)
    tx.onabort = () => ko(tx.error || new Error('Stockage de l’iPhone plein ?'))
  })
}

const tout = () => transaction('readonly', (s) => s.getAll())

function prevenir() { for (const f of abonnes) f({ ...etat }) }

export function abonner(f) {
  abonnes.add(f)
  f({ ...etat })
  return () => abonnes.delete(f)
}

async function recompter() {
  const liste = await tout()
  etat.surIphone = liste.length
  etat.refusees = liste.filter((p) => p.refusee).length
  prevenir()
}

/** Identifiant de prise ou de section : 22 caractères aléatoires, sûrs dans une adresse. */
export function nouvelId() {
  const o = crypto.getRandomValues(new Uint8Array(16))
  return btoa(String.fromCharCode(...o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Garde une prise sur l'iPhone puis lance l'envoi. meta : {section, mode, ordre, coins, rotation, filtre…} */
export async function ajouter(meta, rendu, source = null) {
  const prise = { id: meta.id || nouvelId(), meta: { ...meta, prise_le: meta.prise_le || new Date().toISOString() }, rendu, source, ajoutee: Date.now() }
  prise.meta.id = prise.id
  await transaction('readwrite', (s) => s.put(prise))
  await recompter()
  pousser()
  return prise.id
}

function plusTard(ms) {
  clearTimeout(minuterie)
  minuterie = setTimeout(pousser, ms)
}

/** Envoie ce qui attend sur l'iPhone, une prise à la fois, dans l'ordre d'arrivée. */
export async function pousser() {
  if (enCours) return
  enCours = true
  clearTimeout(minuterie)
  try {
    const liste = (await tout()).filter((p) => !p.refusee).sort((a, b) => a.ajoutee - b.ajoutee)
    for (const prise of liste) {
      etat.envoi = true; prevenir()
      const corps = new FormData()
      corps.append('meta', JSON.stringify(prise.meta))
      corps.append('rendu', prise.rendu, `${prise.id}-rendu.jpg`)
      if (prise.source) corps.append('source', prise.source, `${prise.id}-source.jpg`)
      let r
      try {
        r = await fetch('/api/prises', { method: 'POST', body: corps, credentials: 'same-origin' })
      } catch {
        etat.horsLigne = true; etat.erreur = 'NAS injoignable : nouvel essai bientôt.'
        plusTard(PAUSES[Math.min(echecs++, PAUSES.length - 1)])
        return
      }
      etat.horsLigne = false
      if (r.status === 201) {
        await transaction('readwrite', (s) => s.delete(prise.id))   // accusé de réception : effacé de l'iPhone
        echecs = 0; etat.erreur = ''
        await recompter()
        continue
      }
      if (r.status === 401) {
        etat.connexion = true; etat.erreur = 'Connexion nécessaire : les prises attendent sur l’iPhone.'
        return
      }
      if (r.status === 422) {
        let detail = ''
        try { detail = (await r.json()).detail } catch { /* sans détail */ }
        await transaction('readwrite', (s) => s.put({ ...prise, refusee: detail || 'Prise refusée par le NAS.' }))
        await recompter()
        continue
      }
      etat.erreur = `Le NAS a répondu ${r.status} : nouvel essai bientôt.`
      plusTard(PAUSES[Math.min(echecs++, PAUSES.length - 1)])
      return
    }
  } finally {
    enCours = false
    etat.envoi = false
    prevenir()
  }
}

/** À appeler après une connexion réussie. */
export function reprendre() {
  etat.connexion = false
  echecs = 0
  pousser()
}

export async function refusees() {
  return (await tout()).filter((p) => p.refusee)
}

export async function abandonner(id) {
  await transaction('readwrite', (s) => s.delete(id))
  await recompter()
}

// La file repart d'elle-même : au lancement, au retour du réseau, au retour au premier plan, et toutes les 30 s.
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => { echecs = 0; pousser() })
  document.addEventListener('visibilitychange', () => { if (!document.hidden) pousser() })
  setInterval(() => { if (!enCours && etat.surIphone) pousser() }, 30000)
  recompter().then(pousser).catch(() => { etat.erreur = 'Stockage de l’iPhone indisponible.'; prevenir() })
  if (new URLSearchParams(location.search).has('essai')) window.__fileEnvoi = { ajouter, pousser, reprendre, etat, refusees, nouvelId }
}
