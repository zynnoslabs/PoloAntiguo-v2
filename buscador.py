"""
buscador.py — Polo Antiguo v2
Fuente: Brave Search API (gratuita, 2000 búsquedas/mes, sin restricciones de IP).
Requiere: BRAVE_API_KEY en variables de entorno Render.
Obtené la clave gratis en: https://api.search.brave.com/app/keys
4 queries × ciclo de 90min → rotación completa ~11 horas.
"""
import os, json, time, logging, requests
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# ### CAMBIO AQUÍ ### 30 queries para Brave Search — cubre todas las categorías
QUERIES = [
    # ═══ RELOJES Y JOYERÍA ═══
    ("heredé reloj longines antiguo vendo argentina",          "herencia"),
    ("vendo reloj de bolsillo suizo antiguo argentina",        "vendedor"),
    ("busco comprar reloj longines bolsillo antiguo argentina","comprador"),
    ("tasación reloj antiguo longines omega buenos aires",     "tasacion"),
    ("remate reloj antiguo colección buenos aires",            "remate"),
    ("vendo joyería plata antigua collares pulseras argentina","vendedor"),
    # ═══ MILITARIA ═══
    ("heredé sable militar antiguo argentina vendo",           "herencia"),
    ("vendo militaria pistola antigua ejército argentino",     "vendedor"),
    ("busco militaria sable argentino siglo xix colección",    "comprador"),
    ("condecoración medalla militar antigua argentina vendo",  "vendedor"),
    # ═══ PLATERÍA ═══
    ("heredé mate de plata antiguo vendo argentina",           "herencia"),
    ("vendo platería criolla mate bombilla plata",             "vendedor"),
    ("cubiertos plata antigua vendo argentina",                "vendedor"),
    ("compro platería criolla argentina piezas antiguas",      "comprador"),
    # ═══ AUDIO ═══
    ("vendo radio antigua válvulas argentina",                 "vendedor"),
    ("heredé gramófono vitrola antiguo vendo argentina",       "herencia"),
    ("busco radio antigua válvulas coleccionista argentina",   "comprador"),
    # ═══ NÁUTICA ═══
    ("vendo brújula náutica antigua argentina",                "vendedor"),
    ("sextante antiguo vendo argentina colección",             "vendedor"),
    # ═══ ARTE ═══
    ("bronce decorativo antiguo vendo argentina",              "vendedor"),
    ("cuadro pintura antigua argentina vendo",                 "vendedor"),
    ("heredé objetos arte antiguo vendo sucesión argentina",   "herencia"),
    # ═══ MUEBLES E ILUMINACIÓN ═══
    ("vendo mueble antiguo luis xv xvi buenos aires",          "vendedor"),
    ("lámpara antigua art nouveau art deco vendo argentina",   "vendedor"),
    ("araña cristal antigua vendo argentina",                  "vendedor"),
    # ═══ NUMISMÁTICA ═══
    ("vendo monedas argentinas antiguas colección",            "vendedor"),
    ("billetes antiguos argentina vendo coleccionista",        "vendedor"),
    ("heredé colección monedas billetes antiguos argentina",   "herencia"),
    # ═══ HERENCIA / REMATE GENÉRICO ═══
    ("heredé contenido casa antigua vendo todo argentina",     "herencia"),
    ("sucesión vendo antigüedades muebles plata argentina",    "herencia"),
]

QUERIES_POR_CICLO = 4   # 4 queries × 16 ciclos/día (90min) = 64/día = 1920/mes < 2000 gratis


def fetch_brave(con) -> list[dict]:
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        log.error("BRAVE_API_KEY no configurada en Render. Ver https://api.search.brave.com/app/keys")
        return []

    row = con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM serp_uso").fetchone()
    total_ciclos = row[0] or 0
    n = len(QUERIES)
    inicio = (total_ciclos * QUERIES_POR_CICLO) % n
    indices = [(inicio + i) % n for i in range(QUERIES_POR_CICLO)]
    queries_ciclo = [QUERIES[i] for i in indices]

    resultados = []
    sess = requests.Session()
    sess.headers.update({
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    })

    for kw, tipo_forzado in queries_ciclo:
        try:
            r = sess.get(BRAVE_URL, params={
                "q": kw, "count": 10,
                "search_lang": "es", "country": "AR",
                "freshness": "pw",   # última semana
            }, timeout=15)
            r.raise_for_status()
            hits = r.json().get("web", {}).get("results", [])

            nuevos = 0
            for res in hits:
                url_res = res.get("url", "")
                lid = f"brave_{abs(hash(url_res + kw))}"
                if not url_res or not es_nuevo(con, lid, "brave"):
                    continue
                marcar_visto(con, lid, "brave")
                resultados.append({
                    "id":        lid,
                    "fuente":    "Web",
                    "tipo":      tipo_forzado,
                    "titulo":    res.get("title", ""),
                    "precio":    None,
                    "moneda":    "ARS",
                    "url":       url_res,
                    "imagen":    "",
                    "ubicacion": "AR",
                    "keyword":   kw,
                    "raw":       json.dumps({
                        "title":       res.get("title"),
                        "description": res.get("description", "")[:300],
                        "url":         url_res,
                        "tipo":        tipo_forzado,
                    }, ensure_ascii=False)[:600],
                })
                nuevos += 1

            log.info(f"Brave '{kw[:40]}': {len(hits)} hits, {nuevos} nuevos")
            time.sleep(1.0)

        except Exception as e:
            log.warning(f"Brave '{kw[:40]}': {e}")
            time.sleep(2.0)

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()
    log.info(f"Brave total nuevos: {len(resultados)} (queries {inicio}–{(inicio+QUERIES_POR_CICLO-1)%n} de {n})")
    return resultados


def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()
    todos = fetch_brave(con)
    con.close()
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r, ensure_ascii=False, indent=2))
