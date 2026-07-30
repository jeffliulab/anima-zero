# Contribuer

<a href="../../../CONTRIBUTING.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/CONTRIBUTING.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/CONTRIBUTING.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="../es/CONTRIBUTING.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

> ANIMA Zero est un **prototype de recherche ouvert** — un projet de portfolio et
> d'enseignement, sous licence MIT (voir [LICENSE](../../../LICENSE)). Il avance surtout grâce
> à son mainteneur, mais les tickets, les retours, les petits correctifs et les améliorations
> de documentation sont les bienvenus. Merci de lire d'abord [`README.md`](README.md) pour
> l'architecture, ainsi que le [code de conduite](CODE_OF_CONDUCT.md).

## De quoi il s'agit

ANIMA est le **cerveau** d'un robot incarné : System 2, il pense et ne bouge jamais. Il observe
et opère un **monde** (System 1) qui tourne séparément, à travers une interface appelée **AWI**,
portée par MCP. Le cadre est agnostique quant au domaine — il ne code en dur rien à propos d'un
monde particulier.

## Le lancer en local

```bash
uv tool install anima-zero     # le cerveau seul — un monde est un programme séparé
```

Pour développer, trois processus : un monde, le backend, l'application web — voir le README.
La configuration (clés d'API, adresse d'un Ollama local, la liste des mondes) se trouve dans
[`.env.example`](../../../.env.example). Il n'y a aucun sous-module : un clone ordinaire suffit.

## Ajouter quelque chose

- **Un nouveau monde.** Un monde est un **serveur MCP** standard (monté sur `/mcp`) qui parle
  trois primitives : **Tools** (ce qu'il sait faire), **Resources** (la perception,
  `anima://observation`) et **Prompts** (sa propre `guidance`). Ajoutez son adresse avec
  `anima world add NOM URL` et le cerveau le pilote sans qu'une ligne change. Partez de
  [`world/camera`](../../../world/camera) s'il se contente d'être regardé, de
  [`world/sim-chess`](../../../world/sim-chess) s'il agit, ou de
  [`world/sim-house-nav`](../../../world/sim-house-nav) pour le cas complet, et lisez d'abord
  [`world/README.md`](../../../world/README.md).
- **Un nouveau cerveau (LLM).** Voir [`src/llm/README.md`](../../../src/llm/README.md). La
  plupart des modèles parlent le protocole compatible OpenAI ; enregistrez le vôtre dans le
  tableau de `src/llm/factory.py`.
- **Un outil.** Les outils sont déclarés par le monde dans le `tools/list` de MCP : un nom,
  trois ou quatre phrases disant **quand l'appeler et quand ne pas l'appeler**, un JSON Schema
  et un `kind`. Le cadre les transmet au modèle comme de vrais appels de fonction — n'écrivez
  jamais du JSON à la main dans un prompt.

## Les règles de la maison

La plupart existent parce que quelque chose a mal tourné une fois. Elles sont appliquées par
`python scripts/selfcheck.py`, que la CI exécute à chaque poussée.

- **L'orchestrateur reste agnostique à la tâche.** `src/core/orchestrator.py` ne doit pas savoir
  quel jeu ni quelle tâche il pilote. Le savoir spécifique à une tâche appartient au monde. En
  cas de doute : *ce code aurait-il encore un sens face à un autre monde ?*
- **Un ensemble se complète, il ne se remplace pas.** `ANIMA_WORLDS`, `.env.example`, les listes
  par défaut, les tableaux du README — ajouter une entrée ne doit pas en faire disparaître une.
  C'est une règle stricte parce qu'elle a été enfreinte : ajouter un monde en a un jour retiré
  un autre de l'interface, entièrement.
- **Pas de codage en dur.** Les chemins sont dérivés ou viennent de l'environnement. Les nombres
  réglables vont dans `src/config.py` avec une description, pas en ligne. Tout ce que le modèle
  doit juger — l'intention, l'arrêt, le prochain coup — est jugé par le modèle, jamais par une
  liste de mots-clés.
- **Un bouche-trou se déclare, il ne s'enterre pas.** Si vous devez en laisser un, dites-le dans
  la *pull request*.
- **Les tests et capacités annoncés doivent exister.** Un commentaire affirmant que quelque
  chose est couvert alors que ce n'est pas le cas est le même mensonge que des données truquées.

### Les langues

Le partage se fait par **public**, et c'est délibéré :

| Quoi | Langue |
|---|---|
| Le texte lu par un **modèle** — prompt système, descriptions d'outils, `guidance` d'un monde | **Anglais uniquement.** Voir `src/prompts.py` pour le pourquoi |
| Les textes d'interface lus par une **personne** | Anglais, chinois et japonais, tenus à jour ensemble |
| Les documents lus par une **personne** — README, ce fichier, SECURITY, ROADMAP | Ces trois langues plus le français et l'espagnol, dans `docs/i18n/` |
| Les *docstrings* de l'API publique — `core/awi.py`, chaque `awi_mcp.py`, en-têtes de modules | Anglais et chinois |
| Les commentaires internes expliquant pourquoi une chose est ainsi | **En chinois, et c'est voulu** |

Cette dernière ligne est une vraie décision, pas un oubli. Ces commentaires sont la pensée du
mainteneur, et les traduire aplatirait ce qui fait leur utilité. Ils n'empêchent personne
d'utiliser le projet, et les parties nécessaires pour l'*étendre* — le contrat, la `guidance`,
la documentation — existent en plusieurs langues.

### Les commits

L'anglais d'abord, le chinois ensuite, pour que l'historique se lise en anglais d'un coup d'œil :

```text
type: English summary line

English body — what changed and why.

---
中文说明：这次改了什么、为什么这么改。
```

Expliquez le raisonnement, pas seulement le diff. Un commit qui dit *pourquoi* vaut plus tard
bien plus qu'un commit qui redit *quoi*. Le fichier `.gitmessage` à la racine du dépôt sert de
modèle — un `git config commit.template .gitmessage` une fois par clone et il se remplit tout
seul.

## Liste de contrôle

- [ ] `pytest -q` passe
- [ ] `ruff check .` passe
- [ ] `python scripts/selfcheck.py` passe
- [ ] `python docs/check_readme.py` passe si vous avez touché un README
- [ ] Comportement modifié → **chaque** CHANGELOG (l'anglais à la racine, les autres sous
      `docs/i18n/`), plus le README correspondant
- [ ] **Une garde que vous ajoutez se déclenche vraiment.** Cassez la chose exprès, regardez le
      test passer au rouge, remettez tout en place. Une garde que personne n'a vue échouer est
      une garde dont personne ne sait si elle fonctionne — ce projet en a attrapé quatre qui
      avaient discrètement cessé de garder quoi que ce soit.

## Matériel réel

⚠️ Le code et les commandes qui touchent au matériel réel comportent un risque physique.
**Quiconque les lance doit être présent devant la machine.** Voir [SECURITY.md](SECURITY.md).

## Signalement

Ouvrez un ticket. Pour tout ce qui touche à la sécurité, lisez d'abord
[SECURITY.md](SECURITY.md) — en particulier le §2, sur les raisons pour lesquelles connecter un
monde est une décision de confiance.

Licence : ce projet est publié sous [MIT](../../../LICENSE). Contribuer signifie accepter que
votre contribution soit également offerte sous MIT. MIT autorise déjà l'usage commercial en
source fermée : il n'y a donc aucun accord de contributeur à signer ni double licence à gérer.
Les conditions applicables à chaque version sont consignées dans [NOTICE](../../../NOTICE).
