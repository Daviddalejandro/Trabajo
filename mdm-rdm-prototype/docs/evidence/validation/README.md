# Evidencia · conjunto de validación en la consola (datos sintéticos)

Capturas de la Consola de Stewardship tras `make validation-load` (SAP ECC KNA1 + sistema de crédito),
generadas con Playwright el 2026-09-14. Resultado del matching: 187 `AUTO_MERGE`, 2 `PROBABLE` y 1 `POSSIBLE`.

| Archivo | Contenido |
|---|---|
| `01_zona_gris_cola.png` | Cola con los dos pares `PROBABLE` (V2: TI vs. CC; V18: dígito transpuesto), ambos `SAP_ECC_SD · CREDITO_CORE` |
| `02_zona_gris_detalle_V2.png` | Detalle del par V2: 70/100, documento 0/30 (tipo distinto), resto de atributos plenos, evidencia A/B, owners de las dos fuentes y decisión con justificación obligatoria (**Fusionar (pedir a owners)**) |
| `03_zona_gris_possible_V3.png` | Detalle del par V3 (`POSSIBLE`, 62/100): homónimos con la misma fecha y documentos distintos |

Guía paso a paso: [`docs/GUIA_PRUEBAS_MANUALES.md`](../../GUIA_PRUEBAS_MANUALES.md).
