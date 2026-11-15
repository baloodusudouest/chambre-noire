// Noms d'album et de tag, mêmes règles que le serveur (app/envoi.py) : affichés avant l'envoi.
export const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']
const feuille = (a, m) => (m ? `${a}-${String(m).padStart(2, '0')}` : String(a))
export function noms(libelle, annee, mois, nonDatee, albumNonDatees = '') {
  const l = (libelle || '').trim().replace(/[\/\\]/g, '-')
  return nonDatee
    ? { album: albumNonDatees || `Non datées ${l}`, tag: `${l}/Non datée` }
    : { album: `${feuille(annee, mois)} ${l}`, tag: `${l}/${feuille(annee, mois)}` }
}
