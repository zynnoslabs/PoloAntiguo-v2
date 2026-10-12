"""
analizador.py — Polo Antiguo v2
Groq analiza cada listado y genera mensaje WA listo para enviar.
"""
import os, json, logging
from groq import Groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("analizador")

client = Groq(api_key=os.environ.get("GROQ_API_KEY",""))

_MODELO_CACHE = None
_MODELOS = [
    "gemma2-9b-it",
    "llama3-8b-8192",
    "llama-3.2-3b-preview",
    "mixtral-8x7b-32768",
    "qwen-qwq-32b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
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
            client.chat.completions.create(
                model=m,
                messages=[{"role":"user","content":'Responde exactamente: {"ok":true}'}],
                max_tokens=50, temperature=0,
                response_format={"type":"json_object"},
            )
            _MODELO_CACHE = m
            log.info(f"Modelo activo: {m}")
            return m
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ["model_not_found","404","decommissioned","not found","json_validate_failed"]):
                log.warning(f"Modelo no disponible: {m}")
                continue
            _MODELO_CACHE = m
            log.warning(f"Modelo (error no-fatal): {m}")
            return m
    _MODELO_CACHE = _MODELOS[0]
    log.error("Ningun modelo disponible. Configura GROQ_MODEL en Render.")
    return _MODELO_CACHE

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
Precio mínimo: $5.000 ARS o equivalente USD.
Mercados: Argentina, Sudamérica, España, USA (piezas muy valiosas).
"""

SYSTEM_PROMPT = f"""Eres el asistente de análisis de Polo Antiguo.
Analizás listados de antigüedades y decidís si son oportunidades de negocio.

{PERFIL}

Respondé ÚNICAMENTE con JSON válido:
{{
  "relevante": true/false,
  "score": 1-10,
  "categoria": "reloj|militaria|plata|monedas|mueble|porcelana|bronce|radio|otro",
  "razon": "frase corta explicando el potencial de negocio",
  "mensaje_wa": "mensaje WhatsApp listo para enviar (vacío si no es relevante)"
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
    prompt = f"""Analizá este listado:

Fuente: {item.get('fuente')}
Tipo: {item.get('tipo')} ({'alguien vende, JC puede comprar' if item.get('tipo')=='vendedor' else 'alguien busca comprar, JC puede venderle'})
Título: {item.get('titulo')}
Precio: {item.get('precio')} {item.get('moneda','')}
Ubicación: {item.get('ubicacion','')}
Datos: {item.get('raw','')}

Respondé solo con el JSON."""

    try:
        resp = client.chat.completions.create(
            model=_detectar_modelo(),
            messages=[
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"user","content":prompt},
            ],
            temperature=0.2, max_tokens=600,
            response_format={"type":"json_object"},
        )
        analisis = json.loads(resp.choices[0].message.content)
        item.update({
            "relevante": analisis.get("relevante", False),
            "score":     analisis.get("score", 0),
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
