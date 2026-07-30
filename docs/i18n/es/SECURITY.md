# Seguridad

<a href="../../../SECURITY.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="../zh/SECURITY.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="../ja/SECURITY.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>
<a href="../fr/SECURITY.md"><img src="https://img.shields.io/badge/Langue-Fran%C3%A7ais-8250df?style=flat-square" alt="Français"></a>
<a href="SECURITY.md"><img src="https://img.shields.io/badge/Idioma-Espa%C3%B1ol-1a7f37?style=flat-square" alt="Español"></a>

> ANIMA Zero es un **prototipo de investigación abierto**, hecho como proyecto de portafolio y
> de enseñanza. Lo que sigue es un relato honesto de aquello contra lo que protege y de aquello
> contra lo que no.

## 1. Esto es un prototipo, no un sistema certificado

ANIMA no tiene ninguna certificación de seguridad. **No lo uses** en entornos médicos,
industriales, de automoción ni en ningún otro contexto crítico para la seguridad. Hacerlo
exigiría una verificación y una certificación que tendrías que llevar a cabo tú.

## 2. ⭐ Conectar un mundo es una decisión de confianza

Esta es la sección que merece entenderse, porque se deriva de la arquitectura y no de ningún
fallo concreto.

ANIMA es un **anfitrión** en el sentido de MCP, y un **mundo** es un proceso aparte al que se
llega por una URL. La autoridad que le entrega a ese mundo es poco habitual:

| Canal | Dónde acaba el texto escrito por el mundo |
|---|---|
| **`guidance`** | Concatenado en el **prompt de sistema** del cerebro: el canal de mayor autoridad del modelo |
| **Descripciones de herramientas** | La lista de herramientas del *function calling* del modelo |
| **Resultados de las acciones** | El historial de la conversación |
| **`kind` / `readOnlyHint`** | Servía para decidir si la compuerta de seguridad llegaba a ejecutarse (recuperado en la v1.1, más abajo) |

Dicho de otro modo: **conectar el mundo de otra persona significa dejar que un desconocido
escriba en el prompt de sistema de tu cerebro.** No es una preocupación teórica. El sector tiene
nombre para los dos ataques —el **envenenamiento de herramientas** (un texto de descripción que
controla el servidor entra en el contexto del agente y se actúa sobre él como si fuera de
confianza) y el **rug pull** (un servidor se porta bien mientras lo revisan y cambia sus
descripciones una vez aprobado)— junto con incidentes reales y CVE.

### Qué hacemos al respecto

1. **La aprobación se ata al contenido, no a un nombre.** La primera vez que conectas un mundo,
   cada herramienta que declara (nombre, kind, descripción, esquema) y su `guidance` **íntegra**
   se te ponen delante, y decides tú. Lo que se registra es el SHA-256 de ese manifiesto. Si no
   ha cambiado, no se te vuelve a preguntar; **si ha cambiado, se te pregunta de nuevo y se te
   dice qué cambió**. Es la misma idea que SSH fijando la clave de un host o Docker fijando el
   digest de una imagen: sustituir algo nuevo bajo un nombre antiguo tiene que ser detectable.
2. **El contenido de un mundo no aprobado no llega al cerebro.** Sigue apareciendo en la lista y
   sigue indicando si está en línea —para que puedas aprobarlo—, pero su `guidance` nunca entra
   en el prompt de sistema y sus herramientas nunca entran en la lista de herramientas.
3. **La `guidance` se acota y se etiqueta antes de inyectarse.** Al modelo se le dice que ese
   bloque es **material, no una instrucción**, y que no puede anular las reglas que lo preceden.
   Los marcadores de acotación se eliminan del texto del propio mundo, de modo que no pueda
   cerrar el cerco antes de tiempo y hacer que el resto se lea como palabras de ANIMA. También
   hay un límite de longitud.
4. **La compuerta de seguridad se le retiró al mundo (v1.1).** El orquestador leía antes el
   `kind` declarado por el mundo para decidir si consultaba la compuerta, de manera que un mundo
   podía saltársela por completo anotando una herramienta destructiva como de solo lectura.
   **Ahora toda acción de un mundo pasa por la compuerta**, con `kind` como una entrada más de
   esa decisión y nunca como un atajo. Inofensivo mientras la compuerta está abierta en
   simulación; un agujero el día en que se cierre para hardware real, que es la única razón por
   la que existe `safety.py`.
5. Cada uno de estos puntos está sostenido por una prueba en `tests/test_world_trust.py`, contra
   una fixture que hace lo que haría de verdad un mundo malicioso.

### Lo que **no** hacemos: por favor, lee esta parte

- **La inyección de prompts no está resuelta.** La acotación y los límites de longitud suben el
  listón. Nada inspecciona la `guidance` en busca de intenciones hostiles, y ninguna comprobación
  de ese tipo sería fiable. Es un problema abierto para todo el campo.
- **El modelo de confianza gobierna si conectarse, no si lo que te cuentan es cierto.** Un mundo
  aprobado todavía puede enviar imágenes de cámara fabricadas o informar de una acción fallida
  como si hubiera tenido éxito. Lo que ve el cerebro es lo que ese mundo eligió mostrarle.
- **Así que la protección de verdad eres tú**: lee el manifiesto cuando lo apruebes. Una
  aprobación pulsada sin leer no es una aprobación.

### En una línea

**Conecta solo mundos en los que confíes.**

> `ANIMA_TRUST_ALL=1` se salta todas las aprobaciones, para desarrollo: cuando estás editando tu
> propio mundo, el manifiesto cambia con cada guardado. Su sitio es tu máquina y solo tu máquina,
> nunca nada compartido ni publicado.

## 3. El cerebro se equivoca (algo inherente a los LLM)

Las decisiones de ANIMA vienen de un modelo grande de lenguaje, en la nube o local, y **puede
alucinar o juzgar mal**. El diseño lo tiene en cuenta: el cerebro solo *piensa* —selecciona
herramientas y rellena argumentos— y nunca sostiene la verdad lógica. Antes de que ocurra
cualquier cosa real hay una compuerta de seguridad y, donde importa, una persona.

## 4. Hardware real

La versión actual es solo software: mundos virtuales y simulación física. **Nunca ha movido
hardware real.** Pero es hacia donde va ANIMA, así que:

- El movimiento real conlleva riesgo físico. Esas órdenes debe ejecutarlas alguien **presente
  junto a la máquina**.
- Este es un brazo con servos: **la parada de emergencia es cortar la corriente**, y al cortarla
  las articulaciones se quedan sin fuerza y caen. Alguien tiene que estar sujetándolas.
- Mantén el ángulo de la pinza de servo **≤ 100°**; más allá, la holgura de los engranajes lo
  vuelve peligroso.
- Comprueba antes de enviar: ¿la acción es legítima?, ¿de verdad lo has visto con claridad?, ¿el
  ángulo de agarre es seguro? Las acciones de alto riesgo o irreversibles necesitan aprobación
  humana explícita.
- ⚠️ Antes del hardware real, `src/core/safety.py` debe pasar de `default_allow=True` a `False`
  con comprobaciones deterministas de verdad. **Esas comprobaciones nunca deben eximir a una
  acción por el `kind` que un mundo haya declarado**: véase §2, punto 4.

## 5. Exposición en red

El backend, por defecto, sirve solo a esta máquina. Antes de escuchar en `0.0.0.0` o de poner
`ANIMA_CORS_ORIGINS=*`, ten claro qué significa: cualquiera en la red puede crear una sesión y
manejar el mundo que hayas conectado. El `*` de `.env.example` es una comodidad para una demo
local, no un valor por defecto para desplegar.

## 6. Claves

Las claves de API de los modelos viven en un `.env` local, ignorado por git y jamás incluido en
un commit. Ten en cuenta también que el contenido de las conversaciones va al proveedor de modelo
que elijas: no pegues en una sesión nada que no deba salir de la máquina.

## 7. Contacto

Abre una incidencia para cualquier cosa relacionada con la seguridad, o escribe al mantenedor (la
dirección está en `pyproject.toml`, bajo `authors`).
