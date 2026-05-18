NEO4J_SCHEMA = """
## ESQUEMA NEO4J — BASE DE DATOS ANTICORRUPCIÓN PERÚ

### NODOS Y PROPIEDADES EXACTAS

**(:Company)**
- ruc: string (PK, 11 dígitos o "hash_<md5>")
- name: string
- nombre_comercial: string
- tipo_contribuyente: string  ("SOCIEDAD ANONIMA", "PERSONA NATURAL CON NEGOCIO", etc.)
- estado: string  ("ACTIVO", "BAJA")
- condicion: string  ("HABIDO", "NO HABIDO")
- domicilio_fiscal: string
- fecha_inscripcion: date
- fecha_inicio_actividades: date
- ciiu_principal: string  (código CIIU)
- actividad_principal: string
- max_trabajadores: integer
- min_trabajadores: integer
- deuda_coactiva: boolean
- omisiones_tributarias: boolean
- tiene_actas_probatorias: boolean
- is_ruc_complete: boolean
- risk_score_v2: float
- total_won_pen: float  (suma total contratos ganados en PEN)
- total_contracts: integer
- diversity_clients: integer  (número de entidades públicas distintas)
- days_to_first_contract: integer

**(:PublicEntity)**
- ruc: string (PK)
- name: string
- region: string  ("LIMA", "CUSCO", "AREQUIPA", etc.)

**(:Contract)**
- external_id: string (PK)
- ocid: string
- tender_id: string
- award_id: string
- monto: float  (en PEN)
- fecha: date
- period_year: integer
- procedure_type: string  ("Adjudicacion Simplificada", "Concurso Público", "Licitacion Publica", "Contratacion Directa", etc.)
- region: string
- evidence_quote: string

**(:Tender)**
- tender_id: string (PK)
- ocid: string
- procedure_type: string
- fecha: date
- monto: float
- region: string

**(:Address)**
- address_hash: string (PK)
- domicilio_fiscal: string
- ubigeo: string
- tipo_via: string  ("AV.", "JR.", "CAL.")
- nombre_via: string
- numero: string
- tipo_zona: string
- is_generic: boolean

**(:Person)**
- doc_id: string (PK, DNI o CE)
- doc_type: string  ("DNI", "CE")
- name: string

**(:Dossier)**
- ocid: string (PK)
- entity_name: string
- sector: string  ("salud", "ambiente_mineria")
- procedure_code: string
- monto: float
- total_score: integer  (20–60)
- risk_level: string  ("BAJO", "MEDIO", "ALTO")
- total_flags: integer
- total_pages: integer
- coverage_pct: float
- generated_at: datetime

**(:RiskFlag)**
- flag_id: string (PK)
- flag_code: string  ("LOW_TRACEABILITY_OUTPUT", "OBSOLETE_PHYSICAL_FORMAT", etc.)
- flag_name: string
- severity: string  ("LOW", "MEDIUM", "HIGH")
- score_contribution: integer
- page_number: integer
- evidence_quote: string
- rule_id: string  ("TDR-R005", "TDR-R002", etc.)
- detection_method: string  ("rule", "ai")

**(:ProcedureSeace)**
- uuid: string (PK)
- nomenclatura: string
- numero: integer
- entidad: string
- descripcion: string
- cuantia: float
- fecha_hora: datetime
- completed_targets: list<string>
- linked_contract_ocid: string

### RELACIONES EXACTAS

- (Company)-[:WON {monto, fecha, procedure_type, region}]->(Contract)
- (Contract)-[:AWARDED_BY]->(PublicEntity)
- (Contract)-[:UNDER_TENDER]->(Tender)
- (Company)-[:LOCATED_AT]->(Address)
- (Company)-[:SAME_ADDRESS_AS {via_address_hash}]->(Company)
- (Company)-[:SAME_REPR_AS {via_person_doc_id}]->(Company)
- (Contract)-[:ANALYZED_BY]->(Dossier)
- (Dossier)-[:HAS_FLAG]->(RiskFlag)
- (Person)-[:REPRESENTS {cargo, fecha_desde}]->(Company)
- (ProcedureSeace)-[:EVENTUAL_CONTRACT]->(Contract)

### QUERIES EJEMPLO

# Empresas con más contratos en una región
MATCH (c:Company)-[w:WON]->(ct:Contract)-[:AWARDED_BY]->(e:PublicEntity {region: "LIMA"})
RETURN c.name, c.ruc, count(ct) AS contratos, sum(w.monto) AS total_pen
ORDER BY total_pen DESC LIMIT 10

# Empresas con cero trabajadores y más de S/1M en contratos
MATCH (c:Company)-[w:WON]->(ct:Contract)
WHERE c.max_trabajadores = 0
WITH c, sum(w.monto) AS total
WHERE total > 1000000
RETURN c.name, c.ruc, c.max_trabajadores, total
ORDER BY total DESC

# Empresas que comparten domicilio fiscal
MATCH (a:Company)-[:SAME_ADDRESS_AS]->(b:Company)
RETURN a.name, b.name, a.domicilio_fiscal LIMIT 20

# Empresas que comparten representante legal
MATCH (a:Company)-[:SAME_REPR_AS]->(b:Company)
MATCH (p:Person)-[:REPRESENTS]->(a)
MATCH (p)-[:REPRESENTS]->(b)
RETURN p.name, a.name, b.name LIMIT 20

# Contratos con TDRs analizados y nivel de riesgo alto
MATCH (ct:Contract)-[:ANALYZED_BY]->(d:Dossier {risk_level: "ALTO"})
MATCH (c:Company)-[:WON]->(ct)
RETURN c.name, ct.external_id, d.total_score, d.total_flags, ct.monto
ORDER BY d.total_score DESC

# Empresas con deuda coactiva que ganaron contratos
MATCH (c:Company {deuda_coactiva: true})-[w:WON]->(ct:Contract)
RETURN c.name, c.ruc, count(ct) AS contratos, sum(w.monto) AS total_pen
ORDER BY total_pen DESC LIMIT 20

# Licitaciones por tipo de procedimiento
MATCH (ct:Contract)
RETURN ct.procedure_type, count(*) AS cantidad, sum(ct.monto) AS total
ORDER BY cantidad DESC

# Persona que representa múltiples empresas
MATCH (p:Person)-[:REPRESENTS]->(c:Company)
WITH p, collect(c.name) AS empresas, count(c) AS total
WHERE total > 1
RETURN p.name, p.doc_id, total, empresas
ORDER BY total DESC

### REGLAS CRÍTICAS
- NUNCA inventes nombres de propiedades. Usa EXACTAMENTE los listados arriba.
- NUNCA inventes tipos de relaciones. Solo usa las listadas arriba.
- Todas las queries deben ser READ-ONLY (MATCH, RETURN, WITH, WHERE, ORDER BY, LIMIT). PROHIBIDO: CREATE, MERGE, SET, DELETE, REMOVE.
- Los montos están en PEN (soles peruanos).
- Para fechas usa: fecha >= date('2024-01-01')
- Para strings usa comparación insensible: toLower(c.name) CONTAINS toLower('busqueda')
- Limita siempre con LIMIT (máximo 100 por defecto).
"""
