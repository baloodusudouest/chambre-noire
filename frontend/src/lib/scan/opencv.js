// Chargement d'OpenCV.js (4.10, paquet npm @techstark/opencv-js@4.10.0-release.1), servi par l'appli
// elle-même (/opencv.js) : aucun appel extérieur. Chargé à la première ouverture de la caméra.
let promesse = null

function script(src) {
  return new Promise((ok, ko) => {
    const s = document.createElement('script')
    s.src = src; s.async = true; s.onload = ok; s.onerror = () => ko(new Error('Module de détection introuvable.'))
    document.head.appendChild(s)
  })
}

function attendre(delai) {
  return new Promise((ok) => {
    const t0 = Date.now(); let accroche = false
    ;(function voir() {
      const c = window.cv
      if (c && c.Mat) return ok(c)
      if (c && typeof c.then === 'function' && !accroche) {
        accroche = true
        c.then((m) => { if (m && m.Mat) { try { delete m.then } catch { /* rien */ } window.cv = m; ok(m) } })
      } else if (c && !accroche) {
        accroche = true; c.onRuntimeInitialized = () => ok(window.cv)
      }
      if (Date.now() - t0 > delai) return ok(null)
      setTimeout(voir, 150)
    })()
  })
}

export function chargerOpenCV() {
  if (!promesse) {
    promesse = (async () => {
      if (!window.cv) await script('/opencv.js')
      const cv = await attendre(60000)
      if (!cv) { promesse = null; throw new Error('Le module de détection ne répond pas.') }
      return cv
    })()
  }
  return promesse
}
