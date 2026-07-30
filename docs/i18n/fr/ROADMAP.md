# Feuille de route

<a href="../../../ROADMAP.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/ROADMAP.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/ROADMAP.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="ROADMAP.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="../es/ROADMAP.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

Ceci n'est pas une liste de souhaits. C'est le miroir de ce que le CHANGELOG admet déjà comme
ne fonctionnant pas, plus les dettes contractées sciemment, chacune numérotée pour qu'on puisse
la désigner.

Une feuille de route de fonctionnalités que personne n'a commencées, c'est du marketing. Une
feuille de route d'échecs mesurés, c'est un plan.

## Maturité

Ce sur quoi vous pouvez compter, dit simplement.

| Partie | Maturité | Ce que cela veut dire |
|---|---|---|
| Le contrat AWI | **Stable** | Ajouts seulement au sein de v1 ; une rupture donne une nouvelle version majeure |
| Le cœur du cerveau (orchestrateur, sessions, adaptateurs LLM) | **Bêta** | Fonctionne, et les entrailles bougent encore entre versions |
| Le modèle de confiance | **Bêta** | Les règles sont fixées ; les surfaces autour ne le sont pas |
| Les mondes | **Expérimental** | Chacun existe pour tester une chose, et est réécrit quand cette chose change |

**Ceci est un prototype de recherche, pas un cadre de production.** Il n'a aucune certification
de sécurité et n'a jamais piloté de matériel réel. Voir [SECURITY.md](SECURITY.md).

## Objectifs ouverts

### R1 · L'identification des pièces souffre d'un biais de confirmation

Cinq pièces cibles, une tentative chacune : deux justes, deux fausses, une inachevée. Mesuré en
v1.0 et inchangé depuis.

L'intéressant est ce que ce n'*est pas*. On soupçonnait qu'une cuisine et une salle de bain se
ressemblent depuis 0,38 m — c'est d'ailleurs une des raisons de l'ajout de l'humanoïde — mais à
1,25 m il voit nettement la plaque de cuisson et la hotte, et parle quand même d'une salle de
bain. Face à la même embrasure, le modèle compose l'histoire qui colle à la pièce qu'il cherche
à ce moment-là.

Ce que l'on vise, c'est le critère d'acceptation plutôt que la perception : décrire d'abord,
classer ensuite, et resserrer ce que « je le vois, donc je suis arrivé » a le droit de signifier.

### R2 · Le changement de langue des prompts n'a pas été mesuré

La v1.1 a réécrit en anglais chaque prompt que le modèle lit, jusque-là en chinois — le prompt
système, les descriptions d'outils, les blocs d'état et la `guidance` des mondes.

**C'est un changement de comportement, et le banc d'essai qui trancherait n'a pas été rejoué.**
Le raisonnement est dans `src/prompts.py` : les modèles ajustés aux instructions sont entraînés
majoritairement en anglais, et un prompt chinois enroulé autour de schémas d'outils anglais fait
un contexte mixte. L'effet mesuré dans la littérature est faible, quelques pour cent, et parfois
négatif.

Dette : les mêmes cinq pièces, avant et après, côte à côte. Tant que cela n'existe pas,
« l'anglais est meilleur ici » est une hypothèse, pas un résultat. Si le résultat est pire, le
point de retour arrière tient dans un seul fichier.

### R3 · L'injection de prompt est atténuée, pas résolue

La `guidance` d'un monde est encadrée, étiquetée comme matière plutôt que comme instruction, et
limitée en longueur. Cela relève le niveau. Rien n'y cherche une intention hostile, et aucune
vérification de ce genre ne serait fiable — c'est un problème ouvert pour tout le domaine.

La protection qui fonctionne est l'approbation humaine dans `anima world add`, et elle ne
fonctionne que si la personne lit vraiment le manifeste. Voir [SECURITY.md](SECURITY.md) §2.

### R4 · Quatre CVE de sévérité élevée dans l'arbre npm du frontend

`next`, `postcss`, `sharp` et `@tailwindcss/postcss`, toutes corrigeables dans les bornes
actuelles. Elles concernent la construction et aucune n'atteint le bundle du navigateur, mais
elles sont réelles et connues.

Pas encore fait parce qu'une montée de version majeure de Next demande de vérifier l'interface à
l'œil, ce qui est un travail distinct de la publication.

### R5 · La bibliothèque de règles d'échecs est assez rapide, pas rapide

`packages/anima-chess` est deux à quatre fois plus lente que python-chess selon la position —
assez pour la recherche consultative de profondeur 3 qu'elle sert (1,27 s pour un plafond de
1,5 s), pas assez pour quoi que ce soit de plus profond.

Le coût identifié est que le hachage Zobrist est reconstruit à zéro à chaque coup joué plutôt
que mis à jour de façon incrémentale. C'est documenté dans `push()` comme un choix délibéré, et
c'est la première chose à changer le jour où arrive une table de transposition.

### R6 · Le chinois atteint encore quelques surfaces

La passe linguistique de la v1.1 a fait passer en anglais tout ce qu'un modèle lit et tout ce
que la CLI et l'application web affichent. Quatre endroits sont restés, chacun pour une raison :

- `world/sim-chess/awi_mcp.py` — descriptions de ressources et de prompts MCP. Ce fichier existe
  en **copie identique au bit près à quatre endroits**, dont trois tenus par un test.
  Changer quatre chaînes, c'est changer les quatre d'un même mouvement : pas une chose à faire le
  jour d'une publication.
- `src/dev_turn.py` — un harnais de développement, pas une commande livrée.
- Les descriptions de champs de `src/config.py` et deux lignes de journal de l'orchestrateur —
  usage interne uniquement. Les indications de panneau qu'elles alimentaient sont désormais
  séparées et en anglais.

Trouvés en installant la roue et en la lançant, pas en lisant les sources. Le balayage qui les a
trouvés mérite d'être gardé : parcourir l'AST, collecter les constantes de chaîne qui ne sont pas
des *docstrings*, et y chercher des caractères CJK.

### R7 · Le contrôle de péremption de l'interface était aveugle là où il comptait

`anima serve` affiche la date de construction de l'application web embarquée, afin qu'une roue
empaquetée sans avoir reconstruit l'interface se remarque. Il lisait cette date dans le mtime de
`index.html` — or `pip install` réécrit les mtimes à l'instant de l'installation, si bien que
**toute copie installée se déclarait fraîchement construite**. Le contrôle ne fonctionnait que
dans une copie de travail de développement, là où il était le moins nécessaire.

Corrigé dans le dépôt (la construction écrit un fichier `.build-time`, qui l'emporte désormais
sur le mtime, et un test le fige). **La roue 1.1.0 sur PyPI conserve l'ancien comportement** —
la date de construction qu'elle annonce est sa date d'installation. Rien d'autre de cette
version n'est affecté ; l'interface qu'elle embarque a été vérifiée en lisant la page elle-même,
pas en faisant confiance à l'horodatage.

Trouvé en installant 1.1.0 depuis PyPI et en remarquant qu'elle annonçait une construction six
heures après la construction réelle.

### R8 · Les traductions n'ont été lues par aucun locuteur natif

231 entrées d'interface en japonais, traduites par le mainteneur avec l'aide d'une relecture
indépendante qui a trouvé 22 vrais défauts — une terminologie repliée sur elle-même, un mot
composé inventé, deux phrases ayant perdu un nom en traduction, et quatre étiquettes de barre
latérale assez longues pour être tronquées. Ceux-là sont corrigés. Les documents racine en
japonais, en français et en espagnol sont venus ensuite, par la même méthode. Le français et
l'espagnol n'existent que sous forme de documents ; l'interface parle anglais, chinois et
japonais.

Ce qui n'est pas corrigé, c'est que **personne parlant ces langues n'en a rien lu**. Chaque
relecture était un autre modèle, pas une personne. La terminologie est au moins cohérente à
l'intérieur de chaque langue (world = ワールド / monde / mundo ; ground truth = 真値 / vérité
terrain / verdad de referencia) et aucun paramètre substituable ne manque, ce qui les rend
utilisables comme premiers jets — mais « utilisable comme premier jet » est la revendication,
pas « correct ». L'anglais et le chinois sont les langues du mainteneur et ne portent pas cette
réserve.

### R9 · Deux pages n'ont pas de sélecteur de langue

`/awi` et `/session-logs` s'affichent en pleine page sans la barre latérale, et le sélecteur vit
dans cette barre. Ouvertes directement, elles héritent de la langue présente dans `localStorage`
et n'offrent aucun moyen d'en changer. Atteintes depuis l'application principale, ce qui est le
chemin normal, elles vont bien.

Non corrigé parce que les options honnêtes sont toutes deux plus grandes que le problème : mettre
le sélecteur dans une mise en page partagée par les deux routes, ou accepter que ces deux routes
soient des surfaces secondaires.

### R10 · Neuf dépendances sont sans borne, et l'une d'elles cassera encore la CI

Deux fois en une semaine, un dépôt vert est passé au rouge sans que personne ne change une ligne :
ruff 0.16.0 a élargi son jeu de règles par défaut (205 remarques dans du code non touché), et
mcp 2.0.0 a déplacé `mcp.server.fastmcp`, que `services/boardgame_engine/app.py` importe
directement. Les deux sont désormais bornées. Neuf dépendances d'exécution ne le sont pas.

**C'est délibéré, pas un oubli.** anima-zero est une bibliothèque que des gens installent, et une
borne supérieure dans une bibliothèque publiée devient le problème de résolution de dépendances
de l'*utilisateur* — un problème qu'il ne peut pas contourner. La règle ici est de ne borner que
ce dont on a montré que cela casse, et ce qui a cassé avait une forme commune : les deux
dépendaient de quelque chose de plus profond que la surface publique et documentée (un
sous-module interne ; la configuration par défaut d'un outil). À cette aune, aucune des neuf
restantes ne se qualifie.

Le plan est donc de borner la troisième quand elle cassera. Une CI rouge plus un changement de
deux lignes coûtent une dizaine de minutes ; une borne spéculative coûte à chaque utilisateur
futur. Et l'exécution rouge porte de l'information — c'est ainsi qu'on apprend que l'API en amont
a bougé.

Si un jour les interruptions pèsent plus lourd, le remède est un fichier de contraintes réservé
à la CI, pas davantage de bornes dans `pyproject.toml` : la CI installe des versions figées
tandis que le paquet publié reste permissif. Cela a son propre prix — une chose de plus à
maintenir, et cela *retarde* le moment où l'on découvre que l'amont a changé. Le raisonnement est
écrit en tête de la liste des dépendances, là où se tient celui qui est tenté d'ajouter une borne.

## Non prévu

Dire non fait partie d'une feuille de route.

- **Chess960, PGN, livres d'ouvertures, UCI** dans `anima-chess` — utilisez python-chess, qui est
  meilleur sur tous ces points.
- **Un installateur en curl.** ANIMA est en Python et ses mondes sont en Python ; ceux qui le
  lanceraient ont déjà Python. `uv tool install` donne la même expérience en une commande sans
  ajouter un second canal de distribution à tenir honnête.
- **Rendre le cerveau plus malin sur un monde particulier.** Le savoir spécifique à une tâche vit
  dans le monde. Le jour où l'orchestrateur apprend ce qu'est le jeu d'échecs, la prétention à
  être un cadre générique s'arrête.
