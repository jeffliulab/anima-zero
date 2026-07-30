# Sécurité

<a href="../../../SECURITY.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/SECURITY.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/SECURITY.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="SECURITY.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="../es/SECURITY.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

> ANIMA Zero est un **prototype de recherche ouvert**, conçu comme un projet de portfolio et
> d'enseignement. Ce qui suit est un état honnête de ce contre quoi il protège, et de ce
> contre quoi il ne protège pas.

## 1. Ceci est un prototype, pas un système certifié

ANIMA ne détient aucune certification de sécurité. **Ne l'utilisez pas** dans un contexte
médical, industriel, automobile ou dans tout autre cadre critique pour la sécurité. Le faire
exigerait une vérification et une certification que vous devriez mener vous-même.

## 2. ⭐ Connecter un monde est une décision de confiance

C'est la section qui mérite d'être comprise, car elle découle de l'architecture et non d'un
bug particulier.

ANIMA est un **hôte** au sens MCP, et un **monde** est un processus distinct joint par une URL.
L'autorité qu'ANIMA confie à ce monde est inhabituelle :

| Canal | Où finit le texte écrit par le monde |
|---|---|
| **`guidance`** | Concaténé dans le **prompt système** du cerveau — le canal le plus privilégié du modèle |
| **Descriptions des outils** | La liste d'outils du *function calling* du modèle |
| **Résultats des actions** | L'historique de la conversation |
| **`kind` / `readOnlyHint`** | Servait à décider si le portail de sécurité s'exécutait (repris en v1.1, ci-dessous) |

Autrement dit : **connecter le monde de quelqu'un d'autre revient à laisser un inconnu écrire
dans le prompt système de votre cerveau.** Ce n'est pas une inquiétude théorique. Le secteur a
un nom pour ces deux attaques — l'**empoisonnement d'outils** (un texte de description contrôlé
par le serveur entre dans le contexte de l'agent et y est traité comme digne de confiance) et
le **rug pull** (un serveur se tient bien pendant l'examen puis change ses descriptions une
fois approuvé) — avec de véritables incidents et des CVE à la clé.

### Ce que nous faisons

1. **L'approbation porte sur le contenu, pas sur un nom.** À la première connexion d'un monde,
   chaque outil qu'il déclare (nom, kind, description, schéma) et sa `guidance` **intégrale**
   vous sont présentés, et c'est vous qui décidez. Ce qui est enregistré est le SHA-256 de ce
   manifeste. S'il n'a pas changé, on ne vous redemande rien ; **s'il a changé, on vous
   redemande et on vous dit ce qui a changé**. C'est l'idée de SSH qui épingle une clé d'hôte
   ou de Docker qui épingle l'empreinte d'une image : substituer autre chose sous un ancien nom
   doit être détectable.
2. **Le contenu d'un monde non approuvé n'atteint pas le cerveau.** Il apparaît toujours dans
   la liste et indique toujours s'il est en ligne — pour que vous puissiez l'approuver — mais
   sa `guidance` n'entre jamais dans le prompt système et ses outils n'entrent jamais dans la
   liste d'outils.
3. **La `guidance` est encadrée et étiquetée avant injection.** On indique au modèle que ce
   bloc est **de la matière, pas une instruction**, et qu'il ne peut pas outrepasser les règles
   qui le précèdent. Les marqueurs d'encadrement sont retirés du texte du monde lui-même, afin
   qu'il ne puisse pas refermer le cadre par anticipation et faire lire la suite comme les
   propres mots d'ANIMA. Une limite de longueur s'applique également.
4. **Le portail de sécurité a été repris au monde (v1.1).** L'orchestrateur lisait autrefois le
   `kind` déclaré par le monde pour décider s'il fallait consulter le portail — un monde pouvait
   donc le contourner entièrement en annotant un outil destructeur comme étant en lecture seule.
   **Toute action d'un monde passe désormais par le portail**, `kind` n'étant qu'une entrée de
   cette décision et jamais un contournement. Inoffensif tant que le portail reste ouvert en
   simulation ; un trou le jour où il sera fermé pour du matériel réel, ce qui est la seule
   raison d'être de `safety.py`.
5. Chacun de ces points est tenu par un test dans `tests/test_world_trust.py`, face à une
   fixture qui fait ce que ferait réellement un monde malveillant.

### Ce que nous ne faisons **pas** — merci de lire cette partie

- **L'injection de prompt n'est pas résolue.** L'encadrement et les limites de longueur
  relèvent le niveau. Rien n'inspecte la `guidance` à la recherche d'une intention hostile, et
  aucune vérification de ce genre ne serait fiable. C'est un problème ouvert pour tout le
  domaine.
- **Le modèle de confiance décide s'il faut se connecter, pas si ce qu'on vous dit est vrai.**
  Un monde approuvé peut encore envoyer des images de caméra fabriquées ou déclarer réussie une
  action qui a échoué. Ce que voit le cerveau est ce que ce monde a choisi de lui montrer.
- **La vraie protection, c'est donc vous** : lisez le manifeste au moment de l'approuver. Une
  approbation cliquée sans lecture n'est pas une approbation.

### En une ligne

**Ne connectez que des mondes en qui vous avez confiance.**

> `ANIMA_TRUST_ALL=1` saute toutes les approbations, pour le développement — quand vous éditez
> votre propre monde, le manifeste change à chaque enregistrement. Cela reste sur votre machine
> et n'a sa place dans aucune configuration partagée ou publiée.

## 3. Le cerveau se trompe (c'est inhérent aux LLM)

Les décisions d'ANIMA proviennent d'un grand modèle de langage, dans le nuage ou en local, et
**il peut halluciner ou mal juger**. La conception en tient compte : le cerveau ne fait que
*penser* — il choisit des outils et remplit des arguments — et ne détient jamais la vérité
logique. Avant que quoi que ce soit de réel n'arrive, il y a un portail de sécurité et, là où
cela compte, un humain.

## 4. Matériel réel

La version actuelle est purement logicielle : des mondes virtuels et de la simulation physique.
Elle **n'a jamais piloté de matériel réel**. Mais c'est là qu'ANIMA se dirige, donc :

- Un mouvement réel comporte un risque physique. Ces commandes doivent être lancées par
  quelqu'un **présent devant la machine**.
- C'est un bras à servomoteurs : **l'arrêt d'urgence consiste à couper le courant**, et une
  fois le courant coupé les articulations se relâchent et retombent. Quelqu'un doit les tenir.
- Gardez l'angle de la pince à servomoteur **≤ 100°** ; au-delà, le jeu des engrenages le rend
  dangereux.
- Vérifiez avant d'envoyer : l'action est-elle licite, avez-vous réellement bien vu, l'angle de
  préhension est-il sûr ? Les actions à haut risque ou irréversibles exigent une approbation
  humaine explicite.
- ⚠️ Avant tout matériel réel, `src/core/safety.py` doit passer de `default_allow=True` à
  `False`, avec de véritables vérifications déterministes. **Ces vérifications ne doivent jamais
  exempter une action à cause du `kind` déclaré par un monde** — voir §2, point 4.

## 5. Exposition réseau

Par défaut, le backend ne sert que cette machine. Avant de vous lier à `0.0.0.0` ou de définir
`ANIMA_CORS_ORIGINS=*`, sachez précisément ce que cela signifie : n'importe qui sur le réseau
peut créer une session et piloter le monde que vous avez connecté. Le `*` de `.env.example` est
une commodité pour une démonstration locale, pas un réglage de déploiement.

## 6. Clés

Les clés d'API des modèles vivent dans un `.env` local, ignoré par git et jamais committé.
Notez aussi que le contenu des conversations part chez le fournisseur de modèle que vous
choisissez — ne collez dans une session rien qui ne doive pas quitter la machine.

## 7. Signalement

Ouvrez un ticket pour tout ce qui touche à la sécurité, ou écrivez au mainteneur (adresse dans
`pyproject.toml`, sous `authors`).
