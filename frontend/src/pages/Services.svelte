<script>
  // « Connexion » : une tuile par service extérieur, avec son voyant. Toucher une tuile ouvre le service :
  // ce que l'appli y lit, ce qu'elle y écrit, et le geste « Vérifier » (n'écrit rien).
  // (pages/Connexion.svelte est la page du mot de passe : ne pas confondre.)
  import { onMount } from 'svelte'
  import Sun from '@lucide/svelte/icons/sun'
  import ScanFace from '@lucide/svelte/icons/scan-face'
  import Hourglass from '@lucide/svelte/icons/hourglass'
  import { api } from '$lib/api.js'
  import { Button } from '$lib/components/ui/button/index.js'

  let { ondeconnecte } = $props()
  let s = $state(null)
  let choisi = $state(null)
  let message = $state('')
  let attente = $state(false)

  async function lire() {
    attente = true
    message = ''
    try { s = await api.get('/api/services') }
    catch (err) { if (err.statut === 401) ondeconnecte?.(); else message = err.message }
    attente = false
  }
  onMount(lire)

  const voyant = (ok, avertissement) => (ok ? (avertissement ? 'bg-amber-400' : 'bg-valide') : s ? 'bg-destructive' : 'bg-muted-foreground/40')
  let immichAvert = $derived(!!s && (s.immich.manquantes.length > 0 || !s.immich.permissions_lues || !s.libelle))
  const basculer = (nom) => (choisi = choisi === nom ? null : nom)
  const recent = (iso, heures) => !!iso && Date.now() - new Date(iso).getTime() < heures * 3600e3
  const quand = (iso) => new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
</script>

<header class="mb-5">
  <p class="etiquette">Chambre noire</p>
  <h1 class="titre">Connexion</h1>
</header>

<div class="grid grid-cols-2 gap-3 md:grid-cols-4" role="list" aria-label="Services">
  <button type="button" role="listitem" aria-pressed={choisi === 'immich'} onclick={() => basculer('immich')}
          class="flex min-h-28 flex-col gap-1 rounded-2xl border bg-card p-4 text-left transition-colors hover:border-primary aria-pressed:border-primary">
    <span class="flex items-start justify-between">
      <Sun class="size-6 text-primary" aria-hidden="true" />
      <span class="size-2.5 rounded-full {voyant(s?.immich.ok, immichAvert)}" aria-hidden="true"></span>
    </span>
    <span class="font-medium">Immich</span>
    <span class="text-sm text-muted-foreground">
      {#if !s}lecture…{:else if !s.immich.ok}hors service{:else if s.immich.manquantes.length}{s.immich.manquantes.length} permission{s.immich.manquantes.length > 1 ? 's' : ''} manquante{s.immich.manquantes.length > 1 ? 's' : ''}{:else}version {s.immich.version}{/if}
    </span>
  </button>
  <button type="button" role="listitem" aria-pressed={choisi === 'ml'} onclick={() => basculer('ml')}
          class="flex min-h-28 flex-col gap-1 rounded-2xl border bg-card p-4 text-left transition-colors hover:border-primary aria-pressed:border-primary">
    <span class="flex items-start justify-between">
      <ScanFace class="size-6 text-primary" aria-hidden="true" />
      <span class="size-2.5 rounded-full {voyant(s?.apprentissage.ok, false)}" aria-hidden="true"></span>
    </span>
    <span class="font-medium">Visages d’Immich</span>
    <span class="text-sm text-muted-foreground">{!s ? 'lecture…' : s.apprentissage.ok ? `répond en ${s.apprentissage.ms} ms` : 'hors service'}</span>
  </button>
  <button type="button" role="listitem" aria-pressed={choisi === 'millesime'} onclick={() => basculer('millesime')}
          class="flex min-h-28 flex-col gap-1 rounded-2xl border bg-card p-4 text-left transition-colors hover:border-primary aria-pressed:border-primary">
    <span class="flex items-start justify-between">
      <Hourglass class="size-6 text-primary" aria-hidden="true" />
      <span class="size-2.5 rounded-full {s && !s.millesime.ouvert ? 'bg-muted-foreground/40' : voyant(recent(s?.millesime.vu, 3), false)}" aria-hidden="true"></span>
    </span>
    <span class="font-medium">Millésime</span>
    <span class="text-sm text-muted-foreground">{!s ? 'lecture…' : !s.millesime.ouvert ? 'adresse fermée' : s.millesime.vu ? `a lu les noms ${quand(s.millesime.vu)}` : 'n’est jamais venu lire'}</span>
  </button>
</div>

{#if choisi === 'immich' && s}
  <section class="mt-4 rounded-2xl border bg-card p-5" aria-label="Immich">
    <h2 class="text-lg font-semibold">Immich {s.immich.version}</h2>
    <dl class="mt-2 grid gap-x-4 gap-y-1 text-sm md:grid-cols-[8rem_1fr]">
      <dt class="text-muted-foreground">Lit</dt><dd>la version, la clé et ses permissions, les albums</dd>
      <dt class="text-muted-foreground">Écrit</dt><dd>les photos datées, l’album du mois, le tag, la description (nom de l’album), le lancement du rangement ; Annuler : retrait et corbeille</dd>
      <dt class="text-muted-foreground">Libellé</dt><dd>{s.libelle ? `« ${s.libelle} »` : 'absent : à régler dans Réglages › Noms dans Immich'}</dd>
      {#if s.immich.cle_nom}<dt class="text-muted-foreground">Clé</dt><dd>« {s.immich.cle_nom} »</dd>{/if}
    </dl>
    {#if s.immich.erreur}<p class="mt-3 text-sm text-destructive" role="alert">{s.immich.erreur}</p>{/if}
    {#if s.immich.permissions_lues}
      {#if s.immich.manquantes.length}
        <p class="mt-3 text-sm">À ajouter à la clé dans Immich (avatar › Paramètres du compte › Clés API › Modifier) :</p>
        <ul class="mt-1 list-inside list-disc text-sm" aria-label="Permissions manquantes">
          {#each s.immich.manquantes as m}<li><code>{m.permission}</code> — {m.pour}</li>{/each}
        </ul>
      {:else}
        <p class="mt-3 text-sm">Toutes les permissions utiles sont là.</p>
      {/if}
    {/if}
    <div class="mt-4"><Button variant="outline" onclick={lire} disabled={attente}>{attente ? 'Vérification…' : 'Vérifier'}</Button></div>
  </section>
{:else if choisi === 'ml' && s}
  <section class="mt-4 rounded-2xl border bg-card p-5" aria-label="Visages d’Immich">
    <h2 class="text-lg font-semibold">Visages d’Immich</h2>
    <p class="mt-1 text-sm text-muted-foreground">Le service d’apprentissage d’Immich donnera le « haut » de chaque photo, sur le NAS, après la prise (étape 5). Il ne reçoit que des images réduites et n’écrit rien.</p>
    {#if s.apprentissage.erreur}<p class="mt-3 text-sm text-destructive" role="alert">{s.apprentissage.erreur}</p>{/if}
    <div class="mt-4"><Button variant="outline" onclick={lire} disabled={attente}>{attente ? 'Vérification…' : 'Vérifier'}</Button></div>
  </section>
{:else if choisi === 'millesime' && s}
  <section class="mt-4 rounded-2xl border bg-card p-5" aria-label="Millésime">
    <h2 class="text-lg font-semibold">Millésime</h2>
    <p class="mt-1 text-sm text-muted-foreground">Millésime date les photos non datées. Il vient lire ici, à chaque relecture d’Immich, le libellé, l’album et le tag des non datées réglés dans Réglages › Noms dans Immich, et les suit. Chambre noire n’écrit rien dans Millésime.</p>
    <p class="mt-3 text-sm">
      {#if !s.millesime.ouvert}Adresse fermée : pose <code>MAISON_JETON</code> dans la stack (jeton commun des applis maison, le même que lit Millésime).
      {:else if s.millesime.vu}Dernière lecture : {quand(s.millesime.vu)}.{:else}Millésime n’est encore jamais venu lire.{/if}
    </p>
  </section>
{:else}
  <p class="mt-4 text-sm text-muted-foreground">Touche un service pour voir ce que Chambre noire y lit et y écrit.</p>
{/if}
{#if message}<p class="mt-3 text-sm text-destructive" role="alert">{message}</p>{/if}
