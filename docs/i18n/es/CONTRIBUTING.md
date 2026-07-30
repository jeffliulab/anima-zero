# Cómo contribuir

<a href="../../../CONTRIBUTING.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/CONTRIBUTING.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/CONTRIBUTING.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="../fr/CONTRIBUTING.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

> ANIMA Zero es un **prototipo de investigación abierto**: un proyecto de portafolio y de
> enseñanza, con licencia MIT (véase [LICENSE](../../../LICENSE)). Lo empuja sobre todo su
> mantenedor, pero las incidencias, los comentarios, las correcciones pequeñas y las mejoras de
> documentación son bienvenidas. Lee antes [`README.md`](README.md) para la arquitectura y el
> [código de conducta](CODE_OF_CONDUCT.md).

## Qué es esto

ANIMA es el **cerebro** de un robot encarnado: System 2, piensa y nunca se mueve. Observa y opera
un **mundo** (System 1) que corre por separado, a través de una interfaz llamada **AWI**,
transportada sobre MCP. El marco es agnóstico respecto al dominio: no codifica en duro nada sobre
ningún mundo concreto.

## Ejecutarlo en local

```bash
uv tool install anima-zero     # solo el cerebro; un mundo es un programa aparte
```

Para desarrollar, tres procesos: un mundo, el backend y la aplicación web; véase el README. La
configuración (claves de API, la dirección de un Ollama local, la lista de mundos) está en
[`.env.example`](../../../.env.example). No hay submódulos: basta con un clon normal.

## Añadir algo

- **Un mundo nuevo.** Un mundo es un **servidor MCP** estándar (montado en `/mcp`) que habla tres
  primitivas: **Tools** (lo que sabe hacer), **Resources** (la percepción,
  `anima://observation`) y **Prompts** (su propia `guidance`). Añade su dirección con
  `anima world add NOMBRE URL` y el cerebro lo maneja sin que cambie una línea. Empieza por
  [`world/camera`](../../../world/camera) si solo se mira, por
  [`world/sim-chess`](../../../world/sim-chess) si actúa, o por
  [`world/sim-house-nav`](../../../world/sim-house-nav) para el completo, y lee antes
  [`world/README.md`](../../../world/README.md).
- **Un cerebro nuevo (LLM).** Véase [`src/llm/README.md`](../../../src/llm/README.md). La mayoría
  de los modelos hablan el protocolo compatible con OpenAI; registra el tuyo en la tabla de
  `src/llm/factory.py`.
- **Una herramienta.** Las herramientas las declara el mundo en el `tools/list` de MCP: un
  nombre, tres o cuatro frases que digan **cuándo llamarla y cuándo no**, un JSON Schema y un
  `kind`. El marco se las pasa al modelo como llamadas de función nativas; nunca escribas JSON a
  mano dentro de un prompt.

## Reglas de la casa

La mayoría existen porque algo salió mal alguna vez. Las hace cumplir
`python scripts/selfcheck.py`, que la CI ejecuta en cada push.

- **El orquestador sigue siendo agnóstico a la tarea.** `src/core/orchestrator.py` no debe saber
  qué juego ni qué tarea está manejando. El conocimiento específico de una tarea pertenece al
  mundo. Ante la duda: *¿este código seguiría teniendo sentido frente a otro mundo?*
- **Los conjuntos se amplían, no se reemplazan.** `ANIMA_WORLDS`, `.env.example`, las listas por
  defecto, las tablas del README: añadir una entrada no debe hacer desaparecer otra. Es una regla
  estricta porque se ha incumplido: añadir un mundo eliminó una vez otro de la interfaz por
  completo.
- **Nada codificado en duro.** Las rutas se derivan o vienen del entorno. Los números ajustables
  van en `src/config.py` con una descripción, no en línea. Todo lo que deba juzgar el modelo
  —la intención, si parar, qué movimiento hacer— lo juzga el modelo, nunca una lista de palabras
  clave.
- **Un provisional se declara, no se entierra.** Si tienes que dejar uno, dilo en la *pull
  request*.
- **Las pruebas y capacidades que se anuncian tienen que existir.** Un comentario que diga que
  algo está cubierto cuando no lo está es la misma mentira que falsear datos.

### Los idiomas

El reparto es por **público**, y es deliberado:

| Qué | Idioma |
|---|---|
| El texto que lee un **modelo**: prompt de sistema, descripciones de herramientas, `guidance` de un mundo | **Solo inglés.** El porqué está en `src/prompts.py` |
| Los textos de interfaz que lee una **persona** | Inglés, chino y japonés, mantenidos a la par |
| Los documentos que lee una **persona**: README, este archivo, SECURITY, ROADMAP | Esos tres idiomas más francés y español, en `docs/i18n/` |
| Los *docstrings* de la API pública: `core/awi.py`, cada `awi_mcp.py`, las cabeceras de módulo | Inglés y chino |
| Los comentarios internos que explican por qué algo es como es | **En chino, y es a propósito** |

Esa última fila es una decisión real, no un olvido. Esos comentarios son el pensamiento del
mantenedor, y traducirlos aplanaría lo que los hace útiles. No impiden a nadie usar el proyecto,
y las partes que hacen falta para *extenderlo* —el contrato, la `guidance`, la documentación—
están en varios idiomas.

### Los commits

Primero el inglés, luego el chino, para que el historial se lea en inglés de un vistazo:

```text
type: English summary line

English body — what changed and why.

---
中文说明：这次改了什么、为什么这么改。
```

Explica el razonamiento, no solo el diff. Un commit que dice *por qué* vale más con el tiempo que
uno que repite *qué*. El archivo `.gitmessage` en la raíz del repositorio guarda esto como
plantilla: un `git config commit.template .gitmessage` una vez por clon y se rellena solo.

## Lista de comprobación

- [ ] `pytest -q` pasa
- [ ] `ruff check .` pasa
- [ ] `python scripts/selfcheck.py` pasa
- [ ] `python docs/check_readme.py` pasa si has tocado algún README
- [ ] Si cambió el comportamiento → **todos** los CHANGELOG (el inglés en la raíz, los demás bajo
      `docs/i18n/`), más el README correspondiente
- [ ] **La guarda que añadas se dispara de verdad.** Rompe la cosa a propósito, mira cómo la
      prueba se pone en rojo y deshaz el estropicio. Una guarda que nadie ha visto fallar es una
      guarda de la que nadie sabe si funciona: este proyecto ha cazado cuatro que habían dejado
      de guardar en silencio.

## Hardware real

⚠️ El código y las órdenes que tocan hardware real conllevan riesgo físico. **Quien los ejecute
tiene que estar presente junto a la máquina.** Véase [SECURITY.md](SECURITY.md).

## Contacto

Abre una incidencia. Para cualquier cosa relacionada con la seguridad, lee antes
[SECURITY.md](SECURITY.md), en especial el §2, sobre por qué conectar un mundo es una decisión de
confianza.

Licencia: este proyecto se publica bajo [MIT](../../../LICENSE). Contribuir implica aceptar que
tu contribución se ofrece también bajo MIT. MIT ya permite el uso comercial con código cerrado,
así que no hay ningún acuerdo de contribuyente que firmar ni doble licencia que gestionar. Qué
condiciones se aplican a cada versión está registrado en [NOTICE](../../../NOTICE).
