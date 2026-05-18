from __future__ import annotations

import json
import os
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END

from .schema import NEO4J_SCHEMA
from .tools import execute_cypher

MAX_RETRIES = 3
RESULT_PREVIEW_LIMIT = 20


class AgentState(TypedDict):
    query: str
    history: list[dict]   # [{role: "user"|"assistant", content: str}]
    cypher: str
    error: str
    raw_results: list[dict]
    narrative: str
    retries: int
    success: bool


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="anthropic/claude-opus-4.6",
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
        max_tokens=2048,
        default_headers={
            "HTTP-Referer": "https://agente-perry.app",
            "X-Title": "Agente Perry",
        },
    )


def _history_messages(history: list[dict]) -> list:
    msgs = []
    for h in history:
        if h["role"] == "user":
            msgs.append(HumanMessage(content=h["content"]))
        else:
            msgs.append(AIMessage(content=h["content"]))
    return msgs


CYPHER_SYSTEM = f"""Eres un experto en Neo4j Cypher especializado en datos anticorrupción de Perú.
Tu única función es traducir preguntas en lenguaje natural a consultas Cypher READ-ONLY válidas.

{NEO4J_SCHEMA}

INSTRUCCIONES:
1. Responde SOLO con la consulta Cypher. Sin explicaciones, sin bloques de código markdown, sin texto adicional.
2. Usa EXACTAMENTE los nombres de propiedades y relaciones del esquema. NO inventes nombres.
3. Solo READ-ONLY: MATCH, RETURN, WITH, WHERE, ORDER BY, LIMIT, OPTIONAL MATCH, COLLECT, COUNT.
4. Siempre incluye LIMIT (máximo 50 si no se especifica).
5. Para búsquedas por nombre: usa toLower() CONTAINS toLower().
6. Los montos están en soles peruanos (PEN).
7. Si hay historial de conversación, úsalo para entender referencias como "esa empresa", "lo mismo pero para Lima", "¿y ella?".
"""

INTERPRET_SYSTEM = """Eres Perry, un analista anticorrupción de Perú experto en datos de contrataciones públicas.
Tu función es explicar resultados de consultas Neo4j en lenguaje natural claro y directo en español.

INSTRUCCIONES:
1. Responde en español, tono periodístico-investigativo.
2. Usa markdown: headers ##, negritas **, listas con -, tablas si hay muchas filas.
3. Destaca patrones sospechosos o anomalías si los hay.
4. Menciona montos en soles (S/) con formato legible (S/ 1.2M, S/ 450K).
5. Si hay pocas filas, resúmelas. Si hay muchas, describe el patrón general.
6. Máximo 3-4 secciones. Directo al punto.
7. Si no hay resultados, explica qué significa eso.
8. Si hay historial, considera el contexto previo para enriquecer el análisis.
"""


def generate_cypher(state: AgentState) -> AgentState:
    history = state.get("history", [])
    messages = [SystemMessage(content=CYPHER_SYSTEM)]

    # Inject prior conversation as context
    if history:
        messages.extend(_history_messages(history))

    if state.get("error") and state.get("retries", 0) > 0:
        messages.append(HumanMessage(
            content=f"Pregunta: {state['query']}\n\n"
                    f"Cypher anterior con error:\n{state['cypher']}\n\n"
                    f"Error Neo4j: {state['error']}\n\n"
                    f"Corrige el Cypher. Responde SOLO con el Cypher corregido."
        ))
    else:
        messages.append(HumanMessage(content=state["query"]))

    llm = _llm()
    response = llm.invoke(messages)
    cypher = response.content.strip()
    cypher = cypher.removeprefix("```cypher").removeprefix("```").removesuffix("```").strip()

    return {**state, "cypher": cypher, "error": ""}


def execute_node(state: AgentState) -> AgentState:
    result = execute_cypher(state["cypher"])
    if result["success"]:
        return {**state, "raw_results": result["records"], "error": "", "success": True}
    return {
        **state,
        "raw_results": [],
        "error": result["error"],
        "retries": state.get("retries", 0) + 1,
        "success": False,
    }


def interpret_results(state: AgentState) -> AgentState:
    preview = state["raw_results"][:RESULT_PREVIEW_LIMIT]
    results_str = json.dumps(preview, ensure_ascii=False, indent=2, default=str)
    history = state.get("history", [])

    messages = [SystemMessage(content=INTERPRET_SYSTEM)]
    if history:
        messages.extend(_history_messages(history))

    messages.append(HumanMessage(
        content=f"Pregunta del usuario: {state['query']}\n\n"
                f"Cypher ejecutado:\n{state['cypher']}\n\n"
                f"Resultados ({len(state['raw_results'])} filas, mostrando primeras {len(preview)}):\n"
                f"{results_str}"
    ))

    llm = _llm()
    response = llm.invoke(messages)
    return {**state, "narrative": response.content.strip()}


def should_retry(state: AgentState) -> str:
    if not state.get("success") and state.get("retries", 0) < MAX_RETRIES:
        return "retry"
    if not state.get("success"):
        return "fail"
    return "interpret"


def fail_node(state: AgentState) -> AgentState:
    return {
        **state,
        "narrative": f"No pude ejecutar la consulta después de {MAX_RETRIES} intentos. "
                     f"Último error: {state.get('error', 'desconocido')}",
        "success": False,
    }


def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("generate_cypher", generate_cypher)
    workflow.add_node("execute", execute_node)
    workflow.add_node("interpret", interpret_results)
    workflow.add_node("fail", fail_node)
    workflow.set_entry_point("generate_cypher")
    workflow.add_edge("generate_cypher", "execute")
    workflow.add_conditional_edges("execute", should_retry, {
        "retry": "generate_cypher", "interpret": "interpret", "fail": "fail",
    })
    workflow.add_edge("interpret", END)
    workflow.add_edge("fail", END)
    return workflow.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_query(query: str, history: list[dict] | None = None) -> dict:
    graph = get_graph()
    initial_state: AgentState = {
        "query": query,
        "history": history or [],
        "cypher": "",
        "error": "",
        "raw_results": [],
        "narrative": "",
        "retries": 0,
        "success": False,
    }
    final_state = graph.invoke(initial_state)
    return {
        "query": final_state["query"],
        "cypher": final_state["cypher"],
        "results": final_state["raw_results"],
        "narrative": final_state["narrative"],
        "success": final_state["success"],
        "retries": final_state.get("retries", 0),
    }
