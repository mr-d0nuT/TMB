# Diseño: FGC en el planificador + botón "Alternativa" en navegación

Fecha: 2026-07-09

## Problema 1 — El planificador no ofrece el FGC como último tramo

Ejemplo del usuario: para ir a Santa Coloma de Cervelló, lo más corto es acabar
en Ferrocarrils (estación CL de la línea Llobregat-Anoia), pero la app no lo
propone.

**Causa raíz.** `planTo()` fusiona el planner de TMB (bus + metro + tram) con
dos composiciones propias: Renfe media distancia e Hispano Igualadina. Ambas
solo se ejecutan como *fallback* cuando el planner no devuelve nada
(`if (its.length === 0)`), y **no existe ningún compositor de rutas FGC**,
aunque la app ya tiene las estaciones (`FGC_STATIONS`) y el horario del día
(dataset `viajes-de-hoy` de dadesobertes.fgc.cat) para la vista de llegadas.
Como Santa Coloma de Cervelló cae dentro del área del planner de TMB, este
devuelve itinerarios (a menudo enrevesados: bus hasta media línea + tren) y
los fallbacks nunca llegan a ejecutarse. El itinerario natural —metro hasta
Pl. Espanya + S3/S4 directo— no aparece.

**Solución.** Nuevo compositor `fgcJourneys(origin, dest)` que se ejecuta
**siempre** en paralelo con el planner (no como fallback) y se fusiona antes
de deduplicar y ordenar por hora de llegada:

1. Estaciones candidatas: las 3 más cercanas al origen (≤ 4500 m) y las 2 más
   cercanas al destino (≤ 3000 m), desde `FGC_STATIONS`.
2. Para cada par origen→destino se piden los pasos del día en ambas estaciones
   (`viajes-de-hoy`, desde ahora, ordenados por hora). El dataset no expone
   `trip_id`, así que el mismo tren se casa por
   `(route_short_name, trip_headsign, shape_id)` exigiendo
   `stop_sequence(destino) > stop_sequence(origen)` y emparejando en orden
   FIFO (los trenes de un mismo patrón no se adelantan entre sí). El join por
   `shape_id` garantiza además no mezclar las dos redes desconectadas de FGC
   (Barcelona-Vallès y Llobregat-Anoia).
3. Tramos a pie si la estación queda a más de 80 m; si la estación de subida
   queda a más de 1200 m, se encadena el acceso con el planner de TMB
   (metro/bus), igual que ya hace la Hispano Igualadina.
4. Caché de 60 s por estación para no repetir peticiones al abrir alternativas.

Con esto, "ir a Santa Coloma de Cervelló" ofrece: L1/L3 → Pl. Espanya →
S3/S4 → Santa Coloma de Cervelló, que llega antes y aparece primero.

## Problema 2 — Botón rojo "Alternativa" durante el trayecto

Petición: con un trayecto iniciado, un botón rojo **"Alternativa"** que
muestre rutas más rápidas hasta el destino **a partir de la próxima parada**
(p. ej. ibas en tren hasta Passeig de Gràcia, pero bajarte en Sants y coger un
metro que sale en 2 minutos llega antes).

**Diseño.**

- **UI**: botón rojo `⚡ Alternativa` en la fila de acciones del `tripPanel`,
  junto a AR y Finalizar. Al pulsarlo se abre una lista de tarjetas dentro del
  panel con: tira de tramos (`legStrip`), parada donde bajarse, hora de
  llegada, minutos que ahorra y botón "Cambiar". Si no hay nada mejor:
  toast "Ya vas por la ruta más rápida".
- **Próxima parada**: se localiza el tramo actual proyectando la posición GPS
  sobre la ruta (`projectOnRoute`, ya existente). Si el tramo es de transporte
  y trae `intermediateStops` (el planner OTP los devuelve pidiendo
  `showIntermediateStops=true`, que se añade a `planReq`), la próxima parada es
  la primera con `arrival` en el futuro; si no hay intermedias (tramos
  compuestos de Renfe/FGC/Hispano), se usa el final del tramo actual
  (transbordo o bajada). Si se está andando, las alternativas salen de la
  posición actual.
- **Cálculo**: se reutiliza la búsqueda de `planTo` extraída a
  `gatherJourneys(origin, dest, whenMs)` (planner TMB fusionado + FGC +
  fallbacks), pasando `date`/`time` al planner OTP con la hora estimada de
  llegada a la próxima parada (verificado: la API los acepta). Los
  compositores propios (FGC/Renfe/hbus) ya filtran por hora de salida ≥ esa
  hora. Se descartan las alternativas que no mejoren la ETA actual en al menos
  2 minutos y las que repitan la secuencia de líneas restante del trayecto en
  curso.
- **Cambio de ruta**: al elegir una alternativa se sustituye el trayecto
  activo sin salir de la navegación: los nuevos tramos se anteponen con el
  trozo del tramo actual entre tu posición y la parada de bajada, de modo que
  la polilínea y el progreso siguen siendo continuos.

## Errores y límites

- Cualquier fuente que falle (FGC open data, planner) se ignora en silencio y
  se sigue con el resto, como ya hace el código existente.
- Los tramos compuestos (Renfe/FGC/hbus) no llevan lista de paradas
  intermedias, así que en ellos "próxima parada" significa "próximo transbordo
  o bajada". El ejemplo Altafulla→Sants queda cubierto cuando el tramo lo
  planifica el planner de TMB (con intermedias); para media distancia Renfe la
  alternativa se calcula desde la estación de bajada.

## Verificación

- En navegador (servidor estático local): origen simulado en Barcelona,
  `planTo` a Santa Coloma de Cervelló debe incluir un itinerario cuyo último
  tramo sea FGC directo desde Pl. Espanya y ordenarlo por llegada.
- Iniciar trayecto y pulsar Alternativa: debe listar rutas desde la próxima
  parada con llegada anterior a la ETA actual y permitir cambiar a una de
  ellas sin romper la navegación.
