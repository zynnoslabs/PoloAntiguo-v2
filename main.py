"""
main.py — Polo Antiguo v2
Orquestador: busca → analiza → guarda → notifica.
Se puede llamar manualmente o desde APScheduler dentro de app.py.
"""
import logging
from db import init_db, guardar_listado
from buscador import buscar_todo
from analizador import analizar_todos
from notificador import enviar_resumen

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("main")

def ciclo_completo():
    log.info("=== Ciclo Polo Antiguo iniciado ===")
    init_db()

    # 1. Buscar
    listados = buscar_todo()
    if not listados:
        log.info("Sin listados nuevos este ciclo.")
        return []

    # 2. Analizar (todos, no solo relevantes)
    analizados = analizar_todos(listados, solo_relevantes=False)

    # 3. Guardar todos en DB
    for item in analizados:
        guardar_listado(item)

    # 4. Filtrar relevantes y notificar
    relevantes = [i for i in analizados if i.get("relevante")]
    if relevantes:
        enviar_resumen(relevantes)

    log.info(f"=== Ciclo terminado: {len(analizados)} analizados, {len(relevantes)} relevantes ===")
    return relevantes

if __name__ == "__main__":
    ciclo_completo()
