"""
buscador.py — Polo Antiguo v2
Fuentes: SerpApi (AR + ES + UY) + eBay API (activa con EBAY_APP_ID)
"""
import os, json, time, requests, logging
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

# ─── SerpApi ──────────────────────────────────────────────────────────────────
# Tuplas: (keyword, gl_pais, tipo_forzado_o_None)
QUERIES_SERP = [
    # AR — señales pre-mercado
    ("heredé reloj antiguo cuánto vale argentina",         "ar", None),
    ("heredé antigüedades plata qué hago argentina",       "ar", None),
    ("heredé contenido casa antigua vendo argentina",      "ar", None),
    ("tasación antigüedades plata buenos aires",           "ar", None),
    ("tasación reloj antiguo longines argentina",          "ar", None),
    ("vendo contenido casa antigua sucesión argentina",    "ar", None),
    ("remate judicial antigüedades buenos aires",          "ar", None),
    ("sucesión vendo antigüedades muebles plata",          "ar", None),
    ("remate antigüedades buenos aires 2026",              "ar", None),
    ("subasta antigüedades argentina 2026",                "ar", None),
    # AR — compradores
    ("busco comprar reloj longines antiguo argentina",     "ar", "comprador"),
    ("compro antigüedades plata buenos aires",             "ar", "comprador"),
    ("busco reloj de bolsillo antiguo argentina",          "ar", "comprador"),
    ("busco mate de plata antiguo argentina",              "ar", "comprador"),
    ("compro monedas antiguas argentina coleccion",        "ar", "comprador"),
    ("busco militaria sable argentino siglo xix",          "ar", "comprador"),
    # AR — Facebook indexado por Google
    ("site:facebook.com heredé antigüedades vendo argentina",    "ar", None),
    ("site:facebook.com reloj longines antiguo vendo argentina", "ar", None),
    # ES — vendedores
    ("vendo reloj longines antiguo bolsillo españa",       "es", "vendedor"),
    ("vendo antigüedades plata relojes antiguos españa",   "es", "vendedor"),
    # ES — compradores
    ("busco reloj longines antiguo comprar españa",        "es", "comprador"),
    ("compro antigüedades plata coleccionista españa",     "es", "comprador"),
    # UY
    ("vendo antigüedades reloj plata uruguay",             "uy", None),
    ("busco comprar antigüedades reloj plata uruguay",     "uy", "comprador"),
]

def _detectar_tipo(titulo, snippet, tipo_forzado):
    if tipo_forzado:
        return tipo_forzado
    texto = (titulo + " " + snippet).lower()
    if any(w in texto for w in ["heredé","herencia","sucesión","contenido casa"]):
        return "herencia"
    if any(w in texto for w in ["tasación","tasar","qué vale","cuánto vale"]):
        return "tasacion"
    if any(w in texto for w in ["remate","subasta","lote","martillo"]):
        return "remate"
    if any(w in texto for w in ["busco","compro","wanted","looking for","se busca"]):
        return "comprador"
    return "vendedor"

def fetch_serpapi(con) -> list[dict]:
    api_key = os.environ.get("SERPAPI_KEY","")
    if not api_key:
        log.info("SerpApi: sin SERPAPI_KEY, saltando")
        return []

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = con.execute("SELECT cantidad FROM serp_uso WHERE fecha=?", (hoy,)).fetchone()
    uso_hoy = row[0] if row else 0
    MAX_DIA = 3
    if uso_hoy >= MAX_DIA:
        log.info(f"SerpApi: cuota alcanzada ({uso_hoy}/{MAX_DIA})")
        return []

    row_total = con.execute("SELECT SUM(cantidad) FROM serp_uso").fetchone()
    total_usado = row_total[0] or 0
    n = len(QUERIES_SERP)
    inicio = total_usado % n
    queries_hoy = (QUERIES_SERP * 2)[inicio: inicio + MAX_DIA - uso_hoy]

    resultados = []
    for kw, gl, tipo_forzado in queries_hoy:
        try:
            r = requests.get("https://serpapi.com/search", params={
                "api_key": api_key, "q": kw, "hl": "es", "gl": gl, "num": 10,
            }, timeout=15)
            r.raise_for_status()
            data = r.json()
            con.execute("""
                INSERT INTO serp_uso(fecha,cantidad) VALUES(?,1)
                ON CONFLICT(fecha) DO UPDATE SET cantidad=cantidad+1
            """, (hoy,))
            con.commit()
            for res in data.get("organic_results", []):
                url_res = res.get("link","")
                lid = f"serp_{abs(hash(url_res+kw))}"
                if not es_nuevo(con, lid, "serpapi"):
                    continue
                marcar_visto(con, lid, "serpapi")
                titulo = res.get("title","")
                snippet = res.get("snippet","")
                tipo = _detectar_tipo(titulo, snippet, tipo_forzado)
                moneda = "ARS" if gl=="ar" else ("EUR" if gl=="es" else "UYU")
                resultados.append({
                    "id": lid, "fuente": "Web", "tipo": tipo,
                    "titulo": titulo, "precio": None, "moneda": moneda,
                    "url": url_res, "imagen": "",
                    "ubicacion": res.get("source","") + f" ({gl.upper()})",
                    "keyword": kw,
                    "raw": json.dumps({
                        "title": titulo, "snippet": snippet,
                        "url": url_res, "country": gl, "tipo": tipo,
                    }, ensure_ascii=False)[:600],
                })
            time.sleep(1.5)
        except Exception as e:
            log.warning(f"SerpApi '{kw}': {e}")

    log.info(f"SerpApi: {len(resultados)} nuevos (hoy: {uso_hoy+len(queries_hoy)}/{MAX_DIA})")
    return resultados

# ─── eBay API ──────────────────────────────────────────────────────────────────
KEYWORDS_EBAY = [
    "reloj longines bolsillo antiguo",
    "mate plata argentina antique",
    "sable militar argentino antique",
    "monedas argentinas antiguas",
    "reloj omega antiguo pocket watch",
    "porcelana meissen antigua",
    "gramofono antiguo vitrola",
]

def fetch_ebay(con) -> list[dict]:
    app_id = os.environ.get("EBAY_APP_ID","")
    if not app_id:
        return []
    row_total = con.execute("SELECT SUM(cantidad) FROM serp_uso").fetchone()
    total_usado = row_total[0] or 0
    n = len(KEYWORDS_EBAY)
    inicio = total_usado % n
    kws_hoy = (KEYWORDS_EBAY * 2)[inicio: inicio+2]
    resultados = []
    for kw in kws_hoy:
        try:
            r = requests.get(
                "https://svcs.ebay.com/services/search/FindingService/v1",
                params={
                    "OPERATION-NAME": "findItemsByKeywords",
                    "SERVICE-VERSION": "1.0.0",
                    "SECURITY-APPNAME": app_id,
                    "RESPONSE-DATA-FORMAT": "JSON",
                    "keywords": kw,
                    "paginationInput.entriesPerPage": "10",
                    "itemFilter(0).name": "Condition",
                    "itemFilter(0).value(0)": "Used",
                    "sortOrder": "BestMatch",
                }, timeout=15)
            r.raise_for_status()
            data = r.json()
            items = (data.get("findItemsByKeywordsResponse",[{}])[0]
                        .get("searchResult",[{}])[0]
                        .get("item",[]))
            for it in items:
                item_id = it.get("itemId",[""])[0]
                lid = f"ebay_{item_id}"
                if not es_nuevo(con, lid, "ebay"):
                    continue
                marcar_visto(con, lid, "ebay")
                titulo = it.get("title",[""])[0]
                precio_val = (it.get("sellingStatus",[{}])[0]
                               .get("currentPrice",[{}])[0]
                               .get("__value__",""))
                url_res = it.get("viewItemURL",[""])[0]
                pais = it.get("country",[""])[0]
                resultados.append({
                    "id": lid, "fuente": "eBay", "tipo": "vendedor",
                    "titulo": titulo,
                    "precio": float(precio_val) if precio_val else None,
                    "moneda": "USD", "url": url_res,
                    "imagen": it.get("galleryURL",[""])[0],
                    "ubicacion": pais, "keyword": kw,
                    "raw": json.dumps({
                        "title": titulo, "price_usd": precio_val,
                        "country": pais, "url": url_res,
                    }, ensure_ascii=False)[:600],
                })
            time.sleep(1.0)
        except Exception as e:
            log.warning(f"eBay '{kw}': {e}")
    if resultados:
        log.info(f"eBay: {len(resultados)} nuevos")
    return resultados

def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()
    todos = fetch_serpapi(con) + fetch_ebay(con)
    con.close()
    log.info(f"TOTAL nuevos: {len(todos)}")
    return todos

if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r, ensure_ascii=False, indent=2))
