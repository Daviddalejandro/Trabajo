# Conjunto de validación · SAP ECC + sistema de crédito

Validación integral del prototipo con dos fuentes adicionales, distintas de las cinco del escenario
demo (SPEC §13). Todo es sintético y reproducible (`seed 20260914`).

```bash
make test-validation                      # genera, vacía staging/mdm, ingiere y verifica (RDM se conserva)
python backend/cli.py validation-generate # solo los datasets: backend/data/validation/
python backend/cli.py ingest --source ecc_sd --file data/validation/ecc_kna1_validacion.csv
python backend/cli.py ingest --source credito_core --file data/validation/credito_core.csv
make validation-load                      # lo mismo, en un paso, para trabajar la zona gris en la consola (#/stewardship)
```

## Fuentes

| Fuente | Sistema (RDM) | Estructura | Registros |
|---|---|---|---|
| `ecc_kna1_validacion.csv` | `SAP_ECC_SD` (adaptador `ecc_sd`) | KNA1: KUNNR, STKZN, NAME1/NAME2, STCD1/STCD2, GBDAT, LAND1, REGIO, ORT01, STRAS, TELF1, SMTP_ADDR, CTLPC, ZZ_CONTRATOS, LOEVM, ERDAT, AEDAT | 260 (personas y empresas) |
| `credito_core.csv` | `CREDITO_CORE` (adaptador `credito_core`, nuevo) | Maestro de cartera: ID_CLIENTE, TIPO_ID (C/E/T/P/N), NUM_ID, NOMBRES, APELLIDOS, SEXO (H/M), FECHA_NAC (dd/mm/aaaa), CIUDAD, DIRECCION, EMAIL, CELULAR, TEL_ALTERNOS (`numero:TIT|REF:CONF|NOCONF|ERR`), OBLIGACIONES (`numero:CS|TC:VIG|MOR|CAN:inicio:fin`), CALIFICACION (A–E), AUT_TRATAMIENTO, AUT_COMERCIAL, AUT_CENTRALES (S/N), FALLECIDO, CODEUDOR_ID, RAZON_SOCIAL | 232 |
| `credito_core_delta.csv` | corrida delta | Un cliente con correo nuevo (V13) | 1 |
| `rne_validacion.csv` | RNE simulado | El celular del caso V11 más ruido | 21 |

Solapamiento: 200 personas comunes con variaciones de captura (mayúsculas, segundo nombre, correos),
60 solo en ECC, 40 solo en crédito, 12 empresas (una en ambas fuentes).

Homologaciones nuevas en el RDM (`SOURCE_VALUE_MAPPING`, sistema exacto `CREDITO_CORE`): TIPO_ID, SEXO,
PRODUCTO (CS → CREDITO_SOCIAL, TC → TARJETA_CREDITO), ESTADO_OBLIG (VIG/MOR/CAN → ACTIVE/SUSPENDED/CLOSED),
CALIFICACION (A–E → LOW/MEDIUM/HIGH), TIPO_TEL, ESTADO_TEL, FALLECIDO. Relación nueva `GUARANTOR_OF` /
`GUARANTEED_BY` (codeudor). `CREDITO_CORE` entra en `SOURCE_PRIORITY` después de SAP_ECC_MM.

## Casos plantados y desenlace esperado

| Caso | Construcción | Desenlace verificado |
|---|---|---|
| V1 | Mismo documento, nombre con error tipográfico en crédito | Auto-merge; un documento golden |
| V2 | Crédito con tarjeta de identidad antigua (tipos de documento no comparables); nombre, fecha y correo iguales, celular distinto | PROBABLE por el grupo G3 (evidencia ≈ 96 sobre cobertura 70); dos owners (steward.sd, steward.credito) → OWNER_CONSENSUS; unmerge; NO_MATCH vinculante |
| V3 | Homónimos con la misma fecha de nacimiento y documentos distintos (mismo tipo) | PROBABLE por el grupo G2 (evidencia 62): el documento contradictorio impide fusionar solo y el par va a revisión, nunca a merge automático |
| V4 | Dos clientes de crédito con el mismo documento + ECC | Los tres colapsan en un golden con 3 XREF y 3 obligaciones |
| V5 | Empresa con el mismo NIT en ECC y crédito | Merge de organización; NIT golden |
| V6 | FALLECIDO=S con obligación vigente | `party_status=DECEASED`; toda elegibilidad `DECEASED` |
| V7 | AUT_COMERCIAL=N | COMMERCIAL `CONSENT_REVOKED`; COLLECTIONS `ELIGIBLE` |
| V8 | Solo obligaciones canceladas (cierre 2015) | COLLECTIONS `NO_ACTIVE_SERVICE`; retención FINANCIAL_10Y vencida → candidato a purga |
| V9 | Obligación MOR (SUSPENDED) | COLLECTIONS `ELIGIBLE` (Ley 2300/2023 art. 3) |
| V10 | Teléfonos de gestión TIT/NOCONF, REF/NOCONF, TIT/ERR | Solo COLLECTIONS en los dos primeros; `THIRD_PARTY_CONTACT` para la referencia; `INVALID_CONTACT` en el errado |
| V11 | Celular en el RNE | PHONE/COMMERCIAL `RNE_EXCLUSION`; COLLECTIONS y BENEFITS `ELIGIBLE` |
| V12 | Sin documento (cuarentena), teléfono inválido (advertencia), producto LB sin homologar | Cuarentena; hallazgo VALIDITY; alta de LIBRANZA + homologación + rehomologar → elegibilidad recalculada |
| V13 | Delta con correo nuevo | XREF hit, sin matching, survivorship MOST_RECENT, `golden_version` incrementada |
| V14 | CODEUDOR_ID | `GUARANTEED_BY` y su inversa `GUARANTOR_OF` |
| V15 | ARCO CANCELLATION con obligación vigente | 3 consentimientos revocados; no es candidato a purga |
| V16 | Audiencia COLLECTIONS / PHONE / CREDITO_SOCIAL ACTIVE | Incluye V1 y V16, excluye V6 y V8; auditada |
| V17 | match-preview con los datos de V1 | AUTO_MERGE sugerido sin persistir |
| V18 | Documento con dígito transpuesto | G4 satisfecho pero el veto del documento (modo REVIEW) lo baja a PROBABLE; NO_MATCH del steward es final |
| V19 | Nombre en mayúsculas en crédito, correo nuevo | Nombre desde SAP_ECC_SD (prioridad); correo desde CREDITO_CORE (MOST_RECENT) |
| V20 | Feed de cambios | Inserciones de obligaciones con fuente CREDITO_CORE |
| V21 | Export a Drive | Hoja "Sistemas fuente" incluye CREDITO_CORE |
| V22 | Vista 360 de un golden fusionado | 2 fuentes, 3 vínculos, segmento FINANCIAL_RISK de la fuente autoritativa (SD) vigente |
| V23 | Segunda corrida FULL de ambos archivos | Todo UNCHANGED por hash, 0 matching |
| V24 | Crosswalk | `CREDITO_CORE/SEXO/H` ↔ `SAP_CRM/GESCHL/1` ↔ `SF_EC/gender/M` |
| V25 | Auditoría de un party solo de crédito | Todas las inserciones con lote, fuente CREDITO_CORE y actor |
| V26 | `BPROL=ZBEN` con `ZZ_BENEFICIARIO_DE` | Rol AFFILIATE, sub-rol AFFILIATE_BENEFICIARY, UES SUBSIDIO y relación `BENEFICIARY_OF` con el titular (con su inversa) |
| V27 | `BPROL=ZAFI;ZPRO` en un solo KUNNR | Dos filas de rol: afiliado (SUBSIDIO) y proveedor de servicios (NOT_APPLICABLE) |
| V28 | `BPROL=ZXXX` sin homologar | Rol y sub-rol en UNKNOWN con hallazgo VALIDITY; se corrige con rehomologar (§7.2) |

## Hallazgos de la validación

- Las banderas `S/N` del core de cartera no eran reconocidas por el helper genérico `yn` (pensado
  para Y/N y X): se añadió `sn()` en el adaptador. Sin esa corrección los consentimientos otorgados y
  el marcador de fallecido se perdían en silencio.
- La rehomologación de un producto de crédito cambia `collections_applies`; ahora `rehomologate`
  recalcula la elegibilidad de los parties corregidos.
- Una obligación con producto sin homologar se descartaba en la etapa de calidad y quedaba
  irrecuperable. Ahora se conserva con servicio `0 = UNKNOWN` (UES `NOT_APPLICABLE`) y el hallazgo
  guarda la fila destino, de modo que `rehomologate` la corrige sin nueva extracción (SPEC §7.2).
- `ingest --source all` se limita a las fuentes con CSV por defecto en `data/synth/`; las fuentes
  de validación se ingieren con `--file`.
