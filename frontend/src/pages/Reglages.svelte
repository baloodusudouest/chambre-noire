<script>
  // « Réglages » : le journal des envois (avec Annuler), l'écriture dans Immich. Toujours en bas : version, déconnexion.
  import { onMount } from 'svelte'
  import { api } from '$lib/api.js'
  import { Button } from '$lib/components/ui/button/index.js'
  let { session, deconnecter } = $props()
  let journal = $state(null)
  let message = $state('')
  let confirmer = $state(null)

  const date = (iso) => new Date(iso).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })
  async function lire() {
    try { journal = (await api.get('/api/journal')).journal } catch (err) { message = err.message }
  }
  async function annuler(e) {
    message = ''
    try {
      const r = await api.post(`/api/journal/${e.id}/annuler`)
      message = `${r.photos} photo${r.photos > 1 ? 's' : ''} retirée${r.photos > 1 ? 's' : ''} de l’album et du tag, mise${r.photos > 1 ? 's' : ''} à la corbeille d’Immich. Elles sont revenues dans « À traiter ».`
    } catch (err) { message = err.message }
    confirmer = null
    lire()
  }
  onMount(lire)
</script>

<header class="mb-5">
  <p class="etiquette">Chambre noire</p>
  <h1 class="titre">Réglages</h1>
</header>

<section class="rounded-2xl border bg-card p-5" aria-label="Journal des envois">
  <h2 class="text-lg font-semibold">Journal des envois</h2>
  {#if journal && !journal.length}
    <p class="mt-1 text-sm text-muted-foreground">Aucun envoi pour l’instant.</p>
  {:else if journal}
    <ul class="mt-3 grid gap-3">
      {#each journal as e (e.id)}
        <li class="flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-sm first:border-t-0 first:pt-0">
          <span>
            <span class="font-medium">{e.details.album}</span> — {e.details.assets.length} photo{e.details.assets.length > 1 ? 's' : ''}
            <br /><span class="text-muted-foreground">{date(e.quand)}{e.annule_le ? ` · annulé le ${date(e.annule_le)}` : ''}</span>
          </span>
          {#if !e.annule_le}
            {#if confirmer === e.id}
              <span class="flex gap-2">
                <Button variant="destructive" size="sm" onclick={() => annuler(e)}>Confirmer</Button>
                <Button variant="outline" size="sm" onclick={() => (confirmer = null)}>Non</Button>
              </span>
            {:else}
              <Button variant="outline" size="sm" onclick={() => (confirmer = e.id)} disabled={session.lecture_seule}>Annuler l’envoi</Button>
            {/if}
          {/if}
        </li>
      {/each}
    </ul>
    <p class="mt-3 text-xs text-muted-foreground">Annuler ne touche que les photos de cet envoi : retirées de l’album et du tag, puis mises à la corbeille d’Immich (récupérables 30 jours).</p>
  {/if}
  {#if message}<p class="mt-3 text-sm" role="status">{message}</p>{/if}
</section>

<section class="mt-4 rounded-2xl border bg-card p-5">
  <h2 class="text-lg font-semibold">Écriture dans Immich</h2>
  <p class="mt-1 text-sm text-muted-foreground">
    {session.lecture_seule
      ? 'Lecture seule : Chambre noire lit tout mais n\'écrit rien dans Immich. À retirer dans la stack (CHAMBRE_NOIRE_LECTURE_SEULE) quand le premier jour s\'est bien passé.'
      : `Albums « AAAA-MM ${session.libelle || '…'} », tags « ${session.libelle || '…'}/AAAA-MM » (CHAMBRE_NOIRE_LIBELLE). Pour le premier jour d'une nouvelle version : CHAMBRE_NOIRE_LECTURE_SEULE=oui.`}
  </p>
</section>

<p class="mt-6 flex items-center justify-between gap-3 text-sm text-muted-foreground">
  <span>Chambre noire {session.version}</span>
  <Button variant="outline" onclick={deconnecter}>Se déconnecter</Button>
</p>
