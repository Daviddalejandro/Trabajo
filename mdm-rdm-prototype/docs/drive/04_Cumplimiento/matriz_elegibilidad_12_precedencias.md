# Matriz de elegibilidad de contacto (SPEC §10.3)

Orden de precedencia; el primer criterio que falla fija `reason_cd`.

| # | Criterio | reason_cd | Base legal |
|---|---|---|---|
| 1 | party_status = DECEASED | `DECEASED` | Ley 1581/2012 art. 4 lit. d (veracidad) |
| 2 | Titular menor de edad y finalidad COMMERCIAL | `MINOR` | Ley 1581/2012 art. 7; Decreto 1377/2013 art. 12 |
| 3 | Número en el RNE y finalidad con rne_applies | `RNE_EXCLUSION` | Ley 2300/2023 art. 5 |
| 4 | Vínculo SHARED/GUARDIAN, OWNER menor de edad, finalidad COMMERCIAL | `SHARED_CONTACT_RESTRICTED` | Ley 1581/2012 art. 7 |
| 5 | Vínculo REFERENCE y finalidad distinta de COLLECTIONS | `THIRD_PARTY_CONTACT` | Ley 1581/2012 art. 4 lit. b (finalidad) |
| 6 | Preferencia de contacto allowed=false para la finalidad | `CONTACT_PURPOSE_DENIED` | Ley 2300/2023 art. 3; Res. CRC 7356/2024 |
| 7 | Contacto no confirmado por el titular sin finalidad habilitada (WRONG_PERSON/INVALID nunca elegible) | `UNCONFIRMED_CONTACT / INVALID_CONTACT` | Ley 1581/2012 art. 4 lit. d |
| 8 | COLLECTIONS sin vínculo de servicio ACTIVE/SUSPENDED con collections_applies | `NO_ACTIVE_SERVICE` | Ley 2300/2023 art. 3 |
| 9 | Sin consentimiento GRANTED del tipo requerido por la finalidad | `NO_CONSENT / CONSENT_REVOKED` | Ley 1581/2012 art. 9; Decreto 1377/2013 art. 9 |
| 10 | Preferencia de canal allowed=false (sin preferencia de contacto) | `CHANNEL_DENIED` | Ley 2300/2023 art. 3 |
| 11 | Frecuencia excedida (NEVER en el prototipo) | `FREQUENCY_EXCEEDED` | Ley 2300/2023 art. 3; Res. CRC 7356/2024 |
| 12 | En otro caso | `ELIGIBLE` | — |
