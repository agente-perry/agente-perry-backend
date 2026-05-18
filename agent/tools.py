import os
from neo4j import GraphDatabase
from neo4j.exceptions import CypherSyntaxError, ClientError
from neo4j.time import Date, DateTime, Duration, Time
from neo4j.graph import Node, Relationship

_driver = None

FORBIDDEN_KEYWORDS = {"CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP", "DETACH", "CALL db."}


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
    return _driver


def _serialize(value):
    if isinstance(value, (Date, DateTime, Time)):
        return value.iso_format()
    if isinstance(value, Duration):
        return str(value)
    if isinstance(value, Node):
        return {"_labels": list(value.labels), **{k: _serialize(v) for k, v in value.items()}}
    if isinstance(value, Relationship):
        return {"_type": value.type, **{k: _serialize(v) for k, v in value.items()}}
    if isinstance(value, list):
        return [_serialize(i) for i in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


def validate_read_only(cypher: str) -> None:
    upper = cypher.upper()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in upper:
            raise ValueError(f"Consulta rechazada: contiene operación prohibida '{kw}'")


def execute_cypher(cypher: str, params: dict | None = None) -> dict:
    validate_read_only(cypher)
    driver = get_driver()
    db = os.environ.get("NEO4J_DATABASE", "neo4j")
    try:
        with driver.session(database=db) as session:
            result = session.run(cypher, params or {})
            records = [{k: _serialize(v) for k, v in r.items()} for r in result]
            summary = result.consume()
            return {
                "success": True,
                "records": records,
                "count": len(records),
                "query_type": summary.query_type,
            }
    except (CypherSyntaxError, ClientError) as e:
        return {"success": False, "error": str(e), "records": []}
    except Exception as e:
        return {"success": False, "error": f"Error de conexión: {str(e)}", "records": []}


def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None
