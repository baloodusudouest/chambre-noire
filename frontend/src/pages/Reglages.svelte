<script>
  // « Réglages » : le journal (envois avec Annuler, réglages repris ou restaurés), les noms dans Immich,
  // la restauration depuis une sauvegarde de l'Anneau (0.7.0), l'écriture dans Immich. Toujours en bas : version, déconnexion.
  import { onMount } from 'svelte'
  import { api } from '$lib/api.js'
  import { Button } from '$lib/components/ui/button/index.js'
  import { noms } from '$lib/noms.js'
  let { session, deconnecter, relire } = $props()
  let libelle = $state(session.libelle || '')
  let albumNd = $state(session.album_non_datees || '')
  let messageNoms = $state('')
  const exemple = $derived(libelle.trim() ? noms(libelle, 1987, 5, false) : null)
  const exempleNd = $derived(libelle.trim() ? noms(libelle, 0, 0, true, albumNd.trim()) : null)
  const change = $derived(libelle.trim() !== (session.libelle || '') || albumNd.trim() !== (session.album_non_datees || ''))
  async function enregistrerNoms() {
    messageNoms = ''
    try {
      await api.put('/api/reglages', { libelle: libelle.trim(), album_non_datees: albumNd.trim() })
      messageNoms = 'Enregistré : utilisé dès le prochain envoi. Les albums et tags déjà dans Immich ne sont pas renommés.'
      await relire?.()
    } catch (err) { messageNoms = err.message }
  }
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
  // ---- 0.7.0 : restaurer les réglages depuis une sauvegarde de l'Anneau (réglages seulement, permis en lecture seule)
  const NOMS_REGLAGES = { libelle: 'Libellé des albums et des tags', album_non_datees: 'Album des photos non datées' }
  const valeur = (v) => (v === '' || v === null || v === undefined ? '(vide)' : String(v))
  let dates = $state(null)
  let choix = $state('')
  let apercu = $state(null)
  let confirmerRestaurer = $state(false)
  let messageRestaurer = $state('')
  async function lireDates() {
    messageRestaurer = ''
    try { dates = (await api.get('/api/restaurer')).dates } catch (err) { dates = []; messageRestaurer = err.message }
  }
  async function voir() {
    apercu = null
    confirmerRestaurer = false
    messageRestaurer = ''
    if (!choix) return
    try { apercu = await api.get(`/api/restaurer?le=${encodeURIComponent(choix)}`) } catch (err) { messageRestaurer = err.message }
  }
  async function restaurer() {
    messageRestaurer = ''
    try {
      const r = await api.post('/api/restaurer', { le: choix })
      libelle = r.reglages.libelle
      albumNd = r.reglages.album_non_datees
      messageRestaurer = r.appliques.length
        ? `Réglages restaurés depuis la sauvegarde du ${jour(choix)} (${r.appliques.length}).`
        : 'Rien à restaurer : les réglages sont déjà ceux de cette sauvegarde.'
      apercu = null
      await relire?.()
      lire()
    } catch (err) { messageRestaurer = err.message }
    confirmerRestaurer = false
  }
  const jour = (d) => new Date(`${d}T12:00:00`).toLocaleDateString('fr-FR', { dateStyle: 'long' })
  const ligneJournal = (e) => e.action === 'restauration'
    ? `Réglages restaurés (sauvegarde du ${jour(e.details.le)})`
    : `Réglage repris de la stack : ${NOMS_REGLAGES[e.details.cle] || e.details.cle}`
  onMount(() => { lire(); lireDates() })
</script>

<header class="mb-5">
  <p class="etiquette">Chambre noire</p>
  <h1 class="titre">Réglages</h1>
</header>

<section class="rounded-2xl border bg-card p-5" aria-label="Journal">
  <h2 class="text-lg font-semibold">Journal</h2>
  {#if journal && !journal.length}
    <p class="mt-1 text-sm text-muted-foreground">Aucun envoi pour l’instant.</p>
  {:else if journal}
    <ul class="mt-3 grid gap-3">
      {#each journal as e (e.id)}
        {#if e.action !== 'envoi'}
          <li class="border-t pt-3 text-sm first:border-t-0 first:pt-0">
            <span class="min-w-0 break-words">{ligneJournal(e)}</span>
            <br /><span class="text-muted-foreground">{date(e.quand)}</span>
          </li>
        {:else}
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
        {/if}
      {/each}
    </ul>
    <p class="mt-3 text-xs text-muted-foreground">Annuler ne touche que les photos de cet envoi : retirées de l’album et du tag, puis mises à la corbeille d’Immich (récupérables 30 jours).</p>
  {/if}
  {#if message}<p class="mt-3 text-sm" role="status">{message}</p>{/if}
</section>

<section class="mt-4 rounded-2xl border bg-card p-5" aria-label="Noms dans Immich">
  <h2 class="text-lg font-semibold">Noms dans Immich</h2>
  <div class="mt-3 grid gap-3">
    <label class="grid gap-1 text-sm">Libellé des albums et des tags
      <input bind:value={libelle} maxlength="80" class="h-11 rounded-lg border bg-background px-3" placeholder="Numérisation …" />
    </label>
    <label class="grid gap-1 text-sm">Album des photos non datées <span class="text-muted-foreground">(vide : « Non datées » + libellé)</span>
      <input bind:value={albumNd} maxlength="120" class="h-11 rounded-lg border bg-background px-3" placeholder={libelle.trim() ? `Non datées ${libelle.trim()}` : ''} />
    </label>
    {#if exemple}
      <p class="text-sm text-muted-foreground">Exemple : album <b class="text-foreground">{exemple.album}</b>, tag <b class="text-foreground">{exemple.tag}</b> ;
        non datées : album <b class="text-foreground">{exempleNd.album}</b>, tag <b class="text-foreground">{exempleNd.tag}</b>.</p>
    {/if}
    <p class="text-xs text-muted-foreground">Millésime suit ces noms s’il est relié (Connexion › Millésime) ; sinon, garder le même libellé que dans sa stack. Changer le libellé démarre de nouveaux albums et tags : les anciens restent dans Immich.</p>
    <div><Button onclick={enregistrerNoms} disabled={!change || !libelle.trim()}>Enregistrer</Button></div>
    {#if messageNoms}<p class="text-sm" role="status">{messageNoms}</p>{/if}
  </div>
</section>

<section class="mt-4 rounded-2xl border bg-card p-5" aria-label="Restaurer les réglages">
  <h2 class="text-lg font-semibold">Restaurer les réglages</h2>
  <p class="mt-1 text-sm text-muted-foreground">L’Anneau garde chaque nuit une copie des réglages de Chambre noire (noms dans Immich, jamais de clé ni de mot de passe). Choisir une date pour voir ce qui changerait.</p>
  {#if dates && dates.length}
    <div class="mt-3 flex flex-wrap items-end gap-3">
      <label class="grid min-w-0 gap-1 text-sm">Sauvegarde du
        <select bind:value={choix} onchange={voir} class="h-11 rounded-lg border bg-background px-3">
          <option value="">Choisir une date…</option>
          {#each dates as d (d)}<option value={d}>{jour(d)}</option>{/each}
        </select>
      </label>
    </div>
  {:else if dates}
    {#if !messageRestaurer}<p class="mt-3 text-sm text-muted-foreground">Aucune sauvegarde chez l’Anneau pour l’instant.</p>{/if}
  {/if}
  {#if apercu}
    {#if apercu.differences.length}
      <ul class="mt-3 grid gap-2 text-sm" aria-label="Différences">
        {#each apercu.differences as d (d.cle)}
          <li class="min-w-0 break-words border-t pt-2 first:border-t-0 first:pt-0">
            <span class="text-muted-foreground">{NOMS_REGLAGES[d.cle] || d.cle} :</span>
            {valeur(d.actuel)} → <b>{valeur(d.sauve)}</b>
          </li>
        {/each}
      </ul>
      <div class="mt-3 flex flex-wrap gap-2">
        {#if confirmerRestaurer}
          <Button onclick={restaurer}>Confirmer la restauration</Button>
          <Button variant="outline" onclick={() => (confirmerRestaurer = false)}>Non</Button>
        {:else}
          <Button onclick={() => (confirmerRestaurer = true)}>Restaurer ces réglages</Button>
        {/if}
      </div>
    {:else}
      <p class="mt-3 text-sm text-muted-foreground">Les réglages sont déjà ceux de cette sauvegarde.</p>
    {/if}
  {/if}
  {#if messageRestaurer}<p class="mt-3 text-sm" role="status">{messageRestaurer}</p>{/if}
</section>

<section class="mt-4 rounded-2xl border bg-card p-5">
  <h2 class="text-lg font-semibold">Écriture dans Immich</h2>
  <p class="mt-1 text-sm text-muted-foreground">
    <!-- 0.6.0 : la lecture seule vient de toute la maison (MAISON_LECTURE_SEULE) ou de cette appli seule -->
    {session.lecture_seule
      ? session.origine_lecture_seule === 'maison'
        ? 'Lecture seule pour toute la maison (MAISON_LECTURE_SEULE) : Chambre noire lit tout mais n\'écrit rien dans Immich. Pour écrire ici seulement : CHAMBRE_NOIRE_LECTURE_SEULE=non dans la stack.'
        : 'Lecture seule pour cette appli (CHAMBRE_NOIRE_LECTURE_SEULE) : Chambre noire lit tout mais n\'écrit rien dans Immich. À retirer dans la stack quand le premier jour s\'est bien passé.'
      : 'Chambre noire peut écrire dans Immich. Pour le premier jour d\'une nouvelle version : CHAMBRE_NOIRE_LECTURE_SEULE=oui dans la stack (MAISON_LECTURE_SEULE=oui : toute la maison).'}
  </p>
</section>

<p class="mt-6 flex items-center justify-between gap-3 text-sm text-muted-foreground">
  <span>Chambre noire {session.version}</span>
  <Button variant="outline" onclick={deconnecter}>Se déconnecter</Button>
</p>
