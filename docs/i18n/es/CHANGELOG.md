# Registro de cambios de Anima Zero

<a href="../../../CHANGELOG.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/CHANGELOG.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/CHANGELOG.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="../fr/CHANGELOG.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="CHANGELOG.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

Notas de versión de ANIMA Zero. **Mantenerlas cortas: por versión, solo lo que cambió de
verdad.** (Formato inspirado en [Keep a Changelog](https://keepachangelog.com).)

## [1.2.0] — 2026-07-31

Lo esencial: los primeros cinco minutos están de vuelta — `anima demo` demuestra que todo
el circuito funciona en cualquier máquina, con o sin clave de API — y el repositorio está
listo para recibir visitas: un FAQ, una puerta de entrada para colaboradores, cero alertas
CVE, y los dos fallos de empaquetado que enviaban silenciosamente lo incorrecto están
corregidos y vigilados en CI.

1. **`anima demo` regresa, sin nada de lo que costaba el anterior.** Un mundo-pasillo de
   ~300 líneas (un punto, `look`, `step`, un fotograma de cámara real) se distribuye dentro
   del paquete, escrito a mano según la especificación AWI — sin copias byte a byte, sin
   submódulos, sin un desk duplicado en cada lista de mundos: las tres cosas que mataron
   al mundo desk de v1.1. La demo lo arranca en un puerto libre y elige un cerebro en voz
   alta: tu clave de API si la tienes; si no, un **cerebro local en CPU** (Qwen3-4B-Instruct-2507
   vía Ollama, ~2,5 GB, ofrecido como un pull de una línea — el tamaño más pequeño con
   llamadas a herramientas realmente fiables); si no, el mock honesto. El pasillo sirve
   además como plantilla para escribir tu propio mundo
   (`src/examples/minimal_world.py`, ejecutable por separado con
   `python -m anima.examples.minimal_world`). Entre bastidores, el bucle ahora respeta
   `llm.vision`: un cerebro que no puede ver ya no recibe imágenes.
2. **El camino del usuario nuevo está despejado.** gazebo-chess sale de la lista de mundos
   por defecto (su código vive ahora en el repositorio compañero; define `GAZEBO_CHESS_URL`
   y vuelve, nada se pierde); el sello `.build-time` por fin entra en el wheel, así que
   `anima serve` informa a los usuarios de pip la hora real de construcción de la UI, y CI
   demuestra en cada push que el wheel lleva la UI fresca y su sello; el nuevo
   `docs/faq.md` (inglés y chino) cubre los seis tropiezos reales de los usuarios nuevos;
   y `/awi` y `/session-logs` ya no dan 404 al abrirlos directamente — además ganaron su
   propio selector de idioma (ROADMAP R9, cerrado).
3. **Cero alertas CVE** (ROADMAP R4, cerrado): Next 15 → 16, con `postcss`/`sharp` fijados
   por encima de los avisos mediante `overrides`. `npm audit` está limpio; la interfaz fue
   revisada a simple vista tras el salto de versión mayor.
4. **Una puerta de entrada para colaboradores**: CONTRIBUTING gana una sección «Where to
   start» (escribir un mundo desde la plantilla del pasillo / revisar una traducción /
   good first issues), además de `CITATION.cff` y una insignia de PyPI.

## [1.1.1] — 2026-07-30

Main: el mundo desk y `anima demo` ya no están. El mundo que viajaba dentro del wheel existía para que `pip install` llevara a alguna parte; costaba dos copias idénticas byte a byte, un submódulo de git y un segundo desk en cada lista de mundos, y eso era más de lo que valía.

1. **Eliminados los dos mundos desk, y `anima demo` con ellos**: el integrado que viajaba en el wheel y el submódulo `sim-desk` que lo acompañaba. ⚠️ **`pip install anima-zero` ahora te da el cerebro y ningún mundo.** Un mundo es un programa aparte: clona este repositorio para los de `world/`, o escribe el tuyo siguiendo la especificación AWI. El cerebro simulado no cambia y se sigue pudiendo elegir.
2. **El README te entrega a un agente de código**: donde la instalación lucía una demo de un solo comando, ahora dice que el paso siguiente es conseguir un mundo, y que la vía más rápida es darle el repositorio a Claude Code o Codex y dejar que lea `AGENTS.md`.
3. **La conformidad ya no prueba el mundo que casualmente distribuimos**: la comprobación de extremo a extremo arranca ahora un **mundo mínimo escrito desde la especificación dentro de la propia prueba** —ocho casillas, una herramienta, un PNG real— y descodifica esa imagen en lugar de fiarse del tipo mime declarado. ⛔ Falla en vez de saltarse cuando el objetivo no arranca.
4. **El repositorio ya no tiene submódulos**, `awi_mcp.py` baja de seis copias idénticas byte a byte a cuatro, y solo la de soma-zero queda fuera de este repositorio.

## [1.1.0] — 2026-07-27

Lo principal: pasar de un repositorio de portafolio a un proyecto que otras personas pueden
instalar, conectar y para el que pueden escribir mundos: todo el repositorio relicenciado a
**MIT** (escribiendo nosotros mismos la salida de la última dependencia no permisiva),
`pip install anima-zero` seguido de un comando `anima` de verdad y una aplicación web, **un mundo
tratado como una parte remota no fiable**, y AWI convertida en una especificación escrita con su
verificador.

Novedades:

1. **Relicenciado a MIT; la oferta de doble licencia comercial se retira.** Lo que lo impedía era
   python-chess, bajo GPL, así que **escribimos nuestra propia biblioteca de reglas**
   (`packages/anima-chess`: bitboards y hash Zobrist, MIT). El perft coincide con los valores
   publicados en las seis posiciones estándar, y una búsqueda de profundidad 3 en el medio juego
   tarda 1,27 s frente al tope consultivo de 1,5 s. ⚠️ Es **entre dos y cuatro veces más lenta**
   que python-chess: suficiente para ese único propósito y no para nada más profundo; la causa y
   el arreglo están registrados como R5 de la hoja de ruta. La batería de pruebas pasa con
   python-chess desinstalado. Las 69 dependencias auditadas: ninguna no permisiva.
2. **Se instala y funciona**: `pip install anima-zero` te da el comando `anima`
   (`demo` / `chat` / `run` / `serve` / `doctor` / `world` / `conformance`). La aplicación web se
   exporta como estática y **viaja dentro del wheel**, de modo que `anima serve` te entrega una
   interfaz en una máquina sin node. Vienen incluidos un **mundo de escritorio integrado** y un
   **cerebro simulado que no necesita clave**, así que `anima demo` enseña el bucle entero en un
   comando: imagen, decisión, llamada a herramienta, resultado. ⚠️ Publicar está ahora acoplado a
   compilar la interfaz (`build_ui.py` antes de `python -m build`), y `anima serve` imprime la
   marca de tiempo de compilación de la app web, porque **distribuir un paquete con una interfaz
   caducada es justo lo que nadie llegaría a notar.**

   > ⚠️ **Sustituido en v1.1.1**: el mundo desk integrado y `anima demo` se eliminaron. El
   > comando `anima`, la app web incluida en el wheel y el cerebro simulado no cambian.
3. **⭐ Un mundo se trata como una parte remota no fiable.** La `guidance` de un mundo se une al
   **prompt de sistema** del cerebro y sus descripciones de herramientas se convierten en la
   **lista de herramientas**: todo ello texto que escribió otra persona. Por eso: el contenido de
   un mundo **no llega al cerebro hasta que lo has leído y aprobado** (sigue apareciendo en la
   lista y sigue indicando si está en línea); la aprobación **se ata al hash de un manifiesto**
   (SHA-256 sobre la URL, el nombre, el kind, la descripción y el esquema de cada herramienta, y
   la `guidance` completa), y **un manifiesto cambiado te vuelve a preguntar y te dice qué
   cambió**, que es lo que derrota a un rug pull; la `guidance` se **acota** antes de entrar en el
   prompt de sistema y se etiqueta como material y no como instrucción, con los marcadores de
   acotación eliminados del texto del propio mundo y con límites de longitud. ⛔ La **compuerta de
   seguridad también se le retiró al mundo**: el orquestador solo la consultaba para las
   herramientas que el mundo no hubiera marcado como de solo lectura, así que un mundo podía
   **saltarse la compuerta por completo** anotando una herramienta destructiva con
   `readOnlyHint: true`. Ahora toda acción pasa por la compuerta, con `kind` como una entrada más
   de la decisión. Inofensivo mientras la compuerta seguía abierta en simulación, y un agujero el
   día en que se cierre para hardware real. `ANIMA_TRUST_ALL=1` es una salida de emergencia para
   desarrollo. Todo el modelo de amenaza está fijado por una fixture de mundo malicioso
   (`tests/test_world_trust.py`). ⚠️ **La inyección de prompts está mitigada, no resuelta**:
   véase R3 de la hoja de ruta.
4. **AWI se convirtió en una especificación**: `docs/awi-spec-v1.md` (inglés y chino) enuncia cada
   canal, qué es obligatorio frente a qué es recomendable, y qué hace el anfitrión con lo que un
   mundo envía, incluida una sección sobre que **`kind` es una declaración y no una garantía**.
   Con ella viene `anima conformance <url>`, que se conecta a un mundo, ejercita cada canal e
   informa de cada comprobación citando la sección de la que procede, incluida la comprobación del
   **orden de las cámaras**, que se gana su sitio porque los blobs de imagen no llevan nombre, su
   orden es lo único que ata una imagen a una cámara, y un desajuste es silencioso en cualquier
   otro sitio. ⛔ **Enuncia sus propios límites cada vez**: si el estado filtra una vista divina,
   si el `kind` se corresponde con el comportamiento, si la `guidance` es honesta. Ninguna
   comprobación automática zanja eso. Lo zanja una persona, al aprobar.
5. **El idioma, repartido por público**: todo lo que lee un modelo —prompt de sistema,
   descripciones de herramientas, bloques de estado, la `guidance` de cada mundo— es ahora
   **inglés en una sola versión**, recogido en `src/prompts.py` y terminado con una línea que le
   pide responder en el idioma del usuario. Los documentos que lee la gente vienen en varios
   idiomas. La CLI y la app web están en inglés por defecto. ⚠️ **Eso es un cambio de
   comportamiento y la prueba comparativa que lo zanjaría no se ha vuelto a ejecutar**: la
   comparación de navegación por cinco habitaciones, antes y después, es una deuda reconocida y
   registrada como R2. Hasta que exista, «aquí el inglés es mejor» es una hipótesis. Si resulta
   peor, el punto de vuelta atrás es un archivo. ⚠️ La primera pasada se dejó muchísimo: los
   bloques de mundo del orquestador, el encuadre de imagen que acompaña a cada fotograma, los
   motivos de la compuerta de seguridad, los avisos de truncado, todos los errores de backend que
   muestra la app web y las respuestas del propio cerebro simulado seguían en chino cuando esta
   afirmación ya estaba escrita. Se encontraron instalando el wheel y ejecutándolo, no leyendo el
   código. Lo que queda, y por qué, es R6.
6. **Guardas mecánicas y deudas registradas**: `scripts/selfcheck.py` convierte en guardas de CI
   cuatro reglas de la casa que solo vivían en un cuaderno local (el orquestador se mantiene libre
   de lógica específica de tarea / nada de configuración muerta / ningún provisional sin declarar
   / la versión concuerda en tres sitios), y **todas se probaron por la negativa**: la guarda de
   configuración muerta estaba rota en su primera versión y habría seguido en verde para siempre
   sin probarla. Nuevo `ROADMAP.md` (en ambos idiomas): **no una lista de deseos, sino el espejo
   de los fracasos medidos y las deudas asumidas**, cada una numerada: R1 el sesgo de
   confirmación, R2 el cambio de idioma sin medir, R3 la inyección sin resolver, R4 cuatro CVE de
   severidad alta en el árbol npm del frontend, R5 la velocidad de la biblioteca de ajedrez.

**Límites medidos, registrados con honestidad**: la navegación entre habitaciones está
**igual** que en la v1.0: cinco objetivos, dos aciertos, dos fallos, uno sin terminar. Nada de
esta versión apuntaba a eso. Esta versión trataba de si otra persona puede usar el proyecto, no de
lo listo que es. R1 es lo que apunta al resto.

## [1.0.1] — 2026-07-26

Lo principal: arregla dos fallos del panel de la v1.0: no tenía límite de altura y expulsaba de la
barra lateral la lista de sesiones por completo, y estaba en el sitio equivocado.

1. **Altura limitada y plegable**: el número de notas no está acotado (capacidad por defecto: 20),
   y sin un tope doce notas aplastaban de forma medible la lista de sesiones.
2. **Movido encima de la conversación**: es el estado de la **sesión actual**, pero estaba al
   fondo de la barra lateral entre los elementos **globales** (parámetros de ejecución, panel AWI,
   apariencia): parecía global y estaba a media pantalla de la sesión a la que pertenecía.
   Fijarlo encima de la conversación significa además que **no se va con el scroll**, así que
   durante un turno largo siempre puedes ver qué está haciendo; plegado ocupa una línea y hace las
   veces de barra de estado (con una tarea central, simplemente muestra «trabajando en…»).
3. **Se abandona «memoria de trabajo» como término paraguas**: la expresión no aparece en ninguna
   parte del código y hacía pensar que la tarea central y el cuaderno eran una sola cosa. Ahora se
   muestran como lo que son: la **tarea central** (qué estoy haciendo, una frase, se actualiza
   reescribiéndola) y el **cuaderno** (qué he encontrado, entrada a entrada, se actualiza añadiendo
   y quitando).

## [1.0.0] — 2026-07-26

Lo principal: el robot puede **cambiar de cuerpo, recordar su camino y no chocar con los muebles**:
el mundo pasó de «un perro» a «un cuerpo intercambiable» (se añadió un humanoide Unitree G1, con
una política de giro entrenada específicamente para él), el cerebro ganó una memoria de trabajo
genérica y AWI ganó un canal formal. Al mismo tiempo **se borró sin más la lista de respuestas que
se le daba al cerebro**: lo que este mundo pone a prueba es averiguar mirando en qué habitación
estás, y una puntuación obtenida entregando las respuestas no significa nada.

Novedades:

1. **Un mundo, dos cuerpos**: `sim-house-nav` ya no codifica en duro nada para el cuadrúpedo. El
   modelo, la política, la cámara, la altura de aparición y la forma de enviar el par vienen todos
   del manifiesto de robots de la biblioteca de recursos (⛔ los dos son **opuestos**: PD
   explícito para el cuadrúpedo, PD implícito para el humanoide; si los inviertes, se cae al
   instante). El humanoide tiene 29 grados de libertad y los ojos a 1,25 m, y ve una habitación
   completamente distinta desde el mismo sitio. Se **entrenó una política de giro específicamente
   para él** (rango de la orden de guiñada ampliado de ±0,2 a ±0,8, 10 000 iteraciones): ⚠️ sigue
   **sin poder girar sobre el sitio** (parado, la política toma la opción más barata), así que
   girar arrastra 0,3 m/s de avance y un giro de 90° lo desplaza entre 0,6 y 0,8 m. El mundo
   **informa de ese desplazamiento con honestidad**.
2. **Un canal AWI nuevo para la configuración del mundo**: un mundo **declara** con qué se puede
   configurar (el nuevo recurso MCP `anima://config`), y una persona lo cambia por **HTTP fuera de
   banda**: cambiar la configuración es una acción humana, y al cerebro solo se le dice qué cuerpo
   tiene ahora, igual que un robot real sabe qué cuerpo es. ⛔ El prompt dice sin rodeos que no
   puede cambiar esto: el cerebro no tiene ninguna herramienta para ello, e insinuar lo contrario
   solo hace que estire la mano hacia algo que no existe. Esto arregló además la trampa de la v0.9
   por la que las capacidades se cachean en el primer apretón de manos, de modo que un mundo que
   ganaba una herramienta sin reiniciar el backend no conseguía nunca meterla en la lista de
   herramientas: la app web tiene ahora un botón para rehacer el apretón de manos.
3. **Un registro cuaderno, y la hoja de respuestas retirada**: la tarea central guarda «qué estoy
   haciendo» (una frase) y el nuevo cuaderno guarda «qué he encontrado» (entradas que se añaden y
   se quitan). Ambos se inyectan de forma permanente y no se salen del contexto según crece la
   conversación. Los tres rechazos —vacío, demasiado largo, lleno— dicen por qué, y **nunca truncan
   ni descartan en silencio**. Al mismo tiempo, la `guidance` del mundo perdió su inventario de
   muebles y su tabla de puntos de referencia para doce habitaciones (1180 → 844 caracteres).
   ⚠️ **Medido: quitar las respuestas no cambió nada** (dos de cinco objetivos, como antes), así
   que aquella lista nunca había servido para nada. Y el cuaderno dejó ver por primera vez la causa
   real: describe lo que hay detrás de una puerta como la habitación que está buscando en ese
   momento. Sesgo de confirmación.
4. **Telemetría láser, frenada y cámara de seguimiento**: una telemetría en ocho direcciones entra
   en la percepción (un Go2 real lleva un lidar L1 en la cabeza) y, al avanzar, frena y se queda
   de pie cuando se acerca demasiado, informando con honestidad de cuánto sitio queda. ⛔ Se para,
   no dirige; adónde ir después es siempre decisión del cerebro. La vista de seguimiento en tercera
   persona es **solo para personas**: `/streams` marca cada vista con `awi`, la página web divide
   el panel de sensores en consecuencia, y archivar la vista de seguimiento bajo «lo que ve ANIMA»
   sería mentira. Hay pruebas que sujetan esa línea.
5. **El contrato del mundo se convirtió en una plantilla** (`world/README.md`): las dos líneas,
   AWI y fuera de banda, y una pregunta para distinguirlas: ¿esto es para el cerebro o para una
   persona? Más seis guardas mecánicas que comprueban la integridad del registro (¿está el mundo en
   `.env.example`?, ¿está en la lista antideriva?, ¿marcan `awi` los mundos con varias vistas?, …).

**Límites medidos, registrados con honestidad**: la navegación de corto alcance es sólida
(cuadrúpedo: «ve a la cocina» en 10 pasos / 41 s, «ve al salón» en 9 pasos / 32 s; el humanoide
también consiguió las dos). Pero **la navegación entre habitaciones sigue sin ser fiable**: de
cinco objetivos, dos aciertos, dos fallos y uno sin terminar, lo mismo con ambos cuerpos. ⭐ Esta
versión **refutó la hipótesis de la v0.9 sobre la causa**: se sospechaba que una cocina y un baño
se parecen desde un punto de vista bajo, pero el humanoide a 1,25 m ve con claridad la placa y la
campana y **sigue llamándolo baño**. Así que no es que no pueda ver. Es sesgo de confirmación:
frente a la misma puerta, compone el relato que encaja con la habitación que busca. La próxima
versión apunta al criterio de aceptación (describir primero y clasificar después; apretar lo que
puede significar «lo estoy viendo, luego he llegado»), no a la percepción. Los intentos que sí
funcionaron están en `world/sim-house-nav/实测记录.md`.

## [0.9.0] — 2026-07-25

Lo principal: un mundo nuevo, **sim-house-nav**: un cuadrúpedo Unitree Go2 dentro de una casa,
donde ANIMA solo ve la cámara frontal de su cabeza y tiene que deducir por los muebles dónde está
y llevarlo hasta allí. Con él, «un turno» se amplió de **un movimiento y parar** a **una cosa,
terminada**, y los turnos largos recibieron un freno.

Novedades:

1. **El nuevo mundo sim-house-nav (:8112)**: una marcha de cuadrúpedo de verdad en MuJoCo. Tres
   primitivas de navegación (adelante, izquierda, derecha) se traducen a órdenes de velocidad
   `(vx, vy, wz)` que se le pasan a una política entrenada, así que el perro pisa de verdad en vez
   de teletransportarse. Las primitivas se ejecutan **en lazo cerrado** (una marcha aprendida sigue
   una orden de velocidad solo al 83 % y al 62 %, así que mide sobre la marcha y para cuando ha
   llegado) e informan con honestidad cuando una pared se lo impide. La observación lleva **la
   imagen, el rumbo de la IMU y si se ha caído**: ⛔ ni coordenadas ni nombres de habitación; las
   habitaciones hay que reconocerlas mirando. Las escenas y los modelos de robot se sacaron a una
   biblioteca de recursos aparte, montada por configuración.
2. **Un turno es una cosa** (una revisión del punto 1 de la 0.8, no una derogación de la
   disciplina): cuándo termina un turno lo **decide ANIMA al producir prosa**. El límite de pasos
   pasó de 8 a 60 y se añadió un límite de 900 segundos de reloj, ambos degradados a **cinturones
   de seguridad y no metrónomos**. En ajedrez, «una cosa» sigue siendo un movimiento (2–6 pasos,
   que termina de forma natural, comportamiento sin cambios); en navegación es encontrar la
   habitación objetivo (decenas de pasos, hasta converger). ⛔ El «jugar una partida entera desde
   una frase» rechazado en la v0.7 sigue rechazado: aquello eran **varias cosas** apretujadas en un
   turno, lo cual no tiene nada que ver con el límite de pasos.
3. **Un freno y una ventana para los turnos largos**: interrupción a nivel de sesión
   (`POST /api/sessions/{sid}/interrupt`), con el botón Enviar de la app web convirtiéndose en
   Parar mientras genera. La interrupción alcanza incluso a la espera de una acción, así que
   pulsarla no significa esperar a que el perro termine el paso. Llegar a un límite es una pausa
   educada (la tarea central se queda en el registro y «continúa» la reanuda), y cada uno de los
   tres motivos dice lo suyo. El panel de razonamiento ganó una altura máxima con scroll, números
   de paso y plegado/desplegado, y los parámetros de ejecución principales viven de forma
   permanente abajo a la izquierda, leídos del backend en vez de escritos en el frontend.
4. **Hacer que recuerde qué está haciendo**: el prompt de sistema y la `guidance` del mundo ganaron
   «termina una cosa de una vez», «para una tarea de varios pasos, registra antes la tarea central»
   y «ve escribiendo el avance de vuelta en el registro»: en un turno largo, las imágenes vistas al
   principio se salen del contexto, y ese registro es lo único que no.

**Límites medidos, registrados con honestidad**: la navegación de corto alcance funciona: «ve a la
cocina», encontrada e identificada en 7 pasos / 45 s. Pero **la navegación entre habitaciones aún
no es fiable**: cuatro habitaciones objetivo, un intento cada una, un acierto y tres fallos (dos
habitaciones mal identificadas, una parada a medio camino), y da vueltas en distancias largas.
Desde un punto de vista bajo, la cocina y el baño son difíciles de distinguir (ambos son «encimera,
puertas de armario, panel blanco»). La cuarta primitiva `look_around` se implementó pero **nunca se
ha medido**: el cerebro cachea las capacidades en el primer apretón de manos, y durante los
experimentos nunca llegó a la lista de herramientas.

## [0.8.0] — 2026-07-25

1. El número máximo de pasos por turno queda fijado en 8 por defecto. Por ahora el sistema es
   estrictamente por turnos; los bucles largos quedan fuera de alcance.
2. La configuración central pasó a pydantic-settings: validación de tipos que falla pronto, cada
   parámetro con una descripción y una cota inferior. Los nombres de las variables de entorno y la
   interfaz consumidora `config.*` no cambian, y `.env` afecta ahora a **todos** los parámetros
   (antes solo llegaba a las listas de mundos y de servicios).

## [0.7.0] — 2026-07-06

Lo principal: el mundo gazebo-chess ganó la capacidad de **jugar una partida entera**: a partir de
una frase, ANIMA juega solo una partida completa (decenas de movimientos de coger y dejar físicos,
con capturas, enroque y coronación pasando todos por primitivas de verdad), mientras el mundo
sostiene un árbitro y un oponente informático que se teletransporta, y la partida final se archiva
para su puntuación. **No cambió ni una línea del cerebro** —solo subió `ANIMA_MAX_STEPS`—, lo cual
es en sí mismo la prueba de campo de la afirmación de que cambiar de mundo cuesta una URL.

Novedades:

1. **Una partida entera**: el mundo gazebo-chess sostiene un **árbitro** (una compuerta de
   legalidad antes de que el brazo se mueva, una verdad que solo avanza cuando cada primitiva se ha
   verificado físicamente, detección de fin de partida y una partida archivada) y un **oponente
   informático que se teletransporta** (responde en cuanto el cerebro termina un movimiento, sin
   anunciar qué ha jugado, así que el cerebro tiene que verlo; es una tercera copia independiente
   del motor, que no debe fusionarse con las otras dos), además de las piezas capturadas yendo a
   una caja y la **recuperación desde una pieza de repuesto** (cuando una pieza abandona el tablero
   de forma permanente, colocar una idéntica en su casilla vuelve a alinear la posición con la
   partida) y un botón de «partida nueva». Cero cambios en el cerebro; dos partidas completas
   medidas (38 y 44 movimientos). Las partidas finales alimentan al puntuador, que informa de la
   tasa de éxito de las primitivas y de la latencia por mundo: los fallos físicos y los movimientos
   ilegales nunca se mezclan. El antiguo modo de una sola pieza de demostración, sin FEN, se
   comporta exactamente igual que antes.
2. **Todas las casillas alcanzables, y piezas de verdad**: el agarre pasó a una **inclinación
   radial** más una geometría medida directamente (10 cm desde el eje, casillas de 4,5 cm; ambos
   valores por defecto medidos y ambos sobreescribibles por entorno) → **las 64 casillas
   alcanzables**, arreglando el «toda la columna h es inalcanzable» de la v0.5
   (`scripts/reach_map.py` lo reproduce en un comando). La **diversidad en los reintentos**
   convierte una casilla maldita de forma determinista en una que acierta al primer cambio de
   postura. Las piezas pasaron a ser **mallas Staunton de verdad** (CC-BY 4.0, fuente y licencia en
   el repositorio; los cuerpos de colisión no cambian).
3. **Un registro de tarea central por sesión** (el único cambio en el cerebro, y un mecanismo
   genérico): una tirada de resistencia midió el fallo: la tarea se sale de la ventana de contexto
   y el cerebro se detiene a medio camino. «En qué tarea estoy» es **estado**, no historial de
   conversación. El LLM lo registra, lo reescribe y lo borra **él mismo** mediante las
   metaherramientas integradas `set_core_task` y `clear_core_task` (sin palabras clave, sin fijar
   nada, sin heurísticas), y se inyecta de forma permanente en el prompt de sistema como canal de
   estado en lugar de ocupar la ventana de historial. El comportamiento por turnos no cambia: se
   detiene después de cada movimiento y espera.
4. **Cambio de licencia**: todo el repositorio pasó de Apache-2.0 a **AGPL-3.0 más doble licencia
   comercial.** Lo importante de la AGPL-3.0 es que **prestar un servicio a través de la red**
   también obliga a abrir el código correspondiente. Las integraciones comerciales de código
   cerrado que no quisieran asumirlo podían escribir al mantenedor para una licencia comercial.
   Compatible con python-chess bajo GPL-3; las versiones hasta la v0.6.0 siguen disponibles bajo la
   Apache-2.0 original.
   > ⚠️ **Sustituido por la v1.1**: todo el repositorio es **MIT** desde la v1.1, y la doble
   > licencia comercial se retira con ella (MIT ya permite el uso comercial con código cerrado). Lo
   > que lo hizo posible fue sustituir python-chess por nuestra propia biblioteca de reglas bajo
   > MIT. Las versiones v0.7.0 a v1.0.1 siguen bajo las condiciones AGPL-3.0 con las que salieron.
   > El historial completo de licencias está en [NOTICE](../../../NOTICE).

## [0.6.0] — 2026-07-03

Lo principal: los motores se trajeron al repositorio y el mundo y los servicios quedaron del todo
desacoplados, con el montaje de servicios volviendo al «ensamblado por el anfitrión» del MCP
estándar: limpiar las fronteras antes de apuntar al hardware real. En corto: el anfitrión y los
servicios son ahora independientes entre sí. El servidor de motor habla con el anfitrión ANIMA, el
servidor de mundo habla con el anfitrión ANIMA, y el servidor de mundo y el de motor ya no hablan
en absoluto.

Novedades:

1. Los tres núcleos de motor de juegos de mesa (ajedrez, gomoku, go) se movieron a
   `services/boardgame_engine/`: antes leían archivos de otro repositorio a través de importlib, de
   modo que un clon nuevo no arrancaba. El servicio se renombró a boardgame-engine, las tres
   herramientas de ajedrez están activas, y go y gomoku están colocados a la espera de un
   consumidor. La carpeta externa `3-anima-chess-engine` se borró; el repositorio se sostiene solo.
2. El asesor de motor del cerebro y el oponente informático integrado en el mundo sim-chess se
   separaron en dos copias deliberadamente independientes (`chess_engine.py` y `chess_bot.py`, sin
   compartir código y sin fusionarse): con el servicio de motor apagado, el ordenador del mundo
   sigue jugando, y el asesor viaja con el cerebro de un cuerpo a otro.
3. El «un mundo declara sus servicios» de la v0.5 (`anima://services`) quedó abolido en favor de
   que el cerebro los monte él mismo mediante `config.services()`, en simetría con `worlds()`, en
   línea con el principio MCP de que a qué servidores conectarse es asunto del anfitrión y los
   servidores no se conocen entre sí. El emparejamiento lo hace el modelo mirando la imagen y
   eligiendo una herramienta, no una ligadura estructural.
4. Nombres unificados para las tres capas de MCP y el modelo de la «línea dedicada»: hay exactamente
   dos clases de servidor, el **World Server** (la realidad, las tres primitivas) y el **Engine
   Server** (un asesor, solo herramientas). El anfitrión (el cerebro ANIMA) abre una línea dedicada
   a cada uno, que es la capa cliente (`RemoteWorld` / `RemoteService` en el código, una línea para
   un servidor). Una línea recuerda la dirección, cachea las capacidades en el apretón de manos,
   traduce el protocolo, gestiona los tiempos de espera según el papel (supervisión de vida para un
   mundo, un tiempo de pregunta corto para un motor) y lleva las cuentas. Las líneas no hablan entre
   sí, y así es como se materializa el aislamiento entre servidores. El §4 del README y la página
   `/awi` se actualizaron en consecuencia.

## [0.5.0] — 2026-07-03

Lo principal: una refactorización grande. Se borró la orquestación diseñada por humanos, como el
modo partida, minimizando el marco para poder examinar la inteligencia: el LLM mira la imagen él
mismo, decide cada paso él mismo y llama a las herramientas él mismo.

Novedades:

1. **Semántica de señales de vida para las acciones largas** (una corrección del marco): una acción
   física tarda decenas de segundos, el tiempo de espera fijo de la v0.4 la mataba, y los mundos
   ejecutaban el trabajo en el bucle de eventos, así que un solo movimiento congelaba el servidor de
   mundo entero. Se adoptaron en su lugar las **notificaciones de progreso de MCP**: el mundo
   ejecuta la herramienta en un hilo de trabajo e informa de un progreso legible por etapas, y el
   cerebro **amplía el plazo con cada progreso, declara la muerte solo ante el silencio y pone un
   tope al total**. Esto se generaliza a cualquier mundo con acciones atómicas lentas.
2. LangGraph pasó a ser el sustrato de la orquestación ReAct, sustituyendo a la versión casera
   ingenua.
3. El motor de ajedrez pasó a ser un servicio. Un servicio se diferencia de un mundo en que un
   servicio responde preguntas de ANIMA (un asesor) mientras que un mundo recibe órdenes de ANIMA
   (la realidad). Los servicios los declaraba el propio mundo (`anima://services`) y se montaban
   automáticamente en el apretón de manos.
4. Se borraron el modo partida, los árboles de comportamiento y toda la capa de habilidades: el
   ajedrez vuelve a ser una conversación normal (di «te toca»), y leer el tablero, calcular y
   descomponer los decide el LLM sobre la marcha. Observar–pensar–actuar quedó como el único bucle
   principal.
5. Logs de sesión unificados: las llamadas al LLM, el tráfico de los mundos y las llamadas a
   servicios se funden por sesión en un solo flujo, que en el frontend se puede ver y copiar por
   sesión.
6. Las cámaras múltiples pasaron a ser de primera clase: una percepción puede llevar varias imágenes
   con nombre, y el frontend muestra las vistas en directo una al lado de la otra. gazebo-chess ganó
   dos cámaras y un tablero legible (casillas y coordenadas en los bordes), y «quita esa / pon esta
   / déjala ahí» se midió de extremo a extremo, del lenguaje a la acción.

## [0.4.0] — 2026-07-02

Lo principal: una interfaz de ajedrez en Gazebo, teleoperación y movimiento cartesiano de la pinza.

Novedades:

1. Se abandonó la AWI casera sobre HTTP en favor del servidor MCP estándar. El antiguo esquema de
   perceive, invoke y guidance pasó a ser Tools, Resources y Prompts.
2. El motor de ajedrez dejó de ser parte de una habilidad de ajedrez y pasó a ser un servidor MCP
   por derecho propio.
3. Un mundo nuevo, gazebo-chess: una simulación en Gazebo construida sobre el modelo Episode1 —el
   sustituto de SOMA Zero— con una pinza y unas piezas simuladas.
4. Movimiento cartesiano implementado, y agarre teleoperado de una pieza conseguido.

## [0.3.0] — 2026-06-30

Lo principal: un mundo con cámara real, que dejó a ANIMA ver por primera vez el mundo físico. Una
versión ligera, dedicada sobre todo a probar el flujo desde una cámara real.

Novedades:

1. Un mundo nuevo, camera, con resolución configurable.
2. Detalles de la habilidad de ajedrez ajustados.
3. Depuración e interfaz: la página anima-logs tenía un fallo de atribución de sesión que dejaba la
   «vista por sesión» permanentemente vacía; corregido, y además ganó copiar una sesión entera de
   un clic con todos los campos a la vista. El frontend ganó un tema claro y un interruptor, y AWI
   y anima-logs pasaron a ser paneles incrustados en la página de inicio.

## [0.2.0] — 2026-06-30

Lo principal: un programa nuevo de tablero simulado, sim-chess, y una habilidad de ajedrez. Se
puso en claro el marco de orquestación del agente.

Novedades:

1. Un mundo nuevo, sim-chess, capaz de simular gomoku, ajedrez, go y otros tableros. ANIMA solo ve
   la imagen de sim-chess, nunca su estado interno.
2. Un modo ajedrez en la interfaz de ANIMA: al entrar arranca un modo en bucle con árbol de
   comportamiento en el que ANIMA sigue jugando sin que el usuario tenga que hablar cada vez.
3. Se diseñaron el humano en el bucle y la evaluación, con una prueba de concepto sencilla.
4. Se fijó la abstracción de arriba abajo «Orchestrator → Skill → (Skill) Adapter → Behaviour Tree
   → Tools».
5. Se fijaron las tres peticiones centrales de AWI: perceive, invoke y capabilities.

## [0.1.0] — 2026-06-27

Lo principal: la primera versión de ANIMA Zero. El marco se reescribió por completo, sustituyendo
al prototipo anterior ANIMA O1 y sin reutilizar ni una línea suya.

Novedades:

1. La arquitectura central de separar la cognición del mundo: ANIMA, como sistema cognitivo, piensa
   y decide; un mundo, como entidad independiente, percibe y ejecuta; y ambos se encuentran a
   través del protocolo estándar AWI.
2. El concepto de «mundo» definido: un mundo puede ser cualquier entidad independiente —un
   programa, un robot, un entorno— y ANIMA se comunica con él y lo opera a través de AWI.
3. Una primera interfaz de conversación para ANIMA, con sesiones, memoria guardada en local y la
   posibilidad de cambiar de cerebro a mitad de la conversación.
4. El primer mundo de ejemplo, sim-desk: un escritorio virtual, un bolígrafo y un lienzo, que
   ofrece tres capacidades —mover el bolígrafo, dibujar, borrar— para validar todo el protocolo,
   con la imagen transmitida a ANIMA.

## [Anima O1] — Antes del 2026-06-27

ANIMA O1 fue un diseño temprano. Se desmontó por completo durante el desarrollo de ANIMA Zero y se
reconstruyó desde cero, así que sus detalles no se recogen aquí. ANIMA O1 y los primeros trabajos
de SOMA fijaron la dirección System 1 / System 2 y pusieron los cimientos conceptuales de ANIMA
Zero y SOMA Zero.
