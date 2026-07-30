# Hoja de ruta

<a href="../../../ROADMAP.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/ROADMAP.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/ROADMAP.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="../fr/ROADMAP.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="ROADMAP.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

Esto no es una lista de deseos. Es el espejo de lo que el CHANGELOG ya admite que no funciona,
más las deudas contraídas a sabiendas, cada una con un número para poder señalarla.

Una hoja de ruta de funcionalidades que nadie ha empezado es publicidad. Una hoja de ruta de
fracasos medidos es un plan.

## Madurez

Aquello con lo que puedes contar, dicho sin rodeos.

| Parte | Madurez | Qué significa |
|---|---|---|
| El contrato AWI | **Estable** | Solo añadidos dentro de la v1; una ruptura obtiene una versión mayor nueva |
| El núcleo del cerebro (orquestador, sesiones, adaptadores de LLM) | **Beta** | Funciona, y las tripas todavía se mueven entre versiones |
| El modelo de confianza | **Beta** | Las reglas están asentadas; las superficies que las rodean, no |
| Los mundos | **Experimental** | Cada uno existe para probar una cosa, y se reescribe cuando esa cosa cambia |

**Esto es un prototipo de investigación, no un marco de producción.** No tiene certificación de
seguridad y nunca ha movido hardware real. Véase [SECURITY.md](SECURITY.md).

## Objetivos abiertos

### R1 · La identificación de habitaciones tiene sesgo de confirmación

Cinco habitaciones objetivo, un intento cada una: dos aciertos, dos fallos, una sin terminar.
Medido en la v1.0 y sin cambios desde entonces.

Lo interesante es lo que *no* es. La sospecha era que una cocina y un baño se parecen desde
0,38 m, que es parte de la razón por la que se añadió el humanoide; pero a 1,25 m ve con claridad
la placa y la campana extractora y sigue diciendo que es un baño. Frente a la misma puerta, el
modelo compone el relato que encaja con la habitación que está buscando en ese momento.

Apunta al criterio de aceptación en vez de a la percepción: describir primero y clasificar
después, y apretar lo que puede significar «lo estoy viendo, luego he llegado».

### R2 · El cambio de idioma de los prompts no se ha medido

La v1.1 reescribió en inglés todos los prompts que lee el modelo, antes en chino: el prompt de
sistema, las descripciones de herramientas, los bloques de estado y la `guidance` de los mundos.

**Eso es un cambio de comportamiento, y la prueba comparativa que lo zanjaría no se ha vuelto a
ejecutar.** El razonamiento está en `src/prompts.py`: los modelos ajustados a instrucciones se
entrenan predominantemente en inglés, y un prompt en chino envolviendo esquemas de herramientas
en inglés es un contexto mezclado. El efecto medido en la literatura es pequeño, de unos pocos
puntos porcentuales, y a veces negativo.

Deuda pendiente: las mismas cinco habitaciones, antes y después, una al lado de la otra. Hasta
que eso exista, «aquí el inglés es mejor» es una hipótesis, no un resultado. Si resulta peor, el
punto de vuelta atrás es un solo archivo.

### R3 · La inyección de prompts está mitigada, no resuelta

La `guidance` de un mundo se acota, se etiqueta como material y no como instrucción, y se limita
en longitud. Eso sube el listón. Nada la inspecciona en busca de intención hostil, y ninguna
comprobación de ese tipo sería fiable: es un problema abierto para todo el campo.

La protección que funciona es la aprobación humana de `anima world add`, y solo funciona si la
persona lee de verdad el manifiesto. Véase [SECURITY.md](SECURITY.md) §2.

### R4 · Cuatro CVE de severidad alta en el árbol npm del frontend

`next`, `postcss`, `sharp` y `@tailwindcss/postcss`, todas corregibles dentro del rango actual.
Son de tiempo de compilación y ninguna llega al bundle del navegador, pero son reales y son
conocidas.

Aún sin hacer porque un salto de versión mayor de Next exige revisar la interfaz a ojo, que es un
trabajo distinto del de publicar.

### R5 · La biblioteca de reglas de ajedrez es lo bastante rápida, no rápida

`packages/anima-chess` es entre dos y cuatro veces más lenta que python-chess según la posición:
suficiente para la búsqueda consultiva de profundidad 3 a la que sirve (1,27 s frente a un tope
de 1,5 s), e insuficiente para cualquier cosa más profunda.

El coste conocido es que el hash Zobrist se reconstruye desde cero en cada jugada en vez de
actualizarse de forma incremental. Está documentado en `push()` como una elección deliberada, y
es lo primero que habrá que cambiar cuando llegue una tabla de transposición.

### R6 · El chino todavía asoma en unas pocas superficies

La pasada lingüística de la v1.1 llevó al inglés todo lo que lee un modelo y todo lo que muestran
la CLI y la aplicación web. Quedaron cuatro sitios, cada uno por un motivo:

- `src/worlds/desk/awi_mcp.py`: descripciones de recursos y prompts de MCP. Este archivo existe
  como **copia idéntica byte a byte en seis sitios**, uno de ellos un submódulo, sostenido por una
  prueba. Cambiar cuatro cadenas significa cambiar las seis al unísono, y eso no es algo que se
  haga el día de una publicación.
- `src/dev_turn.py`: un arnés de desarrollo, no un comando que se distribuya.
- Las descripciones de campos de `src/config.py` y dos líneas de log del orquestador: solo
  internas. Las pistas del panel que antes alimentaban están ahora separadas y en inglés.

Se encontraron instalando el wheel y ejecutándolo, no leyendo el código. El barrido que los
encontró merece conservarse: recorrer el AST, recoger las constantes de cadena que no son
*docstrings* y buscar caracteres CJK.

### R7 · La comprobación de caducidad de la interfaz estaba ciega justo donde importaba

`anima serve` muestra cuándo se compiló la aplicación web incluida, para que un wheel empaquetado
sin recompilar la interfaz se note. Leía la fecha de compilación del mtime de `index.html`, y
`pip install` reescribe los mtimes al momento de la instalación, así que **toda copia instalada
afirmaba estar recién compilada**. La comprobación solo funcionaba en una copia de trabajo de
desarrollo, que es donde menos falta hacía.

Corregido en el repositorio (la compilación escribe un archivo `.build-time`, que ahora manda
sobre el mtime, y una prueba lo fija). **El wheel 1.1.0 de PyPI conserva el comportamiento
antiguo**: la fecha de compilación que declara es su fecha de instalación. Nada más de esa
versión se ve afectado; la interfaz que lleva se verificó leyendo la propia página, no confiando
en la marca de tiempo.

Se descubrió instalando 1.1.0 desde PyPI y notando que decía haberse compilado seis horas después
de la compilación real.

### R8 · Las traducciones no las ha leído ningún hablante nativo

231 entradas de interfaz en japonés, traducidas por el mantenedor con la ayuda de una revisión
independiente que encontró 22 defectos reales: terminología colapsada en un solo término, un
compuesto inventado, dos frases que perdieron un sustantivo por el camino y cuatro etiquetas de
barra lateral lo bastante largas como para truncarse. Esos están corregidos. Los documentos raíz
en japonés, francés y español vinieron después, por el mismo método. El francés y el español
existen solo como documentos; la interfaz habla inglés, chino y japonés.

Lo que no está corregido es que **nadie que hable esos idiomas ha leído nada de ello**. Cada
revisión fue otro modelo, no una persona. La terminología es al menos coherente dentro de cada
idioma (world = ワールド / monde / mundo; ground truth = 真値 / vérité terrain / verdad de
referencia) y no falta ningún marcador de sustitución, que es lo que los hace utilizables como
primeros borradores; pero «utilizable como primer borrador» es lo que se afirma, no «correcto».
El inglés y el chino son los idiomas del propio mantenedor y no llevan esa advertencia.

### R9 · Dos páginas no tienen selector de idioma

`/awi` y `/session-logs` se dibujan a página completa sin la barra lateral, y el selector vive en
esa barra. Abiertas directamente, heredan el idioma que haya en `localStorage` y no ofrecen forma
de cambiarlo. Si se llega a ellas desde la aplicación principal, que es el camino normal, están
bien.

Sin corregir porque las opciones honestas son ambas más grandes que el problema: poner el selector
en un layout que compartan las dos rutas, o aceptar que esas dos rutas son superficies
secundarias.

### R10 · Nueve dependencias no tienen tope, y una de ellas volverá a romper la CI

Dos veces en una semana un repositorio en verde se puso en rojo sin que nadie cambiara una línea:
ruff 0.16.0 amplió su conjunto de reglas por defecto (205 avisos en código que nadie había
tocado), y mcp 2.0.0 movió `mcp.server.fastmcp`, que `services/boardgame_engine/app.py` importa
directamente. Ambas tienen ya un tope. Nueve dependencias de ejecución no lo tienen.

**Es deliberado, no un descuido.** anima-zero es una biblioteca que la gente instala, y un tope
superior en una biblioteca publicada se convierte en el problema de resolución de dependencias
*del usuario*, uno que además no puede esquivar. La regla aquí es poner tope solo a lo que se ha
demostrado que rompe, y lo que rompió tenía una forma común: ambas dependían de algo más profundo
que la superficie pública y documentada (un submódulo interno; la configuración por defecto de una
herramienta). Con ese criterio, ninguna de las nueve restantes cumple.

Así que el plan es ponerle tope a la tercera cuando rompa. Una CI en rojo más un cambio de dos
líneas cuestan unos diez minutos; un tope especulativo le cuesta a todo usuario futuro. Y la
ejecución en rojo trae información: es así como te enteras de que la API de arriba se movió.

Si algún día las interrupciones pesan más que eso, el arreglo es un archivo de restricciones solo
para la CI, no más topes en `pyproject.toml`: la CI instala versiones fijas mientras el paquete
publicado sigue siendo permisivo. Tiene su propio precio: algo más que mantener, y *retrasa* el
momento en que descubres que arriba cambió algo. El razonamiento está escrito al principio de la
lista de dependencias, que es donde está de pie quien siente la tentación de añadir un tope.

## No previsto

Decir que no es parte de una hoja de ruta.

- **Chess960, PGN, libros de aperturas y UCI** en `anima-chess`: usa python-chess, que es mejor en
  todo eso.
- **Un instalador por curl.** ANIMA es Python y sus mundos son Python; quien fuera a ejecutarlo ya
  tiene Python. `uv tool install` da la misma experiencia de un solo comando sin añadir un segundo
  canal de distribución que haya que mantener honesto.
- **Hacer al cerebro más listo sobre un mundo concreto.** El conocimiento específico de una tarea
  vive en el mundo. En el momento en que el orquestador aprenda qué es el ajedrez, se acabó la
  pretensión de ser un marco genérico.
