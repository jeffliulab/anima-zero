# Journal des modifications d'Anima Zero

<a href="../../../CHANGELOG.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/CHANGELOG.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/CHANGELOG.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="CHANGELOG.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="../es/CHANGELOG.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

Notes de version d'ANIMA Zero. **À garder courtes : par version, seulement ce qui a réellement
changé.** (Format inspiré de [Keep a Changelog](https://keepachangelog.com).)

## [1.2.0] — 2026-07-31

L'essentiel : les cinq premières minutes sont de retour — `anima demo` prouve que toute la
chaîne fonctionne sur n'importe quelle machine, avec ou sans clé API — et le dépôt est prêt
à accueillir des visiteurs : une FAQ, une porte d'entrée pour les contributeurs, zéro alerte
CVE, et les deux défauts de packaging qui expédiaient silencieusement la mauvaise chose sont
corrigés et surveillés en CI.

1. **Le retour d'`anima demo`, sans rien de ce que l'ancien coûtait.** Un monde-couloir
   d'environ 300 lignes (un point, `look`, `step`, une vraie image caméra) est livré dans le
   paquet, écrit à la main d'après la spec AWI — aucune copie à l'octet près, aucun
   sous-module, aucun desk en double dans chaque liste de mondes : les trois choses qui ont
   tué le monde desk de la v1.1. La démo le lance sur un port libre et choisit un cerveau
   à voix haute : votre clé API si vous en avez une, sinon un **cerveau local sur CPU**
   (Qwen3-4B-Instruct-2507 via Ollama, ~2,5 Go, proposé en une ligne de pull — la plus
   petite taille à l'appel d'outils vraiment fiable), sinon le mock honnête. Le couloir
   sert aussi de modèle pour écrire votre propre monde
   (`src/examples/minimal_world.py`, exécutable seul avec
   `python -m anima.examples.minimal_world`). En coulisses, la boucle respecte désormais
   `llm.vision` : un cerveau qui ne voit pas ne reçoit plus d'images.
2. **Le parcours du nouvel utilisateur est dégagé.** gazebo-chess quitte la liste des
   mondes par défaut (son code vit désormais dans le dépôt compagnon ; définissez
   `GAZEBO_CHESS_URL` et il revient, rien de perdu) ; le tampon `.build-time` entre enfin
   dans le wheel, donc `anima serve` indique l'heure de construction réelle de l'UI aux
   utilisateurs pip, et la CI prouve à chaque push que le wheel embarque l'UI fraîche et
   son tampon ; le nouveau `docs/faq.md` (anglais et chinois) couvre les six pièges
   réels des nouveaux utilisateurs ; et `/awi` comme `/session-logs` ne renvoient plus
   404 quand on les ouvre directement — ils ont aussi gagné leur propre sélecteur de
   langue (ROADMAP R9, clos).
3. **Zéro alerte CVE** (ROADMAP R4, clos) : Next 15 → 16, avec `postcss`/`sharp` épinglés
   au-delà des avis via `overrides`. `npm audit` est propre ; l'interface a été revérifiée
   à l'œil après le saut de version majeure.
4. **Une porte d'entrée pour les contributeurs** : CONTRIBUTING gagne une section
   « Where to start » (écrire un monde depuis le modèle du couloir / relire une traduction /
   good first issues), plus `CITATION.cff` et un badge PyPI.

## [1.1.1] — 2026-07-30

Main : le monde desk et `anima demo` ont disparu. Le monde livré dans le wheel existait pour que `pip install` mène quelque part ; il coûtait deux copies identiques au bit près, un sous-module git et un second desk dans chaque liste de mondes — plus qu'il ne valait.

1. **Les deux mondes desk supprimés, et `anima demo` avec eux** : celui qui voyageait dans le wheel et le sous-module `sim-desk` à côté. ⚠️ **`pip install anima-zero` vous donne désormais le cerveau et aucun monde.** Un monde est un programme séparé : clonez ce dépôt pour ceux de `world/`, ou écrivez le vôtre selon la spécification AWI. Le cerveau factice est inchangé et reste sélectionnable.
2. **Le README vous confie à un agent de code** : là où l'installation exhibait une démo en une commande, elle explique maintenant que l'étape suivante est d'obtenir un monde, et que le plus rapide est de donner le dépôt à Claude Code ou Codex et de le laisser lire `AGENTS.md`.
3. **La conformité ne teste plus le monde que nous livrons par hasard** : le contrôle de bout en bout démarre désormais un **monde minimal écrit d'après la spécification dans le test lui-même** — huit cases, un outil, un vrai PNG — et décode cette image au lieu de croire le type mime déclaré. ⛔ Il échoue au lieu de se sauter quand la cible ne démarre pas.
4. **Le dépôt n'a plus aucun sous-module**, `awi_mcp.py` passe de six copies identiques au bit près à quatre, et seule celle de soma-zero est désormais hors de ce dépôt.

## [1.1.0] — 2026-07-27

L'essentiel : passer d'un dépôt de portfolio à un projet que d'autres peuvent installer,
connecter et pour lequel ils peuvent écrire des mondes — tout le dépôt repassé sous **MIT** (en
écrivant nous-mêmes de quoi sortir de la dernière dépendance non permissive),
`pip install anima-zero` suivi d'une vraie commande `anima` et d'une application web, **un monde
traité comme une partie distante non fiable**, et l'AWI transformée en spécification écrite,
avec un vérificateur.

Nouveautés :

1. **Relicencié sous MIT ; l'offre de double licence commerciale est retirée.** L'obstacle était
   python-chess, sous GPL, alors nous **avons écrit notre propre bibliothèque de règles**
   (`packages/anima-chess` — bitboards et hachage Zobrist, MIT) : le perft correspond aux valeurs
   publiées sur les six positions standard, et une recherche de profondeur 3 en milieu de partie
   prend 1,27 s pour un plafond consultatif de 1,5 s. ⚠️ Elle est **deux à quatre fois plus
   lente** que python-chess — assez pour cet unique usage, pas pour quoi que ce soit de plus
   profond ; la cause et le remède sont consignés en R5 de la feuille de route. La suite de tests
   passe avec python-chess désinstallé. Les 69 dépendances ont été auditées : aucune non
   permissive.
2. **Ça s'installe et ça tourne** : `pip install anima-zero` vous donne la commande `anima`
   (`demo` / `chat` / `run` / `serve` / `doctor` / `world` / `conformance`). L'application web est
   exportée en statique et **voyage à l'intérieur de la roue**, si bien qu'`anima serve` vous
   tend une interface sur une machine sans node. Un **monde bureau intégré** et un **cerveau
   factice ne demandant aucune clé** sont livrés avec, de sorte qu'`anima demo` montre toute la
   boucle en une commande : image, décision, appel d'outil, résultat. ⚠️ Publier est désormais
   couplé à la construction de l'interface (`build_ui.py` avant `python -m build`), et
   `anima serve` affiche la date de construction de l'appli web — parce que **livrer un paquet
   avec une interface périmée est exactement le genre de chose que personne ne remarquerait.**

   > ⚠️ **Remplacé en v1.1.1** : le monde desk intégré et `anima demo` ont été supprimés. La
   > commande `anima`, l'appli web embarquée dans le wheel et le cerveau factice sont intacts.
3. **⭐ Un monde est traité comme une partie distante non fiable.** La `guidance` d'un monde est
   jointe au **prompt système** du cerveau et ses descriptions d'outils deviennent la **liste
   d'outils** — le tout écrit par quelqu'un d'autre. Donc : le contenu d'un monde **n'atteint pas
   le cerveau tant que vous ne l'avez pas lu et approuvé** (il apparaît toujours dans la liste, et
   indique toujours s'il est en ligne) ; l'approbation **porte sur l'empreinte d'un manifeste**
   (SHA-256 de l'URL, du nom, du kind, de la description et du schéma de chaque outil, et de la
   `guidance` intégrale), et **un manifeste modifié vous redemande votre accord en vous disant ce
   qui a changé** — c'est ce qui défait un rug pull ; la `guidance` est **encadrée** avant
   d'entrer dans le prompt système et étiquetée comme matière plutôt que comme instruction, les
   marqueurs d'encadrement étant retirés du texte du monde, avec des limites de longueur.
   ⛔ Le **portail de sécurité a lui aussi été repris au monde** : l'orchestrateur ne le
   consultait que pour les outils que le monde n'avait pas marqués en lecture seule ; un monde
   pouvait donc **sauter le portail entièrement** en annotant un outil destructeur d'un
   `readOnlyHint: true`. Toute action passe désormais par le portail, `kind` n'étant qu'une
   entrée de la décision. Inoffensif tant que le portail restait ouvert en simulation, et un trou
   le jour où il se fermera pour du matériel réel. `ANIMA_TRUST_ALL=1` est une issue de secours de
   développement. Tout le modèle de menace est figé par une fixture de monde malveillant
   (`tests/test_world_trust.py`). ⚠️ **L'injection de prompt est atténuée, pas résolue** — voir
   R3 de la feuille de route.
4. **L'AWI est devenue une spécification** : `docs/awi-spec-v1.md` (anglais et chinois) énonce
   chaque canal, ce qui est requis face à ce qui est recommandé, et ce que l'hôte fait de ce
   qu'un monde envoie — y compris une section sur le fait que **`kind` est une déclaration et non
   une garantie**. Avec elle vient `anima conformance <url>`, qui se connecte à un monde, exerce
   chaque canal et rapporte chaque vérification en citant la section dont elle provient — y
   compris la vérification de **l'ordre des caméras**, qui mérite sa place parce que les blobs
   d'image ne portent pas de nom, que leur ordre est la seule chose qui relie une image à une
   caméra, et qu'un décalage reste silencieux partout ailleurs. ⛔ Elle **énonce ses propres
   limites à chaque fois** : l'état laisse-t-il fuiter une vue divine, le `kind` correspond-il au
   comportement, la `guidance` est-elle honnête — aucune vérification automatique ne tranche cela.
   Une personne le fait, au moment d'approuver.
5. **La langue, partagée par public** : tout ce qu'un modèle lit — prompt système, descriptions
   d'outils, blocs d'état, `guidance` de chaque monde — est désormais **en anglais, en une seule
   version**, rassemblé dans `src/prompts.py`, se terminant par une ligne qui lui demande de
   répondre dans la langue de l'utilisateur. Les documents que lisent les gens existent en
   plusieurs langues. La CLI et l'appli web sont en anglais par défaut. ⚠️ **C'est un changement
   de comportement, et le banc d'essai qui trancherait n'a pas été rejoué** — la comparaison de
   navigation sur cinq pièces, avant et après, est une dette reconnue, consignée en R2.
   Tant qu'elle n'existe pas, « l'anglais est meilleur ici » est une hypothèse. Si le résultat est
   pire, le point de retour arrière tient dans un fichier. ⚠️ La première passe est passée à côté
   de beaucoup : les blocs de monde de l'orchestrateur, le cadrage d'image envoyé avec chaque
   image, les motifs du portail de sécurité, les avis de troncature, toutes les erreurs de
   backend affichées par l'appli web et les réponses du cerveau factice lui-même étaient encore
   en chinois alors que cette affirmation était déjà écrite. Ils ont été trouvés en installant la
   roue et en la lançant, pas en lisant les sources. Ce qu'il reste, et pourquoi, c'est R6.
6. **Des gardes mécaniques, et des dettes consignées** : `scripts/selfcheck.py` transforme quatre
   règles de la maison qui ne vivaient que dans un carnet local en gardes de CI (l'orchestrateur
   reste exempt de logique spécifique à une tâche / pas de configuration morte / pas de
   bouche-trou non déclaré / la version concorde à trois endroits), et **chacune a été testée par
   la négative** — la garde sur la configuration morte était cassée dans sa première version et
   serait restée verte pour toujours sans cela. Nouveau `ROADMAP.md` (dans les deux langues) :
   **pas une liste de souhaits, mais le miroir des échecs mesurés et des dettes assumées**,
   chacune numérotée — R1 le biais de confirmation, R2 le changement de langue non mesuré, R3
   l'injection non résolue, R4 quatre CVE de sévérité élevée dans l'arbre npm du frontend, R5 la
   vitesse de la bibliothèque d'échecs.

**Limites mesurées, consignées honnêtement** : la navigation entre pièces est **inchangée**
depuis la v1.0 — cinq cibles, deux justes, deux fausses, une inachevée. Rien dans cette version
ne visait cela. Cette version portait sur la question de savoir si quelqu'un d'autre peut se
servir du projet, pas sur son intelligence. R1 est ce qui vise le reste.

## [1.0.1] — 2026-07-26

L'essentiel : correction de deux défauts du panneau de la v1.0 — il n'avait aucune limite de
hauteur et chassait entièrement la liste des sessions de la barre latérale, et il n'était pas au
bon endroit.

1. **Hauteur plafonnée et repliable** : le nombre de notes n'est pas borné (capacité par défaut :
   20), et sans plafond douze notes écrasaient mesurablement la liste des sessions.
2. **Déplacé au-dessus de la conversation** : c'est l'état de la **session courante**, mais il se
   trouvait en bas de la barre latérale parmi les éléments **globaux** (paramètres d'exécution,
   tableau de bord AWI, apparence) — il avait l'air global et se trouvait à un demi-écran de la
   session à laquelle il appartenait. L'épingler au-dessus de la conversation fait aussi qu'**il
   ne défile plus hors de vue** : durant un tour long, on voit toujours ce qu'il fait ; replié il
   tient sur une ligne et sert de barre d'état (avec une tâche centrale, il affiche simplement
   « en train de… »).
3. **Abandon de « mémoire de travail » comme terme générique** : l'expression n'apparaît nulle
   part dans le code et laissait croire que la tâche centrale et le carnet ne faisaient qu'un.
   Ils sont désormais montrés pour ce qu'ils sont — la **tâche centrale** (ce que je fais, une
   phrase, mise à jour par réécriture) et le **carnet** (ce que j'ai trouvé, entrée par entrée,
   mis à jour par ajouts et retraits).

## [1.0.0] — 2026-07-26

L'essentiel : le robot peut **changer de corps, se souvenir de son chemin et ne pas rentrer dans
les meubles** — le monde est passé d'« un chien » à « un corps interchangeable » (un humanoïde
Unitree G1 a été ajouté, avec une politique de virage entraînée spécialement pour lui), le
cerveau a gagné une mémoire de travail générique, et l'AWI un canal formel. En même temps, **la
liste des réponses fournie au cerveau a été purement supprimée** : ce que ce monde éprouve, c'est
la capacité à deviner dans quelle pièce on est en regardant, et un score obtenu en donnant les
réponses ne veut rien dire.

Nouveautés :

1. **Un monde, deux corps** : `sim-house-nav` ne code plus rien en dur pour le quadrupède —
   modèle, politique, caméra, hauteur d'apparition et façon d'envoyer le couple viennent tous du
   manifeste de robots de la bibliothèque d'actifs (⛔ les deux sont **opposés** : PD explicite
   pour le quadrupède, PD implicite pour l'humanoïde ; inversez-les et il tombe immédiatement).
   L'humanoïde a 29 degrés de liberté et des yeux à 1,25 m, et voit une pièce complètement
   différente depuis le même endroit. Une **politique de virage a été entraînée spécialement pour
   lui** (plage de consigne de lacet élargie de ±0,2 à ±0,8, 10 000 itérations) — ⚠️ il **ne peut
   toujours pas pivoter sur place** (à l'arrêt, la politique prend l'option la moins coûteuse) :
   un virage emporte donc 0,3 m/s d'avance, et un virage à 90° le déplace de 0,6 à 0,8 m. Le monde
   **rapporte ce déplacement honnêtement**.
2. **Un nouveau canal AWI pour la configuration d'un monde** : un monde **déclare** ce qui peut y
   être configuré (la nouvelle ressource MCP `anima://config`), et une personne le change par
   **HTTP hors bande** — changer la configuration est une action humaine, et le cerveau est
   seulement informé du corps qu'il a désormais, comme un vrai robot sait quel corps il est.
   ⛔ Le prompt dit clairement qu'il ne peut pas changer cela : le cerveau n'a aucun outil pour le
   faire, et laisser entendre le contraire ne fait que le pousser vers quelque chose qui n'existe
   pas. Cela a aussi corrigé le piège de la v0.9 où les capacités sont mises en cache à la
   première poignée de main : un monde ayant gagné un outil sans redémarrage du backend ne le
   voyait jamais arriver dans la liste d'outils — l'appli web a désormais un bouton pour refaire
   la poignée de main.
3. **Un registre carnet, et la clé de correction retirée** : la tâche centrale contient « ce que
   je fais » (une phrase) et le nouveau carnet contient « ce que j'ai trouvé » (des entrées
   ajoutées et retirées). Les deux sont injectés en permanence et ne glissent pas hors du contexte
   à mesure que la conversation s'allonge. Les trois refus — vide, trop long, plein — disent
   pourquoi, et **ne tronquent ni ne jettent jamais en silence**. En même temps, la `guidance` du
   monde a perdu son inventaire de meubles et son tableau de repères pour douze pièces
   (1180 → 844 caractères). ⚠️ **Mesuré : retirer les réponses n'a rien changé** (deux cibles sur
   cinq, comme avant) — cette liste n'avait donc jamais servi à rien. Et le carnet a rendu la
   vraie cause visible pour la première fois : il décrit ce qui se trouve derrière une porte comme
   étant la pièce qu'il cherche à ce moment-là. Biais de confirmation.
4. **Télémétrie laser, freinage et caméra de poursuite** : une télémétrie sur huit directions
   entre dans la perception (un vrai Go2 porte un lidar L1 sur la tête), et en avançant il freine
   et se met debout quand il approche trop, en rapportant honnêtement la place qu'il reste —
   ⛔ il s'arrête, il ne dirige pas ; où aller ensuite reste toujours la décision du cerveau. La
   vue de poursuite à la troisième personne est **réservée aux humains** : `/streams` marque
   chaque vue d'un `awi`, la page web scinde le panneau de capteurs en conséquence, et ranger la
   vue de poursuite sous « ce qu'ANIMA voit » serait un mensonge. Des tests tiennent cette ligne.
5. **Le contrat de monde est devenu un modèle** (`world/README.md`) : les deux lignes, AWI et hors
   bande, et une question pour les distinguer — est-ce pour le cerveau ou pour une personne ?
   Plus six gardes mécaniques vérifiant la complétude de l'enregistrement (le monde est-il dans
   `.env.example`, est-il dans la liste anti-dérive, les mondes multi-vues marquent-ils bien
   `awi`, …).

**Limites mesurées, consignées honnêtement** : la navigation de proximité est solide (quadrupède,
« va à la cuisine » en 10 pas / 41 s, « va au salon » en 9 pas / 32 s ; l'humanoïde a réussi les
deux aussi). Mais **la navigation entre pièces reste peu fiable** : sur cinq cibles, deux justes,
deux fausses, une inachevée — identique pour les deux corps. ⭐ Cette version a **réfuté
l'hypothèse de la v0.9 sur la cause** : on soupçonnait qu'une cuisine et une salle de bain se
ressemblent depuis un point de vue bas, mais l'humanoïde à 1,25 m voit nettement la plaque et la
hotte et **parle quand même d'une salle de bain**. Ce n'est donc pas qu'il ne voit pas. C'est un
biais de confirmation : face à la même embrasure, il compose l'histoire qui colle à la pièce qu'il
cherche. La prochaine version vise le critère d'acceptation (décrire d'abord, classer ensuite ;
resserrer ce que « je le vois, donc je suis arrivé » peut signifier), pas la perception. Les
tentatives qui ont fonctionné sont dans `world/sim-house-nav/实测记录.md`.

## [0.9.0] — 2026-07-25

L'essentiel : un nouveau monde, **sim-house-nav** — un quadrupède Unitree Go2 dans une maison, où
ANIMA ne voit que la caméra avant posée sur sa tête et doit juger d'après les meubles où il se
trouve, puis l'y conduire. Avec cela, « un tour » est passé de **un mouvement puis stop** à **une
chose, menée à son terme**, et les tours longs ont reçu un frein.

Nouveautés :

1. **Le nouveau monde sim-house-nav (:8112)** : une vraie démarche de quadrupède dans MuJoCo —
   trois primitives de navigation (avancer, gauche, droite) sont traduites en consignes de vitesse
   `(vx, vy, wz)` données à une politique entraînée, si bien que le chien marche vraiment au lieu
   de se téléporter. Les primitives s'exécutent **en boucle fermée** (une démarche apprise ne suit
   une consigne de vitesse qu'à environ 83 % et 62 %, elle mesure donc en chemin et s'arrête une
   fois arrivée) et rapportent honnêtement quand un mur l'en empêche. L'observation porte
   **l'image, le cap de l'IMU et la chute éventuelle** — ⛔ aucune coordonnée et aucun nom de
   pièce ; les pièces doivent être reconnues en regardant. Les scènes et les modèles de robots ont
   été extraits dans une bibliothèque d'actifs séparée, montée par configuration.
2. **Un tour est une chose** (une révision du point 1 de la 0.8, pas un abandon de la discipline) :
   la fin d'un tour est **décidée par ANIMA produisant de la prose**. La limite de pas est passée
   de 8 à 60 et une limite de 900 secondes de temps réel a été ajoutée, toutes deux rétrogradées
   au rang de **ceintures de sécurité plutôt que de métronomes**. Aux échecs, « une chose » reste
   un coup (2 à 6 pas, se terminant naturellement, comportement inchangé) ; en navigation, c'est
   trouver la pièce cible (des dizaines de pas, menés jusqu'à convergence). ⛔ Le « jouer une
   partie entière à partir d'une phrase » rejeté en v0.7 reste rejeté — c'était **plusieurs
   choses** entassées dans un tour, ce qui n'a rien à voir avec la limite de pas.
3. **Un frein et une fenêtre pour les tours longs** : interruption au niveau de la session
   (`POST /api/sessions/{sid}/interrupt`), le bouton Envoyer de l'appli web devenant Arrêter
   pendant la génération. L'interruption atteint jusqu'à l'attente d'une action : l'actionner ne
   signifie donc pas attendre que le chien finisse son pas. Atteindre une limite est une pause
   polie (la tâche centrale reste au registre et « continue » reprend), et chacun des trois motifs
   dit ce qu'il a à dire. Le panneau de réflexion a reçu une hauteur plafonnée avec défilement, des
   numéros de pas et un pliage/dépliage, et les principaux paramètres d'exécution siègent en
   permanence en bas à gauche, lus depuis le backend plutôt qu'écrits dans le frontend.
4. **Lui faire retenir ce qu'il fait** : le prompt système et la `guidance` du monde ont gagné
   « termine une chose d'un seul tenant », « pour une tâche en plusieurs pas, enregistre d'abord
   la tâche centrale » et « réécris ton avancement dans le registre en chemin » — dans un tour
   long, les images vues plus tôt glissent hors du contexte, et ce registre est la seule chose qui
   n'en sort pas.

**Limites mesurées, consignées honnêtement** : la navigation de proximité fonctionne — « va à la
cuisine », trouvée et identifiée en 7 pas / 45 s. Mais **la navigation entre pièces n'est pas
encore fiable** : quatre pièces cibles, une tentative chacune, une juste et trois fausses (deux
pièces mal identifiées, une arrêtée à mi-chemin), et il tourne en rond sur les longues distances.
Depuis un point de vue bas, la cuisine et la salle de bain sont difficiles à distinguer (les deux
sont « plan de travail, portes de placard, panneau blanc »). La quatrième primitive `look_around`
a été implémentée mais **jamais mesurée** — le cerveau met les capacités en cache à la première
poignée de main, et elle n'a jamais atteint la liste d'outils pendant les expériences.

## [0.8.0] — 2026-07-25

1. Le nombre maximal de pas par tour est fixé à 8 par défaut. Pour l'instant le système est
   strictement au tour par tour ; les boucles longues sont hors sujet.
2. La configuration centrale est passée à pydantic-settings : validation de type qui échoue tôt,
   chaque paramètre avec une description et une borne inférieure. Les noms de variables
   d'environnement et l'interface consommatrice `config.*` sont inchangés, et `.env` agit désormais
   sur **tous** les paramètres (il n'atteignait auparavant que les listes de mondes et de services).

## [0.7.0] — 2026-07-06

L'essentiel : le monde gazebo-chess a gagné la capacité de **jouer une partie entière** — à partir
d'une phrase, ANIMA joue seul une partie complète (des dizaines de coups de préhension et de dépôt
physiques, avec prises, roque et promotion passant tous par de vraies primitives), tandis que le
monde tient un arbitre et un adversaire informatique qui se téléporte, la partition finale étant
archivée pour la notation. **Pas une ligne du cerveau n'a changé** — seul `ANIMA_MAX_STEPS` a
augmenté — ce qui constitue en soi l'épreuve de terrain de l'affirmation selon laquelle changer de
monde coûte une URL.

Nouveautés :

1. **Une partie entière** : le monde gazebo-chess tient un **arbitre** (un portail de légalité
   avant que le bras ne bouge, une vérité qui n'avance qu'après vérification physique de chaque
   primitive, la détection de fin de partie et une partition archivée) et un **adversaire
   informatique qui se téléporte** (il répond dès que le cerveau termine un coup, sans annoncer ce
   qu'il a joué, de sorte que le cerveau doit le voir — une troisième copie indépendante du moteur,
   à ne surtout pas fusionner avec les deux autres), plus les pièces prises qui vont dans une
   corbeille et la **récupération depuis une pièce de réserve** (quand une pièce quitte
   définitivement l'échiquier, en reposer une identique sur sa case réaligne la position avec la
   partition) et un bouton « nouvelle partie ». Zéro changement côté cerveau ; deux parties
   complètes mesurées (38 et 44 coups). Les partitions finales alimentent le noteur, qui rapporte
   le taux de réussite des primitives et la latence par monde — les échecs physiques et les coups
   illégaux ne sont jamais confondus. L'ancien mode à une seule pièce de démonstration, sans FEN,
   se comporte exactement comme avant.
2. **Toutes les cases atteignables, et de vraies pièces** : la préhension est passée à une
   **inclinaison radiale** plus une géométrie mesurée directement (10 cm depuis l'axe, cases de
   4,5 cm — deux valeurs par défaut mesurées, toutes deux surchargeables par l'environnement) →
   **les 64 cases atteignables**, corrigeant le « toute la colonne h est inatteignable » de la
   v0.5 (`scripts/reach_map.py` le reproduit en une commande). La **diversité des reprises**
   transforme une case maudite de façon déterministe en une case qui réussit au premier changement
   de posture. Les pièces sont devenues de **vrais maillages Staunton** (CC-BY 4.0, source et
   licence dans le dépôt ; corps de collision inchangés).
3. **Un registre de tâche centrale par session** (l'unique changement côté cerveau, et un mécanisme
   générique) : une session d'endurance a mesuré la défaillance — la tâche glisse hors de la
   fenêtre de contexte et le cerveau s'arrête en chemin. « Sur quelle tâche suis-je » est un
   **état**, pas de l'historique de conversation. Le LLM l'enregistre, le réécrit et l'efface
   **lui-même** par les méta-outils intégrés `set_core_task` et `clear_core_task` (pas de
   mots-clés, pas d'épinglage, pas d'heuristiques), et il est injecté en permanence dans le prompt
   système comme canal d'état plutôt que d'occuper la fenêtre d'historique. Le comportement au tour
   par tour est inchangé : il s'arrête après chaque coup et attend.
4. **Changement de licence** : tout le dépôt est passé d'Apache-2.0 à **AGPL-3.0 plus double
   licence commerciale.** Ce qui compte avec l'AGPL-3.0, c'est que **fournir un service par le
   réseau** oblige aussi à ouvrir les sources correspondantes. Les intégrations commerciales en
   source fermée peu disposées à cela pouvaient contacter le mainteneur pour une licence
   commerciale. Compatible avec python-chess sous GPL-3 ; les versions jusqu'à la v0.6.0 restent
   disponibles sous l'Apache-2.0 d'origine.
   > ⚠️ **Remplacé par la v1.1** : tout le dépôt est sous **MIT** depuis la v1.1, et la double
   > licence commerciale est retirée avec elle (MIT autorise déjà l'usage commercial en source
   > fermée). Ce qui l'a rendu possible, c'est le remplacement de python-chess par notre propre
   > bibliothèque de règles sous MIT. Les versions v0.7.0 à v1.0.1 restent sous les conditions
   > AGPL-3.0 avec lesquelles elles ont été livrées. L'historique complet des licences est dans
   > [NOTICE](../../../NOTICE).

## [0.6.0] — 2026-07-03

L'essentiel : les moteurs ont été rapatriés dans le dépôt et le monde et les services entièrement
découplés, le montage des services revenant à l'« assemblage par l'hôte » du MCP standard —
nettoyer les frontières avant de viser le matériel réel. En bref : l'hôte et les services sont
désormais indépendants l'un de l'autre. Le serveur de moteur parle à l'hôte ANIMA, le serveur de
monde parle à l'hôte ANIMA, et le serveur de monde et le serveur de moteur ne se parlent plus du
tout.

Nouveautés :

1. Les trois cœurs de moteur de jeux de plateau (échecs, gomoku, go) ont été déplacés dans
   `services/boardgame_engine/` — ils lisaient auparavant des fichiers d'un autre dépôt via
   importlib, si bien qu'un clone frais ne démarrait pas. Le service a été renommé boardgame-engine,
   les trois outils d'échecs sont actifs, et le go et le gomoku sont en place en attente d'un
   consommateur. Le dossier externe `3-anima-chess-engine` a été supprimé ; le dépôt tient debout
   seul.
2. Le conseiller moteur du cerveau et l'adversaire informatique intégré au monde sim-chess ont été
   scindés en deux copies délibérément indépendantes (`chess_engine.py` et `chess_bot.py`, sans
   code partagé, à ne pas fusionner) : moteur de service éteint, l'ordinateur du monde continue de
   jouer, et le conseiller voyage avec le cerveau d'un corps à l'autre.
3. Le « un monde déclare ses services » de la v0.5 (`anima://services`) a été aboli au profit d'un
   cerveau qui les monte lui-même via `config.services()`, symétriquement à `worlds()` — conforme
   au principe MCP selon lequel le choix des serveurs à connecter regarde l'hôte, et les serveurs
   ne se connaissent pas entre eux. L'appariement se fait par le modèle qui regarde l'image et
   choisit un outil, pas par une liaison structurelle.
4. Nommage unifié des trois couches MCP et modèle de la « ligne dédiée » : il y a exactement deux
   sortes de serveurs — le **World Server** (la réalité, les trois primitives) et l'**Engine
   Server** (un conseiller, des outils uniquement). L'hôte (le cerveau ANIMA) ouvre une ligne
   dédiée vers chacun, ce qui est la couche client (`RemoteWorld` / `RemoteService` dans le code,
   une ligne pour un serveur). Une ligne retient l'adresse, met les capacités en cache à la poignée
   de main, traduit le protocole, gère les délais selon le rôle (supervision de vie pour un monde,
   court délai de question pour un moteur) et tient les comptes. Les lignes ne se parlent pas :
   c'est ainsi que l'isolation des serveurs est réalisée. Le §4 du README et la page `/awi` ont été
   mis à jour en conséquence.

## [0.5.0] — 2026-07-03

L'essentiel : une grande refonte — l'orchestration conçue par un humain, comme le mode partie, a
été supprimée, minimisant le cadre afin d'examiner l'intelligence : le LLM regarde l'image
lui-même, décide chaque pas lui-même et appelle les outils lui-même.

Nouveautés :

1. **Une sémantique de signes de vie pour les actions longues** (une correction du cadre) : une
   action physique prend des dizaines de secondes, le délai fixe de la v0.4 la tuait, et les mondes
   exécutaient le travail sur la boucle d'événements, si bien qu'un seul coup gelait tout le
   serveur de monde. Adoption des **notifications de progression MCP** à la place : le monde
   exécute l'outil sur un fil de travail et rapporte une progression lisible par étapes, et le
   cerveau **prolonge l'échéance à chaque progression, ne déclare la mort que sur le silence, et
   plafonne le total**. Cela se généralise à tout monde ayant des actions atomiques lentes.
2. LangGraph est devenu le substrat de l'orchestration ReAct, remplaçant la version maison naïve.
3. Le moteur d'échecs est devenu un service. Un service diffère d'un monde en ce qu'un service
   répond aux questions d'ANIMA (un conseiller) tandis qu'un monde reçoit les ordres d'ANIMA (la
   réalité). Les services étaient déclarés par le monde lui-même (`anima://services`) et montés
   automatiquement à la poignée de main.
4. Le mode partie, les arbres de comportement et toute la couche de compétences ont été supprimés :
   les échecs redeviennent une conversation ordinaire (dites « à toi »), et lire l'échiquier,
   calculer et décomposer sont décidés sur le moment par le LLM. Observer–penser–agir est devenue
   l'unique boucle principale.
5. Journaux de session unifiés : appels au LLM, trafic des mondes et appels de services sont fondus
   par session en un seul flux, consultable et copiable par session dans le frontend.
6. Les caméras multiples sont devenues de première classe : une perception peut porter plusieurs
   images nommées, et le frontend affiche les vues en direct côte à côte. gazebo-chess a gagné deux
   caméras et un échiquier lisible (cases et coordonnées sur les bords), et « enlève celle-là /
   pose celle-ci / mets-la là » a été mesuré de bout en bout, du langage à l'action.

## [0.4.0] — 2026-07-02

L'essentiel : une interface d'échecs sous Gazebo, la téléopération et le mouvement cartésien de la
pince.

Nouveautés :

1. L'AWI maison en HTTP a été abandonnée au profit du serveur MCP standard. Les anciens perceive,
   invoke et guidance sont devenus Tools, Resources et Prompts.
2. Le moteur d'échecs a cessé d'être une partie d'une compétence d'échecs pour devenir un serveur
   MCP à part entière.
3. Un nouveau monde, gazebo-chess : une simulation Gazebo bâtie sur le modèle Episode1 — la
   doublure de SOMA Zero — avec une pince et des pièces simulées.
4. Mouvement cartésien implémenté, et préhension téléopérée d'une pièce réussie.

## [0.3.0] — 2026-06-30

L'essentiel : un monde à vraie caméra, laissant ANIMA voir le monde physique réel pour la première
fois. Une version légère, surtout consacrée à tester le flux d'une vraie caméra.

Nouveautés :

1. Un nouveau monde, camera, à résolution réglable.
2. Détails de la compétence d'échecs ajustés.
3. Débogage et interface : la page anima-logs avait un défaut d'attribution de session qui rendait
   la « vue par session » toujours vide ; corrigé, avec en prime la copie en un clic d'une session
   entière, tous champs affichés. Le frontend a gagné un thème clair et un interrupteur, et AWI et
   anima-logs sont devenus des panneaux intégrés à la page d'accueil.

## [0.2.0] — 2026-06-30

L'essentiel : un nouveau programme de plateau simulé, sim-chess, et une compétence d'échecs. Le
cadre d'orchestration de l'agent a été mis au clair.

Nouveautés :

1. Un nouveau monde, sim-chess, capable de simuler le gomoku, les échecs, le go et d'autres
   plateaux. ANIMA ne voit que l'image de sim-chess, jamais son état interne.
2. Un mode échecs dans l'interface d'ANIMA : y entrer démarre un mode en boucle piloté par un arbre
   de comportement, dans lequel ANIMA continue de jouer sans que l'utilisateur ait à parler à
   chaque fois.
3. L'humain dans la boucle et l'évaluation ont été conçus, avec une simple preuve de concept.
4. L'abstraction descendante « Orchestrator → Skill → (Skill) Adapter → Behaviour Tree → Tools » a
   été fixée.
5. Les trois requêtes centrales de l'AWI ont été fixées : perceive, invoke et capabilities.

## [0.1.0] — 2026-06-27

L'essentiel : la première version d'ANIMA Zero. Le cadre a été entièrement réécrit, remplaçant le
prototype antérieur ANIMA O1 et n'en réutilisant aucune ligne.

Nouveautés :

1. L'architecture centrale de séparation entre la cognition et le monde : ANIMA, système cognitif,
   pense et décide ; un monde, entité indépendante, perçoit et exécute ; et les deux se rencontrent
   à travers le protocole standard AWI.
2. La notion de « monde » définie : un monde peut être n'importe quelle entité indépendante — un
   programme, un robot, un environnement — et ANIMA communique avec lui et l'opère via l'AWI.
3. Une première interface de discussion pour ANIMA, avec des sessions, une mémoire gardée en local
   et la possibilité de changer de cerveau en cours de conversation.
4. Le premier monde d'exemple, sim-desk : un bureau virtuel, un stylo et une toile, offrant trois
   capacités — déplacer le stylo, dessiner, effacer — pour valider tout le protocole, l'image étant
   diffusée vers ANIMA.

## [Anima O1] — Avant le 2026-06-27

ANIMA O1 était une conception initiale. Elle a été entièrement démontée pendant le développement
d'ANIMA Zero et rebâtie à partir de rien, si bien que ses détails ne sont pas consignés ici.
ANIMA O1 et les premiers travaux SOMA ont fixé la direction System 1 / System 2, et ont posé les
fondations conceptuelles d'ANIMA Zero et de SOMA Zero.
