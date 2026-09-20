# Resumen ejecutivo · Prototipo MDM/RDM Party (2026-09-16)

**Objetivo.** Demostrar, con datos exclusivamente sintéticos, que un MDM in-house del dominio Party resuelve la identidad única del titular
entre SAP ECC (SD/MM), SAP CRM, SuccessFactors y el portal web, con gobierno de referencia (RDM), matching auditable, stewardship con
juicio experto y cumplimiento embebido (Ley 1581/2012, Decreto 1377/2013, Ley 2300/2023, Res. CRC 7356/2024).

| Indicador | Valor |
|---|---|
| Parties golden | 900 |
| Parties fusionados automáticamente | 691 |
| Candidatos pendientes de revisión | 0 |
| Pares de matching (AUTO_MERGE / PROBABLE / POSSIBLE) | 691 / 3 / 1 |
| Vínculos de contacto elegibles / no elegibles | 3799 / 5762 |
| Filas de auditoría | 58685 |

**Trazabilidad al caso financiero.** (1) Golden record único por titular con survivorship por atributo y fuente ganadora visible;
(2) contactabilidad por contacto y finalidad con 12 precedencias, RNE y consentimientos multi-tipo → audiencias de campaña sin
consolidación manual; (3) cobranza solo sobre obligación vigente y con teléfonos de gestión trazados por origen y confirmación;
(4) ARCO con SLA en días hábiles y purga simulada sin borrado; (5) toda decisión humana justificada y auditada (regla dura §3.12).

**Marco de referencia.** DAMA-DMBOK2 cap. 10 y 11 (datos de referencia y maestros); ISO/IEC 27001:2022 A.5.34 y A.8.15;
ISO/IEC 42001:2023 cl. 6.1 y NIST AI RMF 1.0 (GOVERN) para la supervisión humana del matching; COBIT 2019 APO14 (gestión de datos).

**Siguiente paso.** Validar con las UES los campos Z ilustrativos, definir owners y stewards definitivos y planear el piloto con extractores reales.
