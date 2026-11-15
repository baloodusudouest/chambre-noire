<script>
  // « Réglages » : ce qui n'est pas un service. Toujours en bas : la version et la déconnexion.
  import { Button } from '$lib/components/ui/button/index.js'
  let { session, deconnecter } = $props()
</script>

<header class="mb-5">
  <p class="etiquette">Chambre noire</p>
  <h1 class="titre">Réglages</h1>
</header>

<section class="rounded-2xl border bg-card p-5">
  <h2 class="text-lg font-semibold">Écriture dans Immich</h2>
  <p class="mt-1 text-sm text-muted-foreground">
    {session.lecture_seule
      ? 'Lecture seule : Chambre noire lit tout mais n\'écrit rien dans Immich. À retirer dans la stack (CHAMBRE_NOIRE_LECTURE_SEULE) quand le premier jour s\'est bien passé.'
      : 'Chambre noire peut écrire dans Immich. Pour le premier jour d\'une nouvelle version : CHAMBRE_NOIRE_LECTURE_SEULE=oui dans la stack.'}
  </p>
</section>

<p class="mt-6 flex items-center justify-between gap-3 text-sm text-muted-foreground">
  <span>Chambre noire {session.version}</span>
  <Button variant="outline" onclick={deconnecter}>Se déconnecter</Button>
</p>
