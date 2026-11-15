<script>
  // « Scanner » : l'écran de travail. 0.1.0 = squelette : la prise de vue (caméra, détection, trois modes)
  // arrive à l'étape 3 du plan (docs/dossier.md § 6). D'ici là, Scan Immich reste l'outil de numérisation.
  import Images from '@lucide/svelte/icons/images'
  import File from '@lucide/svelte/icons/file-image'
  import BookOpen from '@lucide/svelte/icons/book-open'

  const modes = [
    { nom: 'Rafale', icone: Images, texte: 'Plusieurs tirages d’affilée, puis revue, date et envoi groupés.' },
    { nom: '1 photo', icone: File, texte: 'Prise, aperçu, date et envoi, puis la suivante.' },
    { nom: 'Page d’album', icone: BookOpen, texte: '1 à 4 tirages découpés par prise, une date par page.' },
  ]
</script>

<header class="mb-5">
  <p class="etiquette">Chambre noire</p>
  <h1 class="titre">Scanner</h1>
</header>

<section class="rounded-2xl border border-primary/40 bg-card p-5" aria-label="État">
  <h2 class="text-lg font-semibold">La prise de vue arrive à l’étape 3</h2>
  <p class="mt-1 text-sm text-muted-foreground">
    Cette première version vérifie le lien avec Immich (écran Connexion). Pour numériser aujourd’hui,
    utilise Scan Immich, comme d’habitude.
  </p>
</section>

<ul class="mt-4 grid gap-3 md:grid-cols-3" aria-label="Modes prévus">
  {#each modes as m}
    {@const Icone = m.icone}
    <li class="flex gap-3 rounded-2xl border bg-card p-4 opacity-70">
      <Icone class="mt-0.5 size-6 shrink-0 text-primary" aria-hidden="true" />
      <span><span class="font-medium">{m.nom}</span><br /><span class="text-sm text-muted-foreground">{m.texte}</span></span>
    </li>
  {/each}
</ul>
