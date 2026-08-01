# ANIMA Zero

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![PyPI](https://img.shields.io/pypi/v/anima-zero.svg)](https://pypi.org/project/anima-zero/)
[![MCP](https://img.shields.io/badge/protocol-MCP-6f42c1.svg)](https://modelcontextprotocol.io)
[![MuJoCo](https://img.shields.io/badge/sim-MuJoCo-orange.svg)](https://mujoco.org)
[![Version](https://img.shields.io/github/v/tag/jeffliulab/anima-zero?label=version&color=lightgrey)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../../../LICENSE)

<a href="../../../README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/README.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/README.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="../fr/README.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="README.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

> 🤖 **Si eres un agente de IA, lee primero [AGENTS.md](../../../AGENTS.md)** — el punto de entrada
> para máquinas: la regla de capas, dónde vive cada dato y los comandos.

## Visión general

ANIMA Zero es el cerebro de un robot encarnado. Piensa pero nunca se mueve: decide *qué hacer*,
y el cuerpo decide *cómo moverse*.

Dile «ve al salón». No tiene mapa, ni coordenadas, ni una lista de habitaciones: solo la cámara
que lleva el robot en la cabeza. A partir de ahí deduce dónde está, elige una dirección y sigue
caminando hasta ver la habitación que le has pedido. El robot camina con una marcha aprendida, de
modo que las patas pisan de verdad; aquí no se teletransporta nada.

<div align="center">
<img src="../../images/nav-g1.gif" alt="ANIMA conduciendo un humanoide por una casa" width="820">
<br>
<img src="../../images/nav-go2.gif" alt="ANIMA conduciendo un cuadrúpedo por una casa" width="820">
<br>
<sub>Un cerebro, dos cuerpos: arriba un humanoide G1, abajo un cuadrúpedo Go2.
En cada secuencia, la mitad izquierda es la única entrada que recibe ANIMA; la mitad derecha es lo
que ocurre en realidad, y eso no lo ve nunca.</sub>
</div>

### ¿Por qué «Zero»?

Es un nombre de serie, no un número de versión. **Zero significa que esta línea sigue siendo
abierta**: el cerebro es ANIMA Zero, el cuerpo es Open Chess Robot, y cualquier edición comercial futura
llevará otro nombre en lugar de cerrar esta. Todo el proyecto es MIT.

En PyPI es `pip install anima-zero` y el import es `import anima`: el nombre `anima` a secas ya
estaba registrado por otra persona.

## Qué sabe hacer

- **Un cerebro, cuerpos distintos**: el mismo código de cerebro maneja un cuadrúpedo Unitree Go2
  y un humanoide Unitree G1 sin cambiar una línea; lo único que difiere es la altura de los ojos,
  0,38 m frente a 1,25 m.
- **Una interfaz para cualquier mundo**: un mundo es un proceso aparte que habla AWI sobre MCP.
  Cambiar de mundo es cambiar una URL, y un mundo no es de fiar hasta que lo has revisado y
  aprobado.
- **De una frase a los pares articulares**: una instrucción atraviesa cinco capas antes de
  convertirse en movimiento de una pata, y esas capas trabajan con tres órdenes y medio de
  magnitud de diferencia en frecuencia.
- **Recuerda lo que está haciendo**: dos registros de estado viajan dentro del prompt de sistema,
  de modo que un turno de sesenta pasos no olvida ni el objetivo ni lo que ya ha descartado.
- **Auditable e interrumpible**: cada imagen, cada pensamiento y cada llamada a herramienta quedan
  registrados, y un turno en marcha se puede detener en pleno vuelo.

<div align="center">
<img src="../../images/eye-go2.png" alt="La vista del cuadrúpedo" width="400">
<img src="../../images/eye-g1.png" alt="La vista del humanoide" width="400">
<br>
<sub>El mismo salón por los ojos del cuadrúpedo (izquierda) y por los del humanoide (derecha).
Lo que un robot puede ver decide lo que puede concluir, y por eso la escena está construida de
forma realista y no a la medida de una máquina concreta.</sub>
</div>

## Arquitectura

Un mundo es un programa por derecho propio: hoy un simulador, mañana hardware real. ANIMA nunca
mete la mano dentro. Todo lo que el cerebro sabe llega por cuatro canales, y todo lo que hace sale
por esos mismos cuatro. Una persona también puede saltarse el cerebro por completo y trastear con
el mundo desde la interfaz del propio mundo, que es la prueba más clara de que ambos están
realmente separados.

<div align="center">
<img src="../../images/arch-overview.svg" alt="La persona, ANIMA y el mundo, con AWI en medio" width="860">
</div>

Los tres extremos de abajo —verdad de referencia, vídeo y comprobación de vida— nunca viajan por
MCP y nunca llegan al cerebro. Esa separación es deliberada: en el momento en que la verdad de
referencia entra en la percepción, la capacidad que este mundo pretende poner a prueba queda
regalada.

Dentro de una sola instrucción, la estratificación se vuelve concreta. El cerebro razona una vez
por paso; la política de marcha corre a 50 Hz; la física, a 500 Hz. Esa distancia es lo que
significan aquí System 2 y System 1, y es la razón de que el cerebro solo pueda emitir intención,
nunca ángulos articulares.

<div align="center">
<img src="../../images/command-journey.svg" alt="De una frase a los pares articulares" width="860">
</div>

El mundo informa con honestidad, no con complacencia. Una marcha aprendida no sigue exactamente
una orden de velocidad —un giro deriva, un paso se queda corto—, así que el mundo mide lo que
ocurrió de verdad y lo dice, y el cerebro corrige su propio sentido de la posición a partir de eso
y no de lo que pidió.

```text
src/core/      orquestador, contrato AWI, almacén de confianza, compuerta de seguridad
src/clients/   capa cliente de MCP y registro de mundos
src/session/   sesiones, ventana de contexto, log unificado
src/llm/       adaptadores de modelos   src/presentation/  backend HTTP
world/         los mundos, cada uno en su proceso
services/      motor de juegos de mesa   frontend/  app web   eval/  puntuación
```

## Instalación

```bash
uv tool install anima-zero     # o: pipx install anima-zero, o pip a secas
anima demo
```

Eso es todo lo que duran los primeros cinco minutos. La demo arranca un pequeño mundo
integrado —un punto en un pasillo de ocho casillas, el talker/listener de ANIMA— elige un
cerebro y ejecuta un turno de verdad: si tienes clave de API la usa; si no, te guía hacia un
**cerebro local gratuito que corre en CPU** (Qwen3-4B vía Ollama, ~2,5 GB, ofrecido tras
confirmación). Cada fotograma, pensamiento y llamada a herramienta queda en un registro de
sesión que puedes releer después.

Un mundo real es un programa aparte y **ninguno viaja dentro del wheel**, así que el paso
siguiente es conseguir uno: clona este repositorio para los que viven en
[`world/`](../../../world/), o escribe el tuyo siguiendo
[la especificación AWI](../../awi-spec-v1.md) — `src/examples/minimal_world.py`
(el pasillo de la demo) es la plantilla para copiar.

La forma más rápida de orientarte es entregarle el repositorio a un agente de código —Claude
Code, Codex, el que uses— y dejar que lea [AGENTS.md](../../../AGENTS.md), que está escrito
justo para eso. Arrancará un mundo contigo, o te escribirá uno nuevo.

```text
anima demo                    prueba que el circuito funciona: mundo integrado, un cerebro, un turno real
anima chat --world W          una conversación en la terminal
anima run --say "..."         un solo turno, para guiones
anima serve                   la API del backend, para la app web
anima world add NOMBRE URL    registrar un mundo, y revisarlo antes de aprobarlo
anima doctor                  qué está configurado y qué responde
```

¿Atascado? [El FAQ](../../faq.md) cubre los seis tropiezos reales de los usuarios nuevos
(en inglés y chino por ahora).

### La instalación completa

Tres procesos: un mundo, el backend y la app web. Las escenas y los robots vienen de alice-house,
que se busca junto a este repositorio; define `HOUSENAV_ASSETS_ROOT` si está en otro sitio.

```bash
cd world/sim-house-nav && pip install -e . && uvicorn server:app --port 8112
pip install -e . && cp .env.example .env      # añade una clave de API, o apunta a un Ollama local
anima serve
cd frontend && npm install && npm run dev
```

### Conectar un mundo es una decisión de confianza

Un mundo es un proceso remoto, y la descripción que hace de sí mismo aterriza en el prompt de
sistema del cerebro, así que ni sus herramientas ni su `guidance` llegan al cerebro hasta que lo
has mirado y has dicho que sí. `anima world add NOMBRE URL` imprime lo que declara y luego
pregunta. La aprobación se ata al contenido, no al nombre: si el mundo vuelve distinto se te
pregunta otra vez, con una nota sobre qué cambió. Mientras desarrollas tu propio mundo, pon
`ANIMA_TRUST_ALL=1`. [SECURITY.md](SECURITY.md) explica contra qué protege esto y contra qué no.

## Verlo funcionar

Abre la app web, crea una sesión contra `sim-house-nav` y escribe «ve al salón». La columna
central muestra lo que ve el robot y, por separado, una cámara de seguimiento que solo ves tú. La
columna derecha muestra cada paso: imagen, razonamiento, llamada a herramienta y respuesta del
mundo.

<div align="center">
<img src="../../images/ui-chat-en.png" alt="La aplicación web de ANIMA" width="880">
</div>

Para comprobar si una afirmación es cierta y no solo verosímil, pregúntale directamente al mundo:
`curl -s localhost:8112/status`, un extremo para verificación humana que nunca entra en la
percepción. Cambiar las piezas cuesta una línea cada una: el cuerpo tiene un desplegable en el
panel AWI (o pon `HOUSENAV_ROBOT=g1` antes de arrancar el mundo), el cerebro tiene otro en la app
web, y el mundo se elige al crear la sesión.

Estos mundos vienen con el repositorio:

| Mundo | Puerto | Qué es |
|---|---|---|
| [sim-house-nav](../../../world/sim-house-nav) | 8112 | Un piso y un robot que camina, cuadrúpedo o humanoide |
| [sim-chess](../../../world/sim-chess) | 8102 | Un ajedrez que guarda la única verdad y además responde |
| [camera](../../../world/camera) | 8104 | Una webcam de verdad, sin herramienta alguna: mirar sin tocar |

### Qué tal funciona en realidad

Cinco habitaciones objetivo, un intento cada una, con cada imagen final comprobada a mano contra
lo que el modelo afirmaba:

| Objetivo | Pasos | Resultado |
|---|---|---|
| Cocina | 9 | Correcto: nevera, encimera y armarios altos, todo en cuadro |
| Salón | 5 | Correcto: televisión, sofá y lámpara de pie, sin discusión |
| Dormitorio principal | 34 | Incorrecto: leyó un suelo de mármol como un «colchón blanco» |
| Baño | 40 | Incorrecto: aquello era la cocina |
| Lavadero | 60 | Sin terminar: chocó con el tope de pasos por turno |

El resultado interesante es el negativo. La causa que se sospechaba era que una cocina y un baño
se parecen desde 0,38 m, y esa es parte de la razón por la que se añadió el humanoide. Pero el
humanoide, a 1,25 m, ve con claridad la placa y la campana y sigue llamándolo baño. Así que no es
un problema de percepción: frente a la misma puerta, el modelo compone el relato que encaja con la
habitación que está buscando. La próxima versión apunta al criterio de aceptación en su lugar.

Los intentos que sí funcionaron, con verificación imagen a imagen, están recogidos en
[world/sim-house-nav/实测记录.md](../../../world/sim-house-nav/实测记录.md).

## Añadir tu propio mundo

Implementa un servidor MCP estándar con los cuatro canales de arriba, añade su dirección a
`ANIMA_WORLDS` y el cerebro lo manejará sin cambiar. El ejemplo completo más pequeño viene
dentro del paquete: `src/examples/minimal_world.py` —el pasillo de `anima demo`, anotado línea
a línea según la spec, y ejecutable por separado con `python -m anima.examples.minimal_world`.
Copia de [camera](../../../world/camera) si tu mundo solo se mira, de
[sim-chess](../../../world/sim-chess) si actúa, o de
[sim-house-nav](../../../world/sim-house-nav) para el completo, y lee antes
[world/README.md](../../../world/README.md). El contrato está escrito en
[docs/awi-spec-v1.md](../../awi-spec-v1.md), y `anima conformance <url>` comprueba un mundo contra
él.

## Agradecimientos

Las escenas, los modelos de robot y las políticas de locomoción vienen de
[alice-house](https://github.com/jeffliulab/alice-house). La política de giro del humanoide se
entrenó en [unitree-g1-locomotion](https://github.com/jeffliulab/unitree-g1-locomotion). La física
es [MuJoCo](https://mujoco.org); los modelos de robot provienen de
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie).
