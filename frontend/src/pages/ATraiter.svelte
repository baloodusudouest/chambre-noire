<script>
  // « À traiter » : des tuiles avec un nombre — prises encore sur l'iPhone, refusées par le NAS, sections à dater,
  // envois en cours ou incomplets. Une section ouverte montre sa revue (Section.svelte).
  import { onMount, onDestroy } from 'svelte'
  import Smartphone from '@lucide/svelte/icons/smartphone'
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'
  import CalendarClock from '@lucide/svelte/icons/calendar-clock'
  import { api } from '$lib/api.js'
  import { abonner, pousser, refusees, abandonner } from '$lib/fileEnvoi.js'
  import { Button } from '$lib/components/ui/button/index.js'
  import Section from './Section.svelte'

  let { ondeconnecte, session } = $props()
  let file = $state({ surIphone: 0, refusees: 0, envoi: false, erreur: '' })
  let sections = $state(null)
  let choisi = $state(null)
  let rejetees = $state([])
  let minuterie = 0
  let message = $state('')

  const nomMode = { rafale: 'Rafale', photo: '1 photo', page: 'Page d’album' }
  const date = (iso) => new Date(iso).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })

  async function lire() {
    try { sections = (await api.get('/api/sections')).sections }
    catch (err) { if (err.statut === 401) ondeconnecte?.(); else message = err.message }
    // un envoi en cours : on relit chaque seconde pour suivre la progression
    clearTimeout(minuterie)
    if (sections?.some((s) => s.statut === 'envoi')) minuterie = setTimeout(lire, 1000)
  }
  async function ouvrir(nom, section = null) {
    if (choisi === nom + (section?.id ?? '')) { choisi = null; return }
    choisi = nom + (section?.id ?? '')
    if (nom === 'refusees') rejetees = await refusees()
  }
  const sectionChoisie = $derived(sections?.find((s) => choisi === 'section' + s.id))
  async function oublier(id) { await abandonner(id); rejetees = await refusees() }

  let fin
  onMount(() => { lire(); fin = abonner((e) => { const recues = e.surIphone < file.surIphone; file = e; if (recues) lire() }) })
  onDestroy(() => { fin?.(); clearTimeout(minuterie) })
</script>

<header class="mb-5">
  <p class="etiquette">Chambre noire</p>
  <h1 class="titre">À traiter</h1>
</header>

<div class="grid grid-cols-2 gap-3 md:grid-cols-4" role="list" aria-label="À traiter">
  <button type="button" role="listitem" aria-pressed={choisi === 'iphone'} onclick={() => ouvrir('iphone')}
          class="flex min-h-28 flex-col gap-1 rounded-2xl border bg-card p-4 text-left transition-colors hover:border-primary aria-pressed:border-primary">
    <Smartphone class="size-6 text-primary" aria-hidden="true" />
    <span class="text-3xl font-light tabular-nums">{file.surIphone - file.refusees}</span>
    <span class="text-sm text-muted-foreground">sur l’iPhone, pas encore reçue{file.surIphone - file.refusees > 1 ? 's' : ''}</span>
  </button>
  {#if file.refusees}
    <button type="button" role="listitem" aria-pressed={choisi === 'refusees'} onclick={() => ouvrir('refusees')}
            class="flex min-h-28 flex-col gap-1 rounded-2xl border border-destructive/60 bg-card p-4 text-left transition-colors aria-pressed:border-destructive">
      <TriangleAlert class="size-6 text-destructive" aria-hidden="true" />
      <span class="text-3xl font-light tabular-nums">{file.refusees}</span>
      <span class="text-sm text-muted-foreground">refusée{file.refusees > 1 ? 's' : ''} par le NAS</span>
    </button>
  {/if}
  {#each sections ?? [] as s (s.id)}
    <button type="button" role="listitem" aria-pressed={choisi === 'section' + s.id} onclick={() => ouvrir('section', s)}
            class="flex min-h-28 flex-col gap-1 rounded-2xl border bg-card p-4 text-left transition-colors hover:border-primary aria-pressed:border-primary">
      <CalendarClock class="size-6 {s.statut === 'incomplete' ? 'text-destructive' : 'text-primary'}" aria-hidden="true" />
      <span class="text-3xl font-light tabular-nums">{s.statut === 'incomplete' || s.statut === 'envoi' ? s.envoyees + s.prises : s.prises}</span>
      <span class="text-sm text-muted-foreground">{nomMode[s.mode]} du {date(s.creee_le)},
        {s.statut === 'envoi' ? 'envoi en cours' : s.statut === 'incomplete' ? 'envoi incomplet' : 'à dater'}</span>
    </button>
  {/each}
</div>

{#if choisi === 'iphone'}
  <section class="mt-4 rounded-2xl border bg-card p-5" aria-label="Sur l’iPhone">
    <h2 class="text-lg font-semibold">Sur l’iPhone</h2>
    <p class="mt-1 text-sm text-muted-foreground">
      {file.surIphone - file.refusees
        ? 'Ces prises partent toutes seules dès que le NAS répond. Elles ne sont effacées de l’iPhone qu’une fois reçues.'
        : 'Tout est arrivé sur le NAS.'}
    </p>
    {#if file.erreur}<p class="mt-2 text-sm" role="status">{file.erreur}</p>{/if}
    {#if file.surIphone - file.refusees}
      <div class="mt-3"><Button variant="outline" onclick={pousser} disabled={file.envoi}>{file.envoi ? 'Envoi…' : 'Réessayer maintenant'}</Button></div>
    {/if}
  </section>
{:else if choisi === 'refusees'}
  <section class="mt-4 rounded-2xl border bg-card p-5" aria-label="Prises refusées">
    <h2 class="text-lg font-semibold">Refusées par le NAS</h2>
    <ul class="mt-2 grid gap-2">
      {#each rejetees as p (p.id)}
        <li class="flex items-center justify-between gap-3 text-sm">
          <span>{date(p.meta.prise_le)} — {p.refusee}</span>
          <Button variant="outline" size="sm" onclick={() => oublier(p.id)}>Oublier</Button>
        </li>
      {/each}
    </ul>
  </section>
{:else if sectionChoisie}
  <Section section={sectionChoisie} {session} onchange={lire} />
{:else if sections && !sections.length && !file.surIphone}
  <p class="mt-4 text-sm text-muted-foreground">Rien à traiter.</p>
{/if}
{#if message}<p class="mt-3 text-sm text-destructive" role="alert">{message}</p>{/if}
