# Evidencia · conjunto de validación en la consola (datos sintéticos)

Capturas de la Consola de Stewardship tras `make validation-load` (SAP ECC KNA1 + sistema de crédito),
generadas con Playwright el 2026-09-14. Resultado del matching: 187 `AUTO_MERGE`, 2 `PROBABLE` y 1 `POSSIBLE`.

| Archivo | Contenido |
|---|---|
| `01_zona_gris_cola.png` | Cola con los dos pares `PROBABLE` (V2: TI vs. CC; V18: dígito transpuesto), ambos `SAP_ECC_SD · CREDITO_CORE` |
| `02_zona_gris_detalle_V2.png` | Detalle del par V2: 70/100, documento 0/30 (tipo distinto), resto de atributos plenos, evidencia A/B, owners de las dos fuentes y decisión con justificación obligatoria (**Fusionar (pedir a owners)**) |
| `03_zona_gris_possible_V3.png` | Detalle del par V3 (`POSSIBLE`, 62/100): homónimos con la misma fecha y documentos distintos |
| `04_vista360_resumen.png` | Vista 360 con el resumen ejecutivo en la cabecera (2026-09-15): elegibilidad por finalidad con la razón de exclusión (`COMMERCIAL ✗ NO_CONSENT`), servicios activos por UES, hallazgos DQ abiertos, pares de matching pendientes y consolidación (fuentes, merges, autorizaciones) |
| `05_vista360_pares_pendientes.png` | Capa 7 con los pares pendientes del party (V3, `POSSIBLE` 62) enlazados a la consola, antes del survivorship por campo |
| `06_vista360_linea_tiempo.png` | Capa 6: línea de tiempo de auditoría con filtro por entidad y carga del historial completo |
| `07_roles_beneficiario_bprol.png` | Capa 4 del caso V26 (2026-09-15): el rol lo declara `BPROL` de SAP ECC SD — AFFILIATE con sub-rol AFFILIATE_BENEFICIARY y UES SUBSIDIO —, con el segmento AFFILIATION y la relación `BENEFICIARY_OF` hacia el titular |
| `08_roles_doble_bprol.png` | Capa 4 del caso V27: `BPROL` multivalor produce afiliado y proveedor de servicios desde un solo registro de SD; `CUSTOMER` aparece solo desde CREDITO_CORE con la UES CREDITO |

Guía paso a paso: [`docs/GUIA_PRUEBAS_MANUALES.md`](../../GUIA_PRUEBAS_MANUALES.md).
