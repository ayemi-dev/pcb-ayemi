# Resultado del DRC

Generado por `tools/drc.py` con kicad-cli 10.0.6 y relleno de zonas. No lo edites a mano.

| Concepto | Cantidad |
|---|---|
| Errores y conexiones pendientes | 0 |
| Advertencias | 2 |
| Advertencias justificadas | 2 |
| Advertencias sin justificar | 0 |
| Excluidas en KiCad | 0 |

## Por tipo

| Origen | Severidad | Tipo | Cantidad |
|---|---|---|---|
| violación | warning | silk_edge_clearance | 2 |

## Advertencias justificadas

- `silk_edge_clearance`: Silkscreen clipped by board edge. **Motivo:** Los dos trazos de serigrafía del contorno del USB-C (J101) que llegan al borde de la placa vienen de la huella oficial de KiCad: la caja metálica del conector se apoya en el borde y su contorno impreso queda recortado por el corte. Solo afecta al dibujo de la serigrafía, no al cobre ni a la función.
- `silk_edge_clearance`: Silkscreen clipped by board edge. **Motivo:** Los dos trazos de serigrafía del contorno del USB-C (J101) que llegan al borde de la placa vienen de la huella oficial de KiCad: la caja metálica del conector se apoya en el borde y su contorno impreso queda recortado por el corte. Solo afecta al dibujo de la serigrafía, no al cobre ni a la función.

**Veredicto:** DRC en 0 y todas las advertencias justificadas.
