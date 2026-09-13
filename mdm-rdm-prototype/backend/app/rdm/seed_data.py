"""Semilla del RDM (SPEC §6): 6 dominios, 43 catálogos (21 de negocio + 22 operativos),
valores canónicos, atributos EAV, 6 sistemas fuente, integraciones y homologaciones.

Formato de valor: (code, name) | (code, name, parent_code) | (code, name, parent_code, {eav}).
Solo datos de referencia; ningún dato personal.
"""

DOMAINS = [
    ("DEMOGRAPHICS", "Demografía e identidad"),
    ("GEOGRAPHY", "Geografía (DANE / ISO)"),
    ("GOVERNANCE", "Gobierno, cumplimiento y calidad"),
    ("CONTACT", "Contactabilidad"),
    ("MDM_OPS", "Operación del MDM"),
    ("BUSINESS", "Negocio (UES, roles, servicios, segmentos)"),
]

MDM_ENTITIES = [
    "PARTY", "PARTY_PERSON", "PARTY_ORG", "PARTY_ROLE", "PARTY_SEGMENT", "XREF_PARTY_SOURCE",
    "PARTY_IDENTIFIER", "PARTY_NAME",
    "PARTY_RELATIONSHIP", "PARTY_GROUP", "PARTY_GROUP_MEMBER", "PARTY_SERVICE_ENROLLMENT",
    "CONTACT_POINT", "PARTY_CONTACT_POINT", "PARTY_ADDRESS", "PARTY_CONTACT_PREF",
    "PARTY_CONTACT_ELIGIBILITY_CACHE",
    "MATCH_RULE", "PARTY_DQ_ISSUE", "PARTY_AUDIT_LOG", "PARTY_DATA_RETENTION",
    "PARTY_BUCKET", "BUCKET_CANDIDATE", "PARTY_MATCH", "MATCH_REVIEW_TASK", "PARTY_MERGE_HISTORY",
    "PARTY_SURVIVORSHIP",
    "PARTY_CONSENT", "DATA_SUBJECT_REQUEST",
]
assert len(MDM_ENTITIES) == 29

# catalog_code -> (domain, name, official_source, is_hierarchical, values)
CATALOGS: dict[str, tuple[str, str, str | None, bool, list]] = {
    # ------------------------------------------------------------ Tabla A · negocio (21)
    "CAT_GENDER": ("DEMOGRAPHICS", "Género", "Interno", False, [
        ("M", "Masculino"), ("F", "Femenino"),
    ]),
    "CAT_ID_TYPE": ("DEMOGRAPHICS", "Tipo de documento de identidad", "RNEC / DIAN / Migración Colombia", False, [
        ("CC", "Cédula de ciudadanía", None, {"validation_regex": r"^\d{6,10}$", "applies_to": "PERSON", "has_check_digit": "false"}),
        ("CE", "Cédula de extranjería", None, {"validation_regex": r"^\d{6,7}$", "applies_to": "PERSON", "has_check_digit": "false"}),
        ("TI", "Tarjeta de identidad", None, {"validation_regex": r"^\d{10,11}$", "applies_to": "PERSON", "has_check_digit": "false"}),
        ("NIT", "Número de identificación tributaria", None, {"validation_regex": r"^\d{9}$", "applies_to": "ORGANIZATION", "has_check_digit": "true"}),
        ("PAS", "Pasaporte", None, {"validation_regex": r"^[A-Z0-9]{6,12}$", "applies_to": "PERSON", "has_check_digit": "false"}),
        ("PPT", "Permiso por protección temporal", None, {"validation_regex": r"^\d{6,10}$", "applies_to": "PERSON", "has_check_digit": "false"}),
    ]),
    "CAT_NAME_TYPE": ("DEMOGRAPHICS", "Tipo de nombre", "Interno", False, [
        ("LEGAL", "Nombre legal"), ("SOCIAL", "Nombre social"), ("ALIAS", "Alias"),
        ("PREVIOUS", "Nombre anterior"), ("TRADE", "Nombre comercial"),
    ]),
    "CAT_VERIFICATION_SOURCE": ("GOVERNANCE", "Fuente de verificación de identidad", "Interno", False, [
        ("RNEC_API", "Registraduría Nacional (API)"), ("DIAN_API", "DIAN (API)"), ("MANUAL", "Verificación manual"),
        ("MIGR_COLOM", "Migración Colombia"), ("NOT_VERIFIED", "No verificado"),
    ]),
    "CAT_PARTY_ROLE": ("BUSINESS", "Rol del party", "Interno", False, [
        ("AFFILIATE", "Afiliado"), ("EMPLOYEE", "Empleado"), ("VENDOR", "Proveedor"),
        ("CUSTOMER", "Cliente"), ("DIGITAL_USER", "Usuario digital"), ("AFFILIATING_COMPANY", "Empresa afiliadora"),
    ]),
    # 12 sub-roles del diccionario maestro: 2 ilustrativos por rol principal
    "CAT_PARTY_SUB_ROLE": ("BUSINESS", "Sub-rol del party", "Interno", False, [
        ("AFFILIATE_WORKER", "Afiliado trabajador", None, {"parent_role": "AFFILIATE"}),
        ("AFFILIATE_PENSIONER", "Afiliado pensionado", None, {"parent_role": "AFFILIATE"}),
        ("EMPLOYEE_PERMANENT", "Empleado término indefinido", None, {"parent_role": "EMPLOYEE"}),
        ("EMPLOYEE_TEMPORARY", "Empleado temporal", None, {"parent_role": "EMPLOYEE"}),
        ("VENDOR_GOODS", "Proveedor de bienes", None, {"parent_role": "VENDOR"}),
        ("VENDOR_SERVICES", "Proveedor de servicios", None, {"parent_role": "VENDOR"}),
        ("CUSTOMER_PERSON", "Cliente persona natural", None, {"parent_role": "CUSTOMER"}),
        ("CUSTOMER_COMPANY", "Cliente persona jurídica", None, {"parent_role": "CUSTOMER"}),
        ("DIGITAL_REGISTERED", "Usuario registrado", None, {"parent_role": "DIGITAL_USER"}),
        ("DIGITAL_VERIFIED", "Usuario verificado", None, {"parent_role": "DIGITAL_USER"}),
        ("COMPANY_PRIVATE", "Empresa privada", None, {"parent_role": "AFFILIATING_COMPANY"}),
        ("COMPANY_PUBLIC", "Entidad pública", None, {"parent_role": "AFFILIATING_COMPANY"}),
    ]),
    "CAT_RELATIONSHIP_TYPE": ("DEMOGRAPHICS", "Tipo de relación entre parties (con dirección)", "Interno", False, [
        ("SPOUSE_OF", "Cónyuge de", None, {"from_party_type": "PERSON", "to_party_type": "PERSON", "inverse_code": "SPOUSE_OF"}),
        ("PARENT_OF", "Padre/madre de", None, {"from_party_type": "PERSON", "to_party_type": "PERSON", "inverse_code": "CHILD_OF"}),
        ("CHILD_OF", "Hijo/hija de", None, {"from_party_type": "PERSON", "to_party_type": "PERSON", "inverse_code": "PARENT_OF"}),
        ("GUARDIAN_OF", "Acudiente de", None, {"from_party_type": "PERSON", "to_party_type": "PERSON", "inverse_code": ""}),
        ("BENEFICIARY_OF", "Beneficiario de", None, {"from_party_type": "PERSON", "to_party_type": "PERSON", "inverse_code": ""}),
        ("LEGAL_REP_OF", "Representante legal de", None, {"from_party_type": "PERSON", "to_party_type": "ORGANIZATION", "inverse_code": ""}),
        ("EMPLOYEE_OF", "Empleado de", None, {"from_party_type": "PERSON", "to_party_type": "ORGANIZATION", "inverse_code": ""}),
        ("SHAREHOLDER_OF", "Accionista de", None, {"from_party_type": "ANY", "to_party_type": "ORGANIZATION", "inverse_code": ""}),
        ("SUBSIDIARY_OF", "Subsidiaria de", None, {"from_party_type": "ORGANIZATION", "to_party_type": "ORGANIZATION", "inverse_code": ""}),
        ("BRANCH_OF", "Sucursal de", None, {"from_party_type": "ORGANIZATION", "to_party_type": "ORGANIZATION", "inverse_code": ""}),
    ]),
    "CAT_CONSENT_STATUS": ("GOVERNANCE", "Estado de la autorización", "Ley 1581/2012", False, [
        ("GRANTED", "Otorgada"), ("DENIED", "Negada"), ("REVOKED", "Revocada"), ("EXPIRED", "Vencida"), ("PENDING", "Pendiente"),
    ]),
    "CAT_CONSENT_TYPE": ("GOVERNANCE", "Tipo de autorización (finalidad)", "Ley 1581/2012 art. 8; Ley 1266/2008 art. 6", False, [
        ("DATA_PROCESSING", "Tratamiento de datos personales (Ley 1581/2012 art. 8)"),
        ("COMMERCIAL", "Finalidad comercial y publicitaria"),
        ("FINANCIAL_HABEAS_DATA", "Habeas Data financiero (Ley 1266/2008 art. 6)"),
        ("CLINICAL_RECORDS", "Historia clínica, dato sensible (Ley 1581/2012 art. 6; Ley 23/1981 art. 34)"),
        ("CREDIT_BUREAU", "Reporte a centrales de riesgo (Ley 1266/2008)"),
    ]),
    "CAT_CONTACT_CHANNEL": ("CONTACT", "Canal de contacto", "Ley 2300/2023 art. 3", False, [
        ("EMAIL", "Correo electrónico"), ("PHONE", "Llamada telefónica"), ("SMS", "Mensaje de texto"),
        ("WHATSAPP", "WhatsApp"), ("PHYSICAL_MAIL", "Correo físico"),
    ]),
    "CAT_CONTACT_FREQUENCY": ("CONTACT", "Frecuencia de contacto", "Ley 2300/2023 art. 3", False, [
        ("ANY", "Sin restricción"), ("WEEKLY", "Semanal"), ("MONTHLY", "Mensual"), ("NEVER", "Nunca"),
    ]),
    "CAT_CONTACT_PURPOSE": ("CONTACT", "Finalidad del contacto", "Ley 2300/2023 arts. 3 y 5", False, [
        ("COLLECTIONS", "Cobranza", None, {"required_consent_type": "DATA_PROCESSING", "rne_applies": "false"}),
        ("BENEFITS", "Beneficios y servicios", None, {"required_consent_type": "DATA_PROCESSING", "rne_applies": "false"}),
        ("COMMERCIAL", "Comercial y publicitaria", None, {"required_consent_type": "COMMERCIAL", "rne_applies": "true"}),
    ]),
    "CAT_MERGE_TYPE": ("MDM_OPS", "Tipo de merge", "Interno", False, [
        ("AUTO", "Automático (score ≥ 85)"), ("STEWARD", "Decidido por steward"),
        ("OWNER_CONSENSUS", "Consenso de owners de fuente"), ("MANUAL_OVERRIDE", "Decisión de la Jefatura"),
    ]),
    "CAT_ARCO_REQUEST_TYPE": ("GOVERNANCE", "Tipo de solicitud ARCO", "Ley 1581/2012 arts. 14-15", False, [
        ("ACCESS", "Acceso / consulta", None, {"sla_business_days": "10"}),
        ("RECTIFICATION", "Rectificación", None, {"sla_business_days": "15"}),
        ("CANCELLATION", "Cancelación / supresión", None, {"sla_business_days": "15"}),
        ("OPPOSITION", "Oposición", None, {"sla_business_days": "15"}),
    ]),
    "CAT_REQUEST_STATUS": ("GOVERNANCE", "Estado de solicitud o tarea", "Interno", False, [
        ("RECEIVED", "Recibida"), ("IN_PROGRESS", "En trámite"), ("RESOLVED", "Resuelta"), ("REJECTED", "Rechazada"),
    ]),
    "CAT_DQ_CATEGORY": ("GOVERNANCE", "Categoría de calidad de datos", "DAMA-DMBOK2 Cap. 13", False, [
        ("COMPLETENESS", "Completitud"), ("VALIDITY", "Validez"), ("CONSISTENCY", "Consistencia"),
        ("UNIQUENESS", "Unicidad"), ("TIMELINESS", "Oportunidad"),
    ]),
    "CAT_MDM_ENTITY": ("MDM_OPS", "Entidad del MDM (auditoría genérica)", "Interno", False,
                       [(e, e.replace("_", " ").title()) for e in MDM_ENTITIES]),
    "CAT_GEOCODING_STATUS": ("GEOGRAPHY", "Estado de geocodificación", "Interno", False, [
        ("PENDING", "Pendiente"), ("GEOCODED", "Geocodificada"), ("FAILED", "Fallida"), ("NOT_APPLICABLE", "No aplica"),
    ]),
    "CAT_COUNTRY": ("GEOGRAPHY", "País (ISO 3166-1 alfa-3)", "ISO 3166 / DANE", False, [
        ("COL", "Colombia"), ("VEN", "Venezuela"), ("USA", "Estados Unidos"), ("ESP", "España"),
    ]),
    "CAT_GEO_DIVIPOLA": ("GEOGRAPHY", "División político-administrativa (DIVIPOLA)", "DANE", True, [
        ("11", "Bogotá D.C."),
        ("11001", "Bogotá D.C.", "11", {"locality_type": "CABECERA"}),
        ("05", "Antioquia"),
        ("05001", "Medellín", "05", {"locality_type": "CABECERA"}),
        ("25", "Cundinamarca"),
        ("25286", "Funza", "25", {"locality_type": "CABECERA"}),
        ("25754", "Soacha", "25", {"locality_type": "CABECERA"}),
        ("76", "Valle del Cauca"),
        ("76001", "Cali", "76", {"locality_type": "CABECERA"}),
    ]),
    "CAT_SEGMENT_TYPE": ("BUSINESS", "Segmentación (nivel 1 tipo, nivel 2 valor)", "Interno", True, [
        ("AFFILIATION", "Categoría de afiliación", None, {"authoritative_source": "SAP_CRM"}),
        ("A", "Categoría A", "AFFILIATION"), ("B", "Categoría B", "AFFILIATION"), ("C", "Categoría C", "AFFILIATION"),
        ("FINANCIAL_RISK", "Riesgo financiero", None, {"authoritative_source": "SAP_ECC_SD"}),
        ("LOW", "Bajo", "FINANCIAL_RISK"), ("MEDIUM", "Medio", "FINANCIAL_RISK"), ("HIGH", "Alto", "FINANCIAL_RISK"),
        ("COMMERCIAL", "Segmento comercial", None, {"authoritative_source": "WEB_PORTAL"}),
        ("BASIC", "Básico", "COMMERCIAL"), ("PREMIUM", "Premium", "COMMERCIAL"),
    ]),
    # ------------------------------------------------------------ Tabla B · operativos (22)
    "CAT_PARTY_TYPE": ("MDM_OPS", "Tipo de party", "Interno", False, [
        ("PERSON", "Persona natural"), ("ORGANIZATION", "Persona jurídica"),
    ]),
    "CAT_GOLDEN_STATUS": ("MDM_OPS", "Estado MDM del party", "Interno", False, [
        ("CANDIDATE", "Candidato"), ("GOLDEN", "Golden record"), ("MERGED", "Absorbido por merge"),
    ]),
    "CAT_PARTY_STATUS": ("BUSINESS", "Estado de negocio del party", "Interno", False, [
        ("ACTIVE", "Activo"), ("INACTIVE", "Inactivo"), ("DECEASED", "Fallecido"),
    ]),
    "CAT_MATCH_DECISION": ("MDM_OPS", "Decisión del motor de matching", "Interno", False, [
        ("AUTO_MERGE", "Merge automático (≥ 85)"), ("PROBABLE", "Probable (70-84)"),
        ("POSSIBLE", "Posible (50-69)"), ("NO_MATCH", "Sin coincidencia (< 50)"),
    ]),
    "CAT_STEWARD_DECISION": ("MDM_OPS", "Decisión humana de stewardship", "Interno", False, [
        ("MERGE", "Fusionar"), ("NO_MATCH", "No es la misma persona"), ("ESCALATE", "Escalar"),
    ]),
    "CAT_SEVERITY": ("GOVERNANCE", "Severidad de hallazgo", "Interno", False, [
        ("BLOCKING", "Bloqueante"), ("WARNING", "Advertencia"), ("INFO", "Informativo"),
    ]),
    "CAT_SURVIVORSHIP_STRATEGY": ("MDM_OPS", "Estrategia de survivorship", "Interno", False, [
        ("SOURCE_PRIORITY", "Prioridad de fuente"), ("MOST_RECENT", "Más reciente"),
        ("MOST_COMPLETE", "Más completo"), ("MOST_FREQUENT", "Más frecuente"), ("MANUAL_OVERRIDE", "Decisión manual"),
    ]),
    "CAT_AUDIT_ACTION": ("GOVERNANCE", "Acción de auditoría", "Ley 1581/2012 art. 17", False, [
        ("INSERT", "Inserción"), ("UPDATE", "Actualización"), ("MERGE", "Merge"), ("UNMERGE", "Unmerge"),
        ("REVIEW_DECISION", "Decisión de revisión"), ("ARCO_READ", "Lectura por solicitud ARCO"),
        ("ARCO_UPDATE", "Cambio por solicitud ARCO"), ("REHOMOLOGATE", "Rehomologación"),
        ("PURGE_MARK", "Marca de purga"), ("PURGE_SIMULATED", "Purga simulada"),
    ]),
    "CAT_ELIGIBILITY_REASON": ("CONTACT", "Razón de elegibilidad de contacto", "Ley 2300/2023; Ley 1581/2012", False, [
        ("ELIGIBLE", "Elegible"), ("DECEASED", "Titular fallecido"), ("MINOR", "Titular menor de edad"),
        ("RNE_EXCLUSION", "Número en el Registro de Números Excluidos"),
        ("THIRD_PARTY_CONTACT", "Medio de un tercero"), ("CONTACT_PURPOSE_DENIED", "Finalidad denegada para el contacto"),
        ("UNCONFIRMED_CONTACT", "Contacto no confirmado"), ("NO_ACTIVE_SERVICE", "Sin obligación vigente"),
        ("NO_CONSENT", "Sin autorización"), ("CONSENT_REVOKED", "Autorización revocada o negada"),
        ("CHANNEL_DENIED", "Canal denegado"), ("FREQUENCY_EXCEEDED", "Frecuencia excedida"),
        ("SHARED_CONTACT_RESTRICTED", "Contacto compartido restringido"), ("NO_CONTACT_POINT", "Sin punto de contacto"),
    ]),
    "CAT_PREF_ORIGIN": ("CONTACT", "Origen de preferencia o vínculo de contacto", "Interno", False, [
        ("TITULAR", "Declarado por el titular"), ("LEGAL_REP", "Declarado por representante legal"),
        ("INTERNAL_POLICY", "Política interna"), ("COLLECTIONS_MANAGEMENT", "Gestión de cobranza"),
        ("THIRD_PARTY_REFERENCE", "Referencia de tercero"),
    ]),
    "CAT_CONTACT_USAGE_ROLE": ("CONTACT", "Rol de uso del contacto", "Interno", False, [
        ("OWNER", "Titular del medio"), ("SHARED", "Compartido"), ("GUARDIAN", "Acudiente"), ("REFERENCE", "Referencia de tercero"),
    ]),
    "CAT_CONTACT_CONFIRMATION": ("CONTACT", "Confirmación del vínculo de contacto", "Interno", False, [
        ("CONFIRMED_BY_TITULAR", "Confirmado por el titular"), ("CONFIRMED_BY_CONTACT", "Confirmado por el contacto"),
        ("UNCONFIRMED", "No confirmado"), ("WRONG_PERSON", "Persona equivocada"), ("INVALID", "Inválido"),
    ]),
    "CAT_BLOCKING_STRATEGY": ("MDM_OPS", "Estrategia de blocking", "Interno", False, [
        ("DOC_HASH", "Hash de documento"), ("EMAIL_HASH", "Hash de email"), ("PHONE_HASH", "Hash de teléfono"),
        ("SURNAME_SOUNDEX", "Soundex del primer apellido"), ("NIT_HASH", "Hash de NIT"), ("LEGAL_NAME_TOKENS", "Tokens de razón social"),
    ]),
    "CAT_GROUP_TYPE": ("DEMOGRAPHICS", "Tipo de grupo", "Interno", False, [
        ("FAMILY", "Grupo familiar"), ("CORPORATE_GROUP", "Grupo empresarial"),
    ]),
    "CAT_GROUP_MEMBER_ROLE": ("DEMOGRAPHICS", "Rol en el grupo", "Interno", False, [
        ("ANCHOR", "Ancla"), ("MEMBER", "Miembro"), ("BENEFICIARY", "Beneficiario"),
    ]),
    "CAT_ORG_TYPE": ("BUSINESS", "Tipo de organización", "Cámara de Comercio", False, [
        ("SAS", "Sociedad por acciones simplificada"), ("LTDA", "Sociedad limitada"),
        ("SA", "Sociedad anónima"), ("ESAL", "Entidad sin ánimo de lucro"),
    ]),
    "CAT_BUSINESS_UNIT": ("BUSINESS", "Unidad estratégica de servicio (UES)", "Interno", False, [
        ("SUBSIDIO", "Subsidio familiar"), ("SALUD", "Salud"), ("EDUCACION", "Educación"), ("VIVIENDA", "Vivienda"),
        ("CREDITO", "Crédito social"), ("RECREACION", "Recreación y deportes"),
        ("HOTELERIA_TURISMO", "Hotelería y turismo"), ("MERCADEO", "Mercadeo social"),
    ]),
    "CAT_SERVICE_KIND": ("BUSINESS", "Tipo de relación del servicio", "Interno", False, [
        ("PERSISTENT", "Relación sostenida en el tiempo (genera vínculo)"),
        ("TRANSACTIONAL", "Consumo puntual (solo referencia)"),
    ]),
    "CAT_SERVICE": ("BUSINESS", "Servicio por UES (nivel 1 UES, nivel 2 servicio)", "Interno", True, [
        ("SUBSIDIO", "Subsidio familiar"), ("SALUD", "Salud"), ("EDUCACION", "Educación"), ("VIVIENDA", "Vivienda"),
        ("CREDITO", "Crédito social"), ("RECREACION", "Recreación y deportes"),
        ("HOTELERIA_TURISMO", "Hotelería y turismo"), ("MERCADEO", "Mercadeo social"),
        ("CUOTA_MONETARIA", "Cuota monetaria", "SUBSIDIO", {"service_kind": "PERSISTENT", "collections_applies": "false"}),
        ("SALUD_EPS", "Plan de beneficios EPS", "SALUD", {"service_kind": "PERSISTENT", "collections_applies": "false"}),
        ("SALUD_PLAN_COMPLEMENTARIO", "Plan complementario de salud", "SALUD", {"service_kind": "PERSISTENT", "collections_applies": "true"}),
        ("COLEGIO_MATRICULA", "Matrícula en colegio", "EDUCACION", {"service_kind": "PERSISTENT", "collections_applies": "true"}),
        ("SUBSIDIO_VIVIENDA", "Subsidio de vivienda", "VIVIENDA", {"service_kind": "PERSISTENT", "collections_applies": "false"}),
        ("CREDITO_SOCIAL", "Crédito social", "CREDITO", {"service_kind": "PERSISTENT", "collections_applies": "true"}),
        ("TARJETA_CREDITO", "Tarjeta de crédito", "CREDITO", {"service_kind": "PERSISTENT", "collections_applies": "true"}),
        ("CLUB_SOCIO", "Socio de club", "RECREACION", {"service_kind": "PERSISTENT", "collections_applies": "true"}),
        ("PISCILAGO", "Piscilago", "RECREACION", {"service_kind": "TRANSACTIONAL", "collections_applies": "false"}),
        ("HOTEL", "Hotel", "HOTELERIA_TURISMO", {"service_kind": "TRANSACTIONAL", "collections_applies": "false"}),
        ("SUPERMERCADO", "Supermercado", "MERCADEO", {"service_kind": "TRANSACTIONAL", "collections_applies": "false"}),
        ("DROGUERIA", "Droguería", "MERCADEO", {"service_kind": "TRANSACTIONAL", "collections_applies": "false"}),
    ]),
    "CAT_ENROLLMENT_STATUS": ("BUSINESS", "Estado del vínculo de servicio", "Interno", False, [
        ("ACTIVE", "Activo"), ("SUSPENDED", "Suspendido"), ("CLOSED", "Cerrado"),
    ]),
    "CAT_RETENTION_RULE": ("GOVERNANCE", "Regla de retención", "Política corporativa de retención", False, [
        ("AFFILIATE_5Y", "Afiliados: 5 años desde fin de afiliación", None, {"years": "5", "trigger": "AFFILIATION_END"}),
        ("HR_5Y_POST_EXIT", "RR. HH.: 5 años post-egreso", None, {"years": "5", "trigger": "EMPLOYMENT_END"}),
        ("VENDOR_7Y", "Proveedores: 7 años", None, {"years": "7", "trigger": "VENDOR_END"}),
        ("FINANCIAL_10Y", "Financiero: 10 años desde cierre del último vínculo de CREDITO", None, {"years": "10", "trigger": "ENROLLMENT_CLOSED:CREDITO"}),
        ("HEALTH_20Y", "Salud: 20 años desde cierre del último vínculo de SALUD (Res. 1995/1999 art. 15)", None, {"years": "20", "trigger": "ENROLLMENT_CLOSED:SALUD"}),
        ("LEGAL_HOLD", "Retención legal", None, {"years": "0", "trigger": "HOLD"}),
        ("PURGE_ELIGIBLE", "Elegible para purga", None, {"years": "0", "trigger": "ARCO_CANCELLATION"}),
    ]),
    "CAT_CIIU": ("BUSINESS", "Actividad económica CIIU rev. 4 A.C. (ilustrativo)", "DIAN", False, [
        ("4711", "Comercio al por menor en establecimientos no especializados (alimentos)"),
        ("8610", "Actividades de hospitales y clínicas"),
        ("6492", "Actividades financieras de fondos de empleados y sector solidario"),
        ("5511", "Alojamiento en hoteles"),
        ("8521", "Educación básica primaria"),
    ]),
}
assert len(CATALOGS) == 43, len(CATALOGS)

# code, name, is_prototype_active, data_owner, data_steward
SOURCE_SYSTEMS = [
    ("SAP_ECC_HCM", "SAP ECC 6.0 · HCM (maestro de personal)", False, "Gerencia de Gestión Humana", "steward.hcm"),
    ("SAP_ECC_SD", "SAP ECC 6.0 · SD (clientes KNA1)", True, "Gerencia Comercial", "steward.sd"),
    ("SAP_ECC_MM", "SAP ECC 6.0 · MM (proveedores LFA1)", True, "Gerencia de Abastecimiento", "steward.mm"),
    ("SAP_CRM", "SAP CRM · Business Partner (BUT000/BUT020/ADRC)", True, "Gerencia de Afiliaciones", "steward.crm"),
    ("SF_EC", "SuccessFactors Employee Central", True, "Gerencia de Gestión Humana", "steward.sfec"),
    ("WEB_PORTAL", "Portal web · usuarios digitales", True, "Gerencia de Canales Digitales", "steward.portal"),
]

# (system, source_field, catalog, source_value, canonical_code)
# Regla dura §3.4: sistema fuente exacto; no existe "SAP_ECC".
MAPPINGS = [
    ("SAP_ECC_HCM", "SEXKZ", "CAT_GENDER", "1", "M"),
    ("SAP_ECC_HCM", "SEXKZ", "CAT_GENDER", "2", "F"),
    ("SAP_CRM", "GESCHL", "CAT_GENDER", "1", "M"),
    ("SAP_CRM", "GESCHL", "CAT_GENDER", "2", "F"),
    ("SAP_CRM", "RLTYP", "CAT_PARTY_ROLE", "ZAFI", "AFFILIATE"),
    ("SAP_CRM", "RLTYP", "CAT_PARTY_ROLE", "ZEMP", "AFFILIATING_COMPANY"),
    ("SAP_CRM", "RLTYP", "CAT_PARTY_ROLE", "ZBEN", "AFFILIATE"),   # beneficiario: afiliado por grupo familiar
    ("SAP_ECC_SD", "LAND1", "CAT_COUNTRY", "CO", "COL"),
    ("SAP_ECC_SD", "REGIO", "CAT_GEO_DIVIPOLA", "ANT", "05"),
    ("SAP_ECC_MM", "LAND1", "CAT_COUNTRY", "CO", "COL"),
    ("SAP_ECC_MM", "REGIO", "CAT_GEO_DIVIPOLA", "ANT", "05"),
    ("SF_EC", "gender", "CAT_GENDER", "M", "M"),
    ("SF_EC", "gender", "CAT_GENDER", "F", "F"),
    ("SF_EC", "employmentStatus", "CAT_PARTY_STATUS", "T", "INACTIVE"),
    ("WEB_PORTAL", "tipo_doc", "CAT_ID_TYPE", "cedula", "CC"),
    ("WEB_PORTAL", "categoria", "CAT_SEGMENT_TYPE", "A", "A"),
    ("WEB_PORTAL", "categoria", "CAT_SEGMENT_TYPE", "B", "B"),
    ("WEB_PORTAL", "categoria", "CAT_SEGMENT_TYPE", "C", "C"),
    ("SAP_ECC_SD", "KTOKD", "CAT_SERVICE", "ZCRE", "CREDITO_SOCIAL"),
    ("SAP_ECC_SD", "KTOKD", "CAT_SERVICE", "ZSAL", "SALUD_EPS"),
    ("SAP_ECC_SD", "LOEVM", "CAT_ENROLLMENT_STATUS", "X", "CLOSED"),
    ("SAP_CRM", "RLTYP", "CAT_SERVICE", "ZSUB", "CUOTA_MONETARIA"),
    ("SAP_CRM", "ZZ_ORIGEN_TEL", "CAT_PREF_ORIGIN", "TIT", "TITULAR"),
    ("SAP_CRM", "ZZ_ORIGEN_TEL", "CAT_PREF_ORIGIN", "COB", "COLLECTIONS_MANAGEMENT"),
    ("SAP_CRM", "ZZ_ORIGEN_TEL", "CAT_PREF_ORIGIN", "REF", "THIRD_PARTY_REFERENCE"),
    # ---- F2 · homologaciones requeridas por las estructuras fuente del pipeline (§7.1)
    # SD: riesgo de crédito (CTLPC) → segmento FINANCIAL_RISK; servicios transaccionales; estado de contrato
    ("SAP_ECC_SD", "CTLPC", "CAT_SEGMENT_TYPE", "001", "LOW"),
    ("SAP_ECC_SD", "CTLPC", "CAT_SEGMENT_TYPE", "002", "MEDIUM"),
    ("SAP_ECC_SD", "CTLPC", "CAT_SEGMENT_TYPE", "003", "HIGH"),
    ("SAP_ECC_SD", "KTOKD", "CAT_SERVICE", "ZHOT", "HOTEL"),
    ("SAP_ECC_SD", "KTOKD", "CAT_SERVICE", "ZSUP", "SUPERMERCADO"),
    ("SAP_ECC_SD", "KTOKD", "CAT_SERVICE", "ZDRO", "DROGUERIA"),
    ("SAP_ECC_SD", "KTOKD", "CAT_SERVICE", "ZPIS", "PISCILAGO"),
    ("SAP_ECC_SD", "ZZ_ESTADO_CONTRATO", "CAT_ENROLLMENT_STATUS", "A", "ACTIVE"),
    ("SAP_ECC_SD", "ZZ_ESTADO_CONTRATO", "CAT_ENROLLMENT_STATUS", "S", "SUSPENDED"),
    ("SAP_ECC_SD", "ZZ_ESTADO_CONTRATO", "CAT_ENROLLMENT_STATUS", "C", "CLOSED"),
    # MM: sector (BRSCH) → CIIU; tipo de sociedad
    ("SAP_ECC_MM", "BRSCH", "CAT_CIIU", "G471", "4711"),
    ("SAP_ECC_MM", "BRSCH", "CAT_CIIU", "Q861", "8610"),
    ("SAP_ECC_MM", "BRSCH", "CAT_CIIU", "K649", "6492"),
    ("SAP_ECC_MM", "BRSCH", "CAT_CIIU", "I551", "5511"),
    ("SAP_ECC_MM", "BRSCH", "CAT_CIIU", "P852", "8521"),
    ("SAP_ECC_MM", "ZZ_TIPO_SOC", "CAT_ORG_TYPE", "SAS", "SAS"),
    ("SAP_ECC_MM", "ZZ_TIPO_SOC", "CAT_ORG_TYPE", "LTDA", "LTDA"),
    ("SAP_ECC_MM", "ZZ_TIPO_SOC", "CAT_ORG_TYPE", "SA", "SA"),
    ("SAP_ECC_MM", "ZZ_TIPO_SOC", "CAT_ORG_TYPE", "ESAL", "ESAL"),
    # CRM: tipo de documento (BUT0ID), relaciones (BUT050), categoría, fallecimiento, estado de afiliación,
    # uso y confirmación del teléfono, tipo de organización
    ("SAP_CRM", "IDTYPE", "CAT_ID_TYPE", "ZCC", "CC"),
    ("SAP_CRM", "IDTYPE", "CAT_ID_TYPE", "ZCE", "CE"),
    ("SAP_CRM", "IDTYPE", "CAT_ID_TYPE", "ZTI", "TI"),
    ("SAP_CRM", "IDTYPE", "CAT_ID_TYPE", "ZNIT", "NIT"),
    ("SAP_CRM", "IDTYPE", "CAT_ID_TYPE", "ZPAS", "PAS"),
    ("SAP_CRM", "IDTYPE", "CAT_ID_TYPE", "ZPPT", "PPT"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZSPO", "SPOUSE_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZPAR", "PARENT_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZCHI", "CHILD_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZGUA", "GUARDIAN_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZBEN", "BENEFICIARY_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZREP", "LEGAL_REP_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZEMP", "EMPLOYEE_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZSHA", "SHAREHOLDER_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZSUB", "SUBSIDIARY_OF"),
    ("SAP_CRM", "RELTYP", "CAT_RELATIONSHIP_TYPE", "ZBRA", "BRANCH_OF"),
    ("SAP_CRM", "ZZ_CATEGORIA", "CAT_SEGMENT_TYPE", "A", "A"),
    ("SAP_CRM", "ZZ_CATEGORIA", "CAT_SEGMENT_TYPE", "B", "B"),
    ("SAP_CRM", "ZZ_CATEGORIA", "CAT_SEGMENT_TYPE", "C", "C"),
    ("SAP_CRM", "ZZ_FALLECIDO", "CAT_PARTY_STATUS", "X", "DECEASED"),
    ("SAP_CRM", "ZZ_ESTADO_AFIL", "CAT_ENROLLMENT_STATUS", "A", "ACTIVE"),
    ("SAP_CRM", "ZZ_ESTADO_AFIL", "CAT_ENROLLMENT_STATUS", "S", "SUSPENDED"),
    ("SAP_CRM", "ZZ_ESTADO_AFIL", "CAT_ENROLLMENT_STATUS", "C", "CLOSED"),
    ("SAP_CRM", "ZZ_USO_TEL", "CAT_CONTACT_USAGE_ROLE", "OWN", "OWNER"),
    ("SAP_CRM", "ZZ_USO_TEL", "CAT_CONTACT_USAGE_ROLE", "SHR", "SHARED"),
    ("SAP_CRM", "ZZ_USO_TEL", "CAT_CONTACT_USAGE_ROLE", "GUA", "GUARDIAN"),
    ("SAP_CRM", "ZZ_USO_TEL", "CAT_CONTACT_USAGE_ROLE", "REF", "REFERENCE"),
    ("SAP_CRM", "ZZ_CONF_TEL", "CAT_CONTACT_CONFIRMATION", "TIT", "CONFIRMED_BY_TITULAR"),
    ("SAP_CRM", "ZZ_CONF_TEL", "CAT_CONTACT_CONFIRMATION", "CON", "CONFIRMED_BY_CONTACT"),
    ("SAP_CRM", "ZZ_CONF_TEL", "CAT_CONTACT_CONFIRMATION", "UNC", "UNCONFIRMED"),
    ("SAP_CRM", "ZZ_CONF_TEL", "CAT_CONTACT_CONFIRMATION", "WRG", "WRONG_PERSON"),
    ("SAP_CRM", "ZZ_CONF_TEL", "CAT_CONTACT_CONFIRMATION", "INV", "INVALID"),
    ("SAP_CRM", "ZZ_TIPO_ORG", "CAT_ORG_TYPE", "SAS", "SAS"),
    ("SAP_CRM", "ZZ_TIPO_ORG", "CAT_ORG_TYPE", "LTDA", "LTDA"),
    ("SAP_CRM", "ZZ_TIPO_ORG", "CAT_ORG_TYPE", "SA", "SA"),
    ("SAP_CRM", "ZZ_TIPO_ORG", "CAT_ORG_TYPE", "ESAL", "ESAL"),
    # SF_EC: tipo de documento, motivo de terminación, división → UES
    ("SF_EC", "nationalIdType", "CAT_ID_TYPE", "CC", "CC"),
    ("SF_EC", "nationalIdType", "CAT_ID_TYPE", "CE", "CE"),
    ("SF_EC", "nationalIdType", "CAT_ID_TYPE", "PAS", "PAS"),
    ("SF_EC", "nationalIdType", "CAT_ID_TYPE", "PPT", "PPT"),
    ("SF_EC", "terminationReason", "CAT_PARTY_STATUS", "DEATH", "DECEASED"),
    ("SF_EC", "division", "CAT_BUSINESS_UNIT", "SUB", "SUBSIDIO"),
    ("SF_EC", "division", "CAT_BUSINESS_UNIT", "SAL", "SALUD"),
    ("SF_EC", "division", "CAT_BUSINESS_UNIT", "EDU", "EDUCACION"),
    ("SF_EC", "division", "CAT_BUSINESS_UNIT", "VIV", "VIVIENDA"),
    ("SF_EC", "division", "CAT_BUSINESS_UNIT", "CRE", "CREDITO"),
    ("SF_EC", "division", "CAT_BUSINESS_UNIT", "REC", "RECREACION"),
    ("SF_EC", "division", "CAT_BUSINESS_UNIT", "HOT", "HOTELERIA_TURISMO"),
    ("SF_EC", "division", "CAT_BUSINESS_UNIT", "MER", "MERCADEO"),
    # Portal: tipo de documento, género, segmento comercial
    ("SAP_ECC_SD", "REGIO", "CAT_GEO_DIVIPOLA", "BOG", "11"),
    ("SAP_ECC_SD", "REGIO", "CAT_GEO_DIVIPOLA", "CUN", "25"),
    ("SAP_ECC_SD", "REGIO", "CAT_GEO_DIVIPOLA", "VAL", "76"),
    ("SAP_ECC_MM", "REGIO", "CAT_GEO_DIVIPOLA", "BOG", "11"),
    ("SAP_ECC_MM", "REGIO", "CAT_GEO_DIVIPOLA", "CUN", "25"),
    ("SAP_ECC_MM", "REGIO", "CAT_GEO_DIVIPOLA", "VAL", "76"),
    ("WEB_PORTAL", "tipo_doc", "CAT_ID_TYPE", "tarjeta_identidad", "TI"),
    ("WEB_PORTAL", "tipo_doc", "CAT_ID_TYPE", "pasaporte", "PAS"),
    ("WEB_PORTAL", "tipo_doc", "CAT_ID_TYPE", "cedula_extranjeria", "CE"),
    ("WEB_PORTAL", "tipo_doc", "CAT_ID_TYPE", "ppt", "PPT"),
    ("WEB_PORTAL", "genero", "CAT_GENDER", "M", "M"),
    ("WEB_PORTAL", "genero", "CAT_GENDER", "F", "F"),
    ("WEB_PORTAL", "segmento_comercial", "CAT_SEGMENT_TYPE", "basico", "BASIC"),
    ("WEB_PORTAL", "segmento_comercial", "CAT_SEGMENT_TYPE", "premium", "PREMIUM"),
]
