"""
analizador.py — Polo Antiguo
Groq recibe SOLO el JSON pre-fetcheado (≈300 tokens/item).
NUNCA navega internet. Clasifica relevancia y genera mensaje WA.
"""

import os, json, logging
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("analizador")

client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

# ─── Detección automática de modelo disponible ────────────────────────────────
### CAMBIO AQUÍ ### probe real con json_object — solo pasa modelos que funcionan de verdad

_MODELO_CACHE = None

_PREFERENCIA_MODELOS = [
    "gemma2-9b-it",            # Google Gemma 2 — suele estar activo en free tier
    "llama3-8b-8192",          # Meta Llama 3 8B
    "llama-3.2-3b-preview",    # Meta Llama 3.2 3B
    "mixtral-8x7b-32768",      # Mixtral — muy estable
    "qwen-qwq-32b",            # Qwen reasoning
    "qwen/qwen3.8-27b",        # Qwen alternativo
    "openai/gpt-oss-20b",      # OpenAI on Groq
    "llama-3.3-70b-versatile", # Llama grande (puede estar activo)
    "llama3-70b-8192",         # Llama 70B viejo
]

_PROBE_JSON = '{"ok":true}'   # respuesta mínima válida para test de JSON mode

def _detectar_modelo() -> str:
    """
    Sondea cada modelo con una llamada real en JSON mode.
    Solo acepta el modelo si devuelve JSON sin error.
    Se ejecuta una vez al arrancar; el resultado queda en caché.
    """
    global _MODELO_CACHE
    if _MODELO_CACHE:
        return _MODELO_CACHE

    # Override manual via env var (para Render)
    override = os.environ.get("GROQ_MODEL", "")
    if override:
        _MODELO_CACHE = override
        log.info(f"Modelo Groq (env override): {override}")
        return override

    for m in _PREFERENCIA_MODELOS:
        try:
            client.chat.completions.create(
                model=m,
                messages=[{"role": "user", "content": 'Responde exactamente: {"ok":true}'}],
                max_tokens=50,
                temperature=0,
                response_format={"type": "json_object"},  ### CAMBIO AQUÍ ### probe con JSON mode
            )
            _MODELO_CACHE = m
            log.info(f"Modelo Groq activo: {m}")
            return m
        except Exception as e:
            err = str(e)
            skip_keywords = ["model_not_found", "404", "decommissioned", "not found",
                             "does not exist", "json_validate_failed"]
            if any(k in err.lower() for k in skip_keywords):
                log.warning(f"Modelo no disponible: {m} — probando siguiente...")
                continue
            # Error distinto (rate limit, timeout) → igual usar este modelo
            _MODELO_CACHE = m
            log.warning(f"Modelo Groq (error no-fatal): {m} — {err[:80]}")
            return m

    log.error("¡Ningún modelo Groq disponible! Configurá GROQ_MODEL en Render env vars.")
    _MODELO_CACHE = _PREFERENCIA_MODELOS[0]
    return _MODELO_CACHE

# ─────────────────────────────────────────────────────────────────────────────

# Perfil de Juan Carlos — qué le interesa
PERFIL_JC = """
Polo Antiguo es una casa de antigüedades argentina dirigida por Juan Carlos Santos.
Compra y vende:
- Relojes antiguos (Longines, Omega, IWC, Vacheron, maquinaria suiza y francesa, de bolsillo y pulsera, anteriores a 1970)
- Militaria (sables, pistolas, condecoraciones, uniformes del ejército argentino siglos XIX-XX)
- Objetos de plata (mates, bombillas, cubiertos, candelabros, bandejas)
- Monedas y billetes argentinos antiguos
- Muebles y objetos de estilo europeo (Luis XV, XVI, Rococó, Victoriano) anteriores a 1930
- Porcelana y cristalería fina antigua (Meissen, Limoges, Baccarat)
- Bronce decorativo, mármol, objetos de arte
- Radios antiguas, gramófonos, vitrolas (previas a 1950)

Precio mínimo de interés para compra: $5.000 ARS o equivalente USD.
Mercados geográficos: Argentina, Sudamérica, España, USA (para piezas muy valiosas).
"""

SYSTEM_PROMPT = f"""Eres el asistente de análisis de Polo Antiguo.
Tu única función es analizar listados de antigüedades y decidir si son relevantes para el negocio.

{PERFIL_JC}

Para cada listado que recibas debes responder ÚNICAMENTE con un JSON válido con esta estructura exacta:
{{
  "relevante": true/false,
  "score": 1-10,
  "categoria": "reloj|militaria|plata|monedas|mueble|porcelana|bronce|radio|otro",
  "razon": "una frase corta explicando por qué es o no relevante",
  "mensaje_wa": "mensaje listo para enviar por WhatsApp al vendedor/comprador (si relevante, sino vacío)"
}}

Reglas para mensaje_wa:
- Si tipo=vendedor: el mensaje es para COMPRARLE a esa persona ("Hola, vi tu publicación...")
- Si tipo=comprador: el mensaje es para VENDERLE a esa persona ("Hola, vi que buscás...")
- Siempre en español argentino informal (vos, che)
- Máximo 3 líneas
- Mencionar Polo Antiguo y dar el número 1135408337
- Si no es relevante, mensaje_wa = ""
"""

def analizar_listado(item: dict) -> dict:
    """
    Analiza un listado con Groq. ~300-400 tokens por llamada.
    Retorna el item enriquecido con análisis.
    """
    prompt_user = f"""Analiza este listado:

Fuente: {item.get('fuente')}
Tipo: {item.get('tipo')} ({'alguien vende, JC puede comprar' if item.get('tipo')=='vendedor' else 'alguien busca comprar, JC puede venderle'})
Título: {item.get('titulo')}
Precio: {item.get('precio')} {item.get('moneda','')}
Ubicación: {item.get('ubicacion','')}
Datos: {item.get('raw','')}

Responde solo con el JSON."""

    try:
        response = client.chat.completions.create(
            model=_detectar_modelo(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_user},
            ],
            temperature=0.2,
            max_tokens=600,   ### CAMBIO AQUÍ ### 400→600 evita "max tokens before valid JSON"
            response_format={"type": "json_object"},
        )
        analisis = json.loads(response.choices[0].message.content)
        item["analisis"] = analisis
        item["relevante"] = analisis.get("relevante", False)
        item["score"] = analisis.get("score", 0)
        item["categoria"] = analisis.get("categoria", "otro")
        item["razon"] = analisis.get("razon", "")
        item["mensaje_wa"] = analisis.get("mensaje_wa", "")

        log.info(f"{'✓' if item['relevante'] else '✗'} [{item['score']}/10] {item['titulo'][:60]}")
    except Exception as e:
        log.warning(f"Groq error en '{item.get('titulo','')}': {e}")
        item["relevante"] = False
        item["score"] = 0
        item["categoria"] = "otro"
        item["razon"] = f"Error de análisis: {e}"
        item["mensaje_wa"] = ""

    return item


def analizar_todos(listados: list[dict], solo_relevantes: bool = True) -> list[dict]:
    """
    Analiza todos los listados. Retorna los relevantes (o todos si solo_relevantes=False).
    Groq free tier: ~30 req/min. Ponemos pausa de 2s entre llamadas.
    """
    import time
    analizados = []
    relevantes = []

    for i, item in enumerate(listados):
        resultado = analizar_listado(item)
        analizados.append(resultado)
        if resultado.get("relevante"):
            relevantes.append(resultado)
        if i < len(listados) - 1:
            time.sleep(2.0)   # respetar rate limit Groq free tier

    log.info(f"Analizados: {len(analizados)} | Relevantes: {len(relevantes)}")
    return relevantes if solo_relevantes else analizados


if __name__ == "__main__":
    # Test con item de ejemplo
    test = [{
        "id": "ml_test_1",
        "fuente": "MercadoLibre",
        "tipo": "vendedor",
        "titulo": "Reloj Longines de Bolsillo Antiguo Plata 1920",
        "precio": 150000,
        "moneda": "ARS",
        "url": "https://mercadolibre.com.ar/test",
        "imagen": "",
        "ubicacion": "Buenos Aires",
        "keyword": "reloj longines antiguo",
        "raw": '{"title":"Reloj Longines de Bolsillo Antiguo Plata 1920","price":150000,"condition":"used"}',
    }]
    resultado = analizar_todos(test, solo_relevantes=False)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
