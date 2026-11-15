<script>
  // Navigation commune aux applis : rail à gauche sur PC, pilule d'icônes en bas sur iPhone.
  // Chambre noire : Scanner (écran de travail), À traiter (0.2.0 : prises en attente), Connexion, Réglages.
  import { onMount } from 'svelte'
  import { fly } from 'svelte/transition'
  import Camera from '@lucide/svelte/icons/camera'
  import Network from '@lucide/svelte/icons/network'
  import Inbox from '@lucide/svelte/icons/inbox'
  import { abonner, reprendre } from '$lib/fileEnvoi.js'
  import ATraiter from './pages/ATraiter.svelte'
  import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal'
  import { api } from '$lib/api.js'
  import Connexion from './pages/Connexion.svelte'
  import Scanner from './pages/Scanner.svelte'
  import Services from './pages/Services.svelte'
  import Reglages from './pages/Reglages.svelte'

  const onglets = [
    { page: 'scanner', nom: 'Scanner', icone: Camera },
    { page: 'a-traiter', nom: 'À traiter', icone: Inbox },
    { page: 'connexion', nom: 'Connexion', icone: Network },
    { page: 'reglages', nom: 'Réglages', icone: SlidersHorizontal },
  ]

  let connecte = $state(null) // null : on ne sait pas encore
  let session = $state({ version: '', lecture_seule: false })
  let page = $state(lirePage())
  let file = $state({ surIphone: 0, connexion: false })
  abonner((e) => { file = e; if (e.connexion && connecte) connecte = false })

  function lirePage() {
    const p = location.hash.replace('#/', '')
    return onglets.some((o) => o.page === p) ? p : 'scanner'
  }

  async function verifier() {
    try {
      const s = await api.get('/api/session')
      session = s
      connecte = s.connecte
      if (connecte) reprendre()   // les prises gardées sur l'iPhone repartent
    } catch {
      connecte = false
    }
  }

  async function deconnecter() {
    try { await api.post('/api/deconnexion') } catch { /* déjà déconnecté */ }
    connecte = false
  }

  onMount(verifier)
</script>

<svelte:window onhashchange={() => (page = lirePage())} />

{#if connecte === false}
  <Connexion onconnecte={verifier} />
{:else if connecte}
  <div class="md:pl-52">
    <nav
      aria-label="Sections"
      class="fixed bottom-[calc(0.75rem+env(safe-area-inset-bottom))] left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-full border bg-card/80 p-1.5 shadow-lg backdrop-blur-md
             md:inset-y-0 md:left-0 md:w-52 md:translate-x-0 md:flex-col md:items-stretch md:gap-1 md:rounded-none md:border-0 md:border-r md:bg-transparent md:p-4 md:shadow-none md:backdrop-blur-none"
    >
      <span class="mb-4 hidden px-2 text-xl font-light tracking-tight md:block">Chambre noire</span>
      {#each onglets as o}
        {@const Icone = o.icone}
        <a
          href={'#/' + o.page}
          aria-label={o.nom}
          aria-current={page === o.page ? 'page' : undefined}
          class="flex h-11 items-center gap-2 rounded-full px-4 text-sm font-medium text-muted-foreground transition-colors
                 hover:text-foreground aria-[current=page]:bg-foreground aria-[current=page]:text-background
                 md:h-10 md:rounded-lg md:px-3 md:aria-[current=page]:bg-secondary md:aria-[current=page]:text-foreground"
        >
          <Icone class="size-[1.15rem]" aria-hidden="true" />
          <span class="sr-only md:not-sr-only">{o.nom}</span>
          {#if o.page === 'a-traiter' && file.surIphone}
            <span class="rounded-full bg-primary px-1.5 text-xs text-primary-foreground tabular-nums" aria-label="{file.surIphone} sur l’iPhone">{file.surIphone}</span>
          {/if}
        </a>
      {/each}
    </nav>

    <main
      class="mx-auto max-w-5xl px-[max(1rem,env(safe-area-inset-left))] pt-[calc(1.25rem+env(safe-area-inset-top))] pb-[calc(6rem+env(safe-area-inset-bottom))] md:px-8 md:pt-8 md:pb-10"
    >
      {#if session.lecture_seule}
        <p class="mb-4 rounded-xl border border-primary/50 px-4 py-2 text-sm" role="status">
          Mode lecture seule : Chambre noire lit tout mais n'écrit rien dans Immich (CHAMBRE_NOIRE_LECTURE_SEULE).
        </p>
      {/if}
      {#key page}
        <div in:fly={{ y: 6, duration: 180 }}>
          {#if page === 'a-traiter'}
            <ATraiter ondeconnecte={() => (connecte = false)} />
          {:else if page === 'connexion'}
            <Services ondeconnecte={() => (connecte = false)} />
          {:else if page === 'reglages'}
            <Reglages {session} {deconnecter} />
          {:else}
            <Scanner />
          {/if}
        </div>
      {/key}
    </main>
  </div>
{/if}
