# ADR-0006: Cálculo determinista de costos y tiempos

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: Edward Rayo, Elizabeth Toro, Santiago Cardona

## Contexto

El JSON de respuesta de la API incluye campos con implicaciones
financieras y operacionales:

- `costo_estimado_cop` y su `desglose_costo` (combustible, peajes,
  viáticos, seguro, imprevistos).
- `tiempo_estimado_min`.

Delegar el cálculo de estos números al LLM es peligroso: los LLMs son
propensos a alucinar cifras numéricas, especialmente cuando deben
combinar múltiples fuentes (tarifas SICE-TAC, peajes por categoría
vehicular, componentes de costo por tipo de vehículo).

El grafo Neo4j contiene los datos autoritativos (`Tarifa`, `Peaje`,
`ComponenteCosto`, `Corredor.tiempo_estimado_min_carga`), así que los
números pueden derivarse con fórmulas claras.

## Decisión

Los campos numéricos de la respuesta se **calculan en código**, no por
el LLM:

- `tiempo_estimado_min` = `Corredor.tiempo_estimado_min_carga` +
  `impacto_min_carga` (del estado actual INVIAS).
- `costo_estimado_cop` = suma de componentes calculados desde el grafo:
  - `combustible_cop` = `distancia_km × Vehiculo.costo_km_cop × factor_combustible`
  - `peajes_cop` = suma de `Peaje.valor_cop` para los peajes del
    corredor en la categoría vehicular correspondiente
  - `viaticos_cop`, `seguro_cop`, `imprevistos_cop` según `ComponenteCosto`
    de SICE-TAC
- `desglose_costo` expone cada sumando.

El LLM sigue siendo responsable de:

- Elegir `vehiculo_recomendado` entre la `flota_disponible`.
- Redactar `justificacion` y `alternativas` citando artículos y chunks.
- Emitir `alertas` contextuales a partir del estado del corredor y la
  normativa aplicable.

## Consecuencias

- **Positivas**:
  - Cero alucinación en datos financieros.
  - Los números son trazables a fórmulas explícitas y a nodos del grafo.
  - Las pruebas unitarias pueden validar cálculos con fixtures.
- **Negativas**:
  - El módulo de cálculo debe mantenerse al día cuando SICE-TAC actualiza
    fórmulas o componentes.
  - Dos fuentes de lógica en la respuesta final: el calculador
    determinista y el LLM. Hay que garantizar que no se contradigan
    (p.ej. que el LLM no cite un costo distinto al calculado).
- **Neutrales**:
  - El calculador vive en `api/src/core/services/` como módulo separado
    del servicio de recomendación, reutilizable por tests.

