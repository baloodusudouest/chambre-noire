<script>
  // « Scanner » : l'écran de travail. Trois modes, puis la caméra plein écran. Chaque prise part aussitôt vers
  // le NAS (file d'envoi) ; la date et l'envoi dans Immich se font ensuite dans « À traiter » (étape 4).
  import { onDestroy, tick } from 'svelte'
  import Images from '@lucide/svelte/icons/images'
  import FileImage from '@lucide/svelte/icons/file-image'
  import BookOpen from '@lucide/svelte/icons/book-open'
  import X from '@lucide/svelte/icons/x'
  import { Camera, Depasse, REGLAGES } from '$lib/scan/camera.js'
  import { abonner } from '$lib/fileEnvoi.js'

  const MODES = [
    { id: 'rafale', nom: 'Rafale', icone: Images, texte: 'Plusieurs tirages d’affilée, une section à dater.' },
    { id: 'photo', nom: '1 photo', icone: FileImage, texte: 'Un tirage, une section : pour les photos isolées.' },
    { id: 'page', nom: 'Page d’album', icone: BookOpen, texte: '1 à 4 tirages découpés par prise, une section par page.' },
  ]

  let video = $state()
  let calque = $state()
  let camera = null
  let ouverte = $state(false)
  let mode = $state('rafale')
  let vue = $state({ quads: [], bon: false, petits: [], statut: 'Préparation de la caméra…', px: 0, tropPetit: false })
  let erreur = $state('')
  let flash = $state(false)
  let prisesSession = $state(0)
  let file = $state({ surIphone: 0 })
  const fin = abonner((e) => (file = e))
  const caméraPossible = typeof window !== 'undefined' && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia

  function dessiner(e) {
    vue = e
    const c = calque, v = video
    if (!c || !v?.videoWidth) return
    const dpr = window.devicePixelRatio || 1, cw = c.clientWidth, ch = c.clientHeight
    if (c.width !== Math.round(cw * dpr) || c.height !== Math.round(ch * dpr)) { c.width = Math.round(cw * dpr); c.height = Math.round(ch * dpr) }
    const x = c.getContext('2d'); x.clearRect(0, 0, c.width, c.height)
    const s = Math.max(cw / v.videoWidth, ch / v.videoHeight), ox = (cw - v.videoWidth * s) / 2, oy = (ch - v.videoHeight * s) / 2
    e.quads.forEach((q, i) => {
      const P = q.map((p) => ({ x: (p.x * s + ox) * dpr, y: (p.y * s + oy) * dpr }))
      const mauvais = e.petits[i]
      x.fillStyle = mauvais ? 'rgba(239,91,91,.18)' : e.bon ? 'rgba(79,193,201,.25)' : 'rgba(232,163,61,.16)'
      x.strokeStyle = mauvais ? '#ef5b5b' : e.bon ? '#4fc1c9' : '#e8a33d'
      x.lineWidth = 4 * dpr; x.lineJoin = 'round'
      x.beginPath(); x.moveTo(P[0].x, P[0].y); for (let k = 1; k < 4; k++) x.lineTo(P[k].x, P[k].y); x.closePath()
      x.fill(); x.stroke()
      if (mode === 'page') {
        const cx = P.reduce((a, p) => a + p.x, 0) / 4, cy = P.reduce((a, p) => a + p.y, 0) / 4
        x.beginPath(); x.arc(cx, cy, 18 * dpr, 0, Math.PI * 2); x.fillStyle = 'rgba(0,0,0,.6)'; x.fill()
        x.fillStyle = '#fff'; x.font = `700 ${18 * dpr}px Inter, system-ui, sans-serif`; x.textAlign = 'center'; x.textBaseline = 'middle'
        x.fillText(String(i + 1), cx, cy)
      }
    })
  }

  async function ouvrir(m) {
    mode = m; erreur = ''; prisesSession = 0; ouverte = true
    vue = { quads: [], bon: false, petits: [], statut: 'Préparation de la caméra…', px: 0, tropPetit: false }
    await tick()                       // 0.9.4 : la balise <video> existe avant de créer la caméra
    if (!ouverte || !video) return
    camera = new Camera(video, dessiner)
    camera.mode = m
    camera.surPrise = declencherFlash
    camera.etape = (texte) => { if (!vue.quads.length) vue = { ...vue, statut: texte } }
    camera.surInterruption = () => relancer('Caméra coupée par l’iPhone : reprise…')
    const avant = camera.prises
    const compter = setInterval(() => { if (camera) prisesSession = camera.prises - avant }, 250)
    camera._compter = compter
    await demarrer()
  }

  /** Ouvre (ou rouvre) la caméra ; une ouverture remplacée par une autre ne signale rien. */
  async function demarrer() {
    const c = camera
    if (!c) return
    try { await c.ouvrir() }
    catch (e) {
      if (e instanceof Depasse || c !== camera) return
      erreur = 'Caméra inaccessible : ' + (e.message || e.name) + ' Ferme et rouvre « Scanner » ; si ça recommence, ouvre Chambre noire dans Safari.'
      fermer()
    }
  }

  function relancer(texte) {
    if (!camera || !ouverte) return
    vue = { quads: [], bon: false, petits: [], statut: texte, px: 0, tropPetit: false }
    demarrer()
  }

  // Flash blanc au moment de la prise (automatique ou déclencheur) : apparition immédiate, fondu en 0,35 s
  let flashMinuterie = 0
  function declencherFlash() {
    clearTimeout(flashMinuterie)
    flash = true
    flashMinuterie = setTimeout(() => (flash = false), 90)
  }

  function fermer() {
    if (camera) { clearInterval(camera._compter); camera.fermer() }
    camera = null; ouverte = false
  }

  function changerMode() {
    const i = MODES.findIndex((m) => m.id === mode)
    mode = MODES[(i + 1) % MODES.length].id
    camera?.changerMode(mode)
  }

  async function declencher() {
    if (!camera) return
    if (vue.tropPetit) { erreur = `Tirage trop petit dans l’image (${vue.px.toLocaleString('fr-FR')} px) : rapproche le téléphone.`; return }
    const n = await camera.prendre()
    if (!n) erreur = 'Aucun tirage détecté.'
  }

  function terminer() {
    camera?.terminerSection()
    fermer()
    location.hash = '#/a-traiter'
  }

  // iOS coupe la caméra en arrière-plan : on la rend en partant, on la relance au retour (une seule ouverture à la fois)
  function visibilite() {
    if (!ouverte || !camera) return
    if (document.hidden) { camera.marche = false; camera.gen++; camera.arreterFlux() }
    else relancer('Reprise de la caméra…')
  }
  onDestroy(() => { fin(); fermer() })
  const enSecurite = $derived(Math.max(0, prisesSession - file.surIphone))
</script>

<svelte:document onvisibilitychange={visibilite} />

<header class="mb-5">
  <p class="etiquette">Chambre noire</p>
  <h1 class="titre">Scanner</h1>
</header>

{#if !caméraPossible}
  <p class="mb-4 rounded-xl border border-destructive/60 px-4 py-3 text-sm" role="alert">
    La caméra n’est permise qu’en HTTPS : ouvre Chambre noire par son adresse Tailscale (https://…).
  </p>
{/if}
{#if erreur && !ouverte}<p class="mb-4 text-sm text-destructive" role="alert">{erreur}</p>{/if}

<ul class="grid gap-3 md:grid-cols-3" aria-label="Modes">
  {#each MODES as m}
    {@const Icone = m.icone}
    <li>
      <button type="button" onclick={() => ouvrir(m.id)} disabled={!caméraPossible}
              class="flex w-full gap-3 rounded-2xl border bg-card p-4 text-left transition-colors hover:border-primary disabled:opacity-50">
        <Icone class="mt-0.5 size-6 shrink-0 text-primary" aria-hidden="true" />
        <span><span class="font-medium">{m.nom}</span><br /><span class="text-sm text-muted-foreground">{m.texte}</span></span>
      </button>
    </li>
  {/each}
</ul>
<p class="mt-4 text-sm text-muted-foreground">
  Prise automatique dès que le tirage est immobile et assez net ({REGLAGES.minPx.toLocaleString('fr-FR')} px au moins).
  Chaque prise part aussitôt vers le NAS ; la date et l’envoi dans Immich se font dans « À traiter ».
</p>

{#if ouverte}
  <div class="fixed inset-0 z-50 bg-black" role="dialog" aria-label="Caméra">
    <!-- svelte-ignore a11y_media_has_caption -->
    <video bind:this={video} playsinline muted class="absolute inset-0 size-full object-cover"></video>
    <canvas bind:this={calque} class="pointer-events-none absolute inset-0 size-full"></canvas>
    <div class="pointer-events-none absolute inset-0 bg-white {flash ? 'opacity-85' : 'opacity-0 transition-opacity duration-350 ease-out'}"
         data-flash={flash ? 'oui' : 'non'}></div>

    <div class="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-gradient-to-b from-black/70 to-transparent px-4 pt-[calc(0.75rem+env(safe-area-inset-top))] pb-6 text-white">
      <button type="button" onclick={fermer} class="rounded-full bg-black/50 p-2" aria-label="Fermer la caméra"><X class="size-5" /></button>
      <span class="rounded-full bg-black/50 px-3 py-1.5 text-sm tabular-nums" aria-live="polite">
        {prisesSession} prise{prisesSession > 1 ? 's' : ''} · {enSecurite} sur le NAS
      </span>
      {#if vue.quads.length}
        <span class="rounded-full px-3 py-1.5 text-sm tabular-nums {vue.tropPetit ? 'bg-destructive text-white' : 'bg-primary text-primary-foreground'}">
          {vue.tropPetit ? '⚠' : '✓'} {vue.px.toLocaleString('fr-FR')} px
        </span>
      {:else}<span class="w-16"></span>{/if}
    </div>

    <div class="absolute inset-x-0 bottom-0 flex flex-col items-center gap-4 bg-gradient-to-t from-black/80 to-transparent px-4 pt-10 pb-[calc(1.25rem+env(safe-area-inset-bottom))] text-white">
      <p class="rounded-full bg-black/60 px-4 py-2 text-sm" role="status">{erreur || vue.statut}</p>
      <div class="grid w-full max-w-sm grid-cols-3 items-center">
        <button type="button" onclick={changerMode} class="justify-self-start rounded-full bg-black/50 px-3 py-2 text-sm">
          {MODES.find((m) => m.id === mode).nom}
        </button>
        <button type="button" onclick={declencher} aria-label="Prendre la photo"
                class="size-18 justify-self-center rounded-full border-4 border-white bg-white/20 active:bg-white/60"></button>
        <button type="button" onclick={terminer} class="justify-self-end rounded-full bg-black/50 px-3 py-2 text-sm">Terminer</button>
      </div>
    </div>
  </div>
{/if}
