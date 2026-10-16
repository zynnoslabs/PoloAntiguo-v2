"""
analizador.py — Polo Antiguo v2
Groq analiza cada listado y genera mensaje WA listo para enviar.
"""
import os, re, json, logging
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("analizador")

client = Groq(api_key=os.environ.get("GROQ_API_KEY",""))

_MODELO_CACHE = None
_MODELOS = [
    "openai/gpt-oss-20b",        # ### CAMBIO AQUÍ ### — primero el confirmado disponible
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

def _detectar_modelo() -> str:
    global _MODELO_CACHE
    if _MODELO_CACHE:
        return _MODELO_CACHE

    override = os.environ.get("GROQ_MODEL","")
    if override:
        _MODELO_CACHE = override
        log.info(f"Modelo (env): {override}")
        return override

    for m in _MODELOS:
        try:
            # ### CAMBIO AQUÍ ### — aceptamos cualquier HTTP 200, sin revisar content
            # openai/gpt-oss-20b devuelve 200 pero content vacío en prompts cortos;
            # lo que importa es que NO lance excepción (= modelo disponible)
            client.chat.completions.create(
                model=m,
                messages=[{"role":"user","content":"Respondé: OK"}],
                max_tokens=5, temperature=0,
            )
            _MODELO_CACHE = m
            log.info(f"Modelo activo: {m}")
            return m
        except Exception as e:
            log.warning(f"Modelo no disponible: {m} — {str(e)[:80]}")

    # ### CAMBIO AQUÍ ### — fallback al primer modelo de la lista (el confirmado)
    _MODELO_CACHE = _MODELOS[0]
    log.error("Ningún modelo respondió. Configura GROQ_MODEL=openai/gpt-oss-20b en Render.")
    return _MODELO_CACHE


def _extraer_json(texto: str) -> dict:
    """Extrae el primer bloque JSON del texto de respuesta (con conteo de llaves)."""
    # Intento directo
    try:
        return json.loads(texto.strip())
    except Exception:
        pass

    # Buscar bloque ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", texto)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # ### CAMBIO AQUÍ ### — brace counting (maneja JSON anidado correctamente)
    # El regex {.*?} no-greedy fallaba con {"a": {"b": 1}} → extraía {"a": {"b": 1}
    start = texto.find('{')
    if start == -1:
        return {}

    depth = 0
    in_str = False
    escape = False
    for i, c in enumerate(texto[start:], start):
        if escape:
            escape = False
            continue
        if c == '\\' and in_str:
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(texto[start:i+1])
                except Exception:
                    pass
                break

    return {}


PERFIL = """
Polo Antiguo — casa de antigüedades argentina, Juan Carlos Santos.
Compra y vende:
- Relojes antiguos (Longines, Omega, IWC, Vacheron, suizos/franceses, bolsillo y pulsera, anteriores a 1970)
- Militaria argentina (sables, pistolas, condecoraciones, uniformes, siglos XIX-XX)
- Objetos de plata (mates, bombillas, cubiertos, candelabros, bandejas)
- Monedas y billetes argentinos antiguos
- Muebles estilo europeo (Luis XV/XVI, Rococó, Victoriano) anteriores a 1930
- Porcelana y cristalería fina (Meissen, Limoges, Baccarat)
- Bronce decorativo, mármol, objetos de arte
- Radios, gramófonos, vitrolas (anteriores a 1950)
- Náutica antigua: brújulas, sextantes, cronómetros marinos, instrumentos de navegación
- Arte antiguo: pinturas, esculturas en bronce y mármol, objetos decorativos de arte
- Iluminación antigua: lámparas art nouveau, arañas de cristal, apliques
- Joyería antigua: collares, pulseras, broches en plata u oro (anteriores a 1950)
Precio mínimo: $5.000 ARS o equivalente USD.
Mercados: Argentina, Sudamérica, España, USA (piezas muy valiosas).
"""

SYSTEM_PROMPT = f"""Eres el asistente de análisis de Polo Antiguo.
Analizás listados de antigüedades y decidís si son oportunidades de negocio.

{PERFIL}

IMPORTANTE: Respondé ÚNICAMENTE con un objeto JSON válido, sin texto adicional antes ni después:
{{
  "relevante": true/false,
  "score": 1-10,
  "categoria": "reloj|militaria|plata|monedas|mueble|porcelana|bronce|radio|nautica|arte|iluminacion|joyeria|otro",
  "razon": "frase corta explicando el potencial de negocio",
  "mensaje_wa": "mensaje WhatsApp listo para enviar (string vacío si no es relevante)"
}}

Reglas mensaje_wa:
- tipo=vendedor: querés comprarle → "Hola, vi tu publicación..."
- tipo=comprador: querés venderle → "Hola, vi que buscás..."
- Español argentino informal (vos, che)
- Máximo 3 líneas
- Mencioná Polo Antiguo y el número 1135408337
- Si no es relevante: mensaje_wa = ""
"""

def analizar_listado(item: dict) -> dict:
    prompt = f"""Analizá este listado y respondé solo con JSON:

Fuente: {item.get('fuente')}
Tipo: {item.get('tipo')} ({'alguien vende, JC puede comprar' if item.get('tipo')=='vendedor' else 'alguien busca comprar, JC puede venderle'})
Título: {item.get('titulo')}
Precio: {item.get('precio')} {item.get('moneda','')}
Ubicación: {item.get('ubicacion','')}
Datos: {item.get('raw','')}"""

    try:
        resp = client.chat.completions.create(
            model=_detectar_modelo(),
            messages=[
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"user","content":prompt},
            ],
            temperature=0.2, max_tokens=1000,  # ### CAMBIO AQUÍ ### — era 600, cortaba JSON
        )
        choice = resp.choices[0]
        texto  = choice.message.content or ""
        finish = getattr(choice, "finish_reason", "") or ""
        # ### CAMBIO AQUÍ ### — si se cortó por length, intentamos parsear igual; sino descartamos
        if not texto.strip():
            item.update({"relevante": False, "score": 0, "categoria": "otro",
                         "razon": "Respuesta vacía del modelo", "mensaje_wa": ""})
            log.info(f"✗ [0/10] {item.get('titulo','')[:60]} (respuesta vacía)")
            return item
        if finish == "length":
            log.warning(f"Groq cortó respuesta por length: '{item.get('titulo','')[:50]}'")
            # intenta parsear lo que haya; si falla, descarta como no relevante
            analisis = _extraer_json(texto)
            if not analisis:
                item.update({"relevante": False, "score": 0, "categoria": "otro",
                             "razon": "Respuesta truncada (length)", "mensaje_wa": ""})
                log.info(f"✗ [0/10] {item.get('titulo','')[:60]} (truncado)")
                return item
        else:
            analisis = _extraer_json(texto)
            if not analisis:
                raise ValueError(f"JSON no parseable: {texto[:80]}")
        item.update({
            "relevante": bool(analisis.get("relevante", False)),
            "score":     int(analisis.get("score", 0)),
            "categoria": analisis.get("categoria", "otro"),
            "razon":     analisis.get("razon", ""),
            "mensaje_wa":analisis.get("mensaje_wa", ""),
        })
        simbolo = "✓" if item["relevante"] else "✗"
        log.info(f"{simbolo} [{item['score']}/10] {item['titulo'][:60]}")
    except Exception as e:
        log.warning(f"Groq error '{item.get('titulo','')}': {e}")
        item.update({"relevante":False,"score":0,"categoria":"otro",
                     "razon":f"Error: {e}","mensaje_wa":""})
    return item

def analizar_todos(listados: list[dict], solo_relevantes=True) -> list[dict]:
    import time
    analizados, relevantes = [], []
    for i, item in enumerate(listados):
        r = analizar_listado(item)
        analizados.append(r)
        if r.get("relevante"):
            relevantes.append(r)
        if i < len(listados)-1:
            time.sleep(2.0)
    log.info(f"Analizados: {len(analizados)} | Relevantes: {len(relevantes)}")
    return relevantes if solo_relevantes else analizados
