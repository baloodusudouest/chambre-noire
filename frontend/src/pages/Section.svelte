<script>
  // Revue d'une section reçue : vignettes (↺ ↻ pour tourner, ✕ pour retirer), date, puis « Dater et envoyer ».
  // Une section incomplète (album, tag, description ou rangement raté) se relance avec sa date.
  import RotateCcw from '@lucide/svelte/icons/rotate-ccw'
  import RotateCw from '@lucide/svelte/icons/rotate-cw'
  import X from '@lucide/svelte/icons/x'
  import { api } from '$lib/api.js'
  import { MOIS, noms } from '$lib/noms.js'
  import { Button } from '$lib/components/ui/button/index.js'

  let { section, session, onchange } = $props()
  let prises = $state([])
  // 0.5.1 : nouvel essai automatique (jusqu'à 3) quand une vignette ne se charge pas, puis bouton pour réessayer
  let essais = $state({})
  function rateE(id) { setTimeout(() => (essais[id] = (essais[id] ?? 0) + 1), 800 * ((essais[id] ?? 0) + 1)) }
  let annee = $state('')
  let mois = $state(0)
  let nonDatee = $state(false)
  let message = $state('')
  let attente = $state(false)

  const nbPrises = $derived(prises.length)
  const anneeOk = $derived(nonDatee || (Number(annee) >= 1850 && Number(annee) <= new Date().getFullYear()))
  const apercu = $derived(anneeOk ? noms(session.libelle, Number(annee), Number(mois), nonDatee, session.album_non_datees) : null)
  const enCours = $derived(section.statut === 'envoi')
  const incomplete = $derived(section.statut === 'incomplete')

  async function lire() {
    prises = (await api.get(`/api/sections/${section.id}/prises`)).prises
  }
  $effect(() => { section.id; section.prises; lire() })

  async function tourner(p, sens) {
    const r = (p.rotation + sens + 4) % 4
    try { await api.patch(`/api/prises/${p.id}`, { rotation: r }); p.rotation = r }
    catch (err) { message = err.message }
  }
  async function retirer(p) {
    try { await api.del(`/api/prises/${p.id}`); prises = prises.filter((x) => x.id !== p.id); onchange?.() }
    catch (err) { message = err.message }
  }
  async function envoyer() {
    message = ''; attente = true
    try {
      await api.post(`/api/sections/${section.id}/envoyer`, incomplete ? {} : { annee: Number(annee) || 0, mois: Number(mois), non_datee: nonDatee })
      onchange?.()
    } catch (err) { message = err.message }
    attente = false
  }
</script>

<section class="mt-4 rounded-2xl border bg-card p-5" aria-label="Revue de la section">
  {#if enCours}
    <h2 class="text-lg font-semibold">Envoi en cours…</h2>
    <p class="mt-1 text-sm" role="status">{section.progression || 'Préparation…'}</p>
  {:else if incomplete}
    <h2 class="text-lg font-semibold">Envoi incomplet — « {section.album} »</h2>
    <ul class="mt-2 list-inside list-disc text-sm">
      {#if section.erreur}<li>{section.erreur}</li>{/if}
      {#each section.etapes as e}<li>{e.etape} : {e.erreur}</li>{/each}
    </ul>
    <p class="mt-2 text-sm text-muted-foreground">Relancer garde la date ; les photos déjà envoyées ne repartent pas.</p>
    <div class="mt-3"><Button onclick={envoyer} disabled={attente || session.lecture_seule}>Relancer</Button></div>
  {:else}
    <h2 class="text-lg font-semibold">{nbPrises} photo{nbPrises > 1 ? 's' : ''} à dater</h2>
    <ul class="mt-3 grid grid-cols-3 gap-2 md:grid-cols-6" aria-label="Photos">
      {#each prises as p (p.id)}
        <li class="relative overflow-hidden rounded-lg bg-black/40">
          {#if (essais[p.id] ?? 0) < 4}
            <img src={`/api/prises/${p.id}/vignette.jpg${essais[p.id] ? `?essai=${essais[p.id]}` : ''}`} alt="Photo à envoyer" loading="lazy" decoding="async"
                 onerror={() => rateE(p.id)}
                 class="aspect-square w-full object-contain transition-transform duration-200" style="transform: rotate({p.rotation * 90}deg)" />
          {:else}
            <button type="button" class="flex aspect-square w-full items-center justify-center p-2 text-center text-xs text-muted-foreground"
                    onclick={() => (essais[p.id] = 0)}>Image non chargée — toucher pour réessayer</button>
          {/if}
          {#if p.erreur}<span class="absolute inset-x-0 top-0 bg-destructive/90 px-1 text-[10px] text-white">{p.erreur}</span>{/if}
          <span class="absolute inset-x-0 bottom-0 flex justify-between bg-black/55 p-0.5">
            <button type="button" class="p-1.5 text-white" onclick={() => tourner(p, -1)} aria-label="Tourner à gauche"><RotateCcw class="size-4" /></button>
            <button type="button" class="p-1.5 text-white" onclick={() => retirer(p)} aria-label="Retirer"><X class="size-4" /></button>
            <button type="button" class="p-1.5 text-white" onclick={() => tourner(p, 1)} aria-label="Tourner à droite"><RotateCw class="size-4" /></button>
          </span>
        </li>
      {/each}
    </ul>

    <fieldset class="mt-5 grid gap-3" disabled={!nbPrises}>
      <legend class="mb-2 font-medium">Date</legend>
      <div class="flex flex-wrap gap-2" class:opacity-40={nonDatee}>
        <select bind:value={mois} disabled={nonDatee} aria-label="Mois" class="h-11 rounded-lg border bg-background px-3">
          <option value={0}>Mois inconnu</option>
          {#each MOIS as m, i}<option value={i + 1}>{m}</option>{/each}
        </select>
        <input bind:value={annee} disabled={nonDatee} inputmode="numeric" maxlength="4" placeholder="Année" aria-label="Année"
               class="h-11 w-28 rounded-lg border bg-background px-3 tabular-nums" />
      </div>
      <label class="flex items-center gap-2 text-sm"><input type="checkbox" bind:checked={nonDatee} class="size-5" /> Photos non datées (ni mois ni année)</label>
      {#if apercu && session.libelle}
        <p class="text-sm text-muted-foreground">Album <b class="text-foreground">{apercu.album}</b> · tag <b class="text-foreground">{apercu.tag}</b>
          {nonDatee ? ' · date fictive : 1er janvier 1900' : ` · date : 1er ${mois ? MOIS[mois - 1] : 'janvier'} ${annee}`}</p>
      {:else if !session.libelle}
        <p class="text-sm text-destructive">Libellé des albums et des tags absent : à régler dans <a href="#/reglages" class="underline">Réglages › Noms dans Immich</a>.</p>
      {/if}
      <div><Button onclick={envoyer} disabled={!anneeOk || attente || !session.libelle || session.lecture_seule}>{attente ? 'Envoi…' : 'Dater et envoyer'}</Button></div>
    </fieldset>
  {/if}
  {#if message}<p class="mt-3 text-sm text-destructive" role="alert">{message}</p>{/if}
</section>
