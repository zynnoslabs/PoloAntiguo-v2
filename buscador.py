"""
buscador.py — Polo Antiguo v2
Fuente: Google Custom Search API — funciona desde Render, 100 búsquedas/día gratis.
Requiere 2 vars en Render: GOOGLE_CSE_KEY y GOOGLE_CSE_CX
Ver instrucciones en /admin.
"""
import os, json, time, logging, requests
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

GOOGLE_URL = "https://www.googleapis.com/customsearch/v1"

# ### CAMBIO AQUÍ ### Queries naturales → Google encuentra ML, OLX, Clasificados, foros y más
QUERIES = [
    # ═══ RELOJES — VENDEDORES ═══
    ("vendo reloj longines antiguo argentina",            "vendedor"),
    ("vendo reloj omega bolsillo antiguo argentina",      "vendedor"),
    ("vendo reloj suizo antiguo coleccion argentina",     "vendedor"),
    ("vendo reloj iwc vacheron antiguo argentina",        "vendedor"),
    ("vendo reloj art deco pulsera antiguo argentina",    "vendedor"),
    # ═══ RELOJES — HERENCIAS ═══
    ("herencia reloj longines antiguo vendo argentina",   "herencia"),
    ("heredé relojes antiguos vendo argentina",           "herencia"),
    # ═══ RELOJES — COMPRADORES ═══
    ("busco comprar reloj longines bolsillo antiguo",     "comprador"),
    ("busco reloj suizo antiguo coleccionista argentina", "comprador"),
    # ═══ JOYERÍA ═══
    ("vendo joyeria plata antigua argentina",             "vendedor"),
    ("vendo pulsera collar plata antigua argentina",      "vendedor"),
    ("herencia vendo joyeria antigua plata argentina",    "herencia"),
    # ═══ MILITARIA ═══
    ("vendo sable militar antiguo argentina",             "vendedor"),
    ("vendo militaria antigua pistola coleccion",         "vendedor"),
    ("herencia vendo militaria antigua argentina",        "herencia"),
    # ═══ PLATERÍA ═══
    ("vendo mate plata antiguo argentina",                "vendedor"),
    ("vendo plateria criolla antigua argentina",          "vendedor"),
    ("herencia vendo plateria antigua argentina",         "herencia"),
    # ═══ AUDIO ═══
    ("vendo radio antigua valvulas argentina",            "vendedor"),
    ("vendo gramofono vitrola antiguo argentina",         "vendedor"),
    # ═══ ARTE ═══
    ("vendo cuadro pintura antigua argentina",            "vendedor"),
    ("vendo bronce decorativo antiguo argentina",         "vendedor"),
    ("vendo lampara antigua art nouveau argentina",       "vendedor"),
    # ═══ MUEBLES ═══
    ("vendo mueble antiguo luis xv xvi argentina",        "vendedor"),
    ("herencia vendo muebles antiguos argentina",         "herencia"),
    # ═══ NUMISMÁTICA ═══
    ("vendo monedas antiguas coleccion argentina",        "vendedor"),
    ("vendo billetes antiguos argentina coleccion",       "vendedor"),
    # ═══ LIQUIDACIONES / SUCESIONES ═══
    ("sucesion vendo antiguedades lote argentina",        "herencia"),
]

QUERIES_POR_CICLO = 4   # 4 × 16 ciclos/día = 64/día < 100 límite gratis


def fetch_google(con) -> list[dict]:
    api_key = os.environ.get("GOOGLE_CSE_KEY", "")
    cx      = os.environ.get("GOOGLE_CSE_CX", "")
    if not api_key or not cx:
        log.error("GOOGLE_CSE_KEY / GOOGLE_CSE_CX no configurados. Ir a /admin para ver instrucciones.")
        return []

    row    = con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM serp_uso").fetchone()
    total  = row[0] or 0
    n      = len(QUERIES)
    inicio = (total * QUERIES_POR_CICLO) % n
    indices = [(inicio + i) % n for i in range(QUERIES_POR_CICLO)]

    sess = requests.Session()
    resultados = []

    for idx in indices:
        kw, tipo = QUERIES[idx]
        try:
            r = sess.get(GOOGLE_URL, params={
                "key": api_key,
                "cx":  cx,
                "q":   kw,
                "num": 10,
                "gl":  "ar",       # resultados de Argentina
                "hl":  "es",
                "lr":  "lang_es",
                "dateRestrict": "m1",   # último mes
            }, timeout=15)
            r.raise_for_status()
            items = r.json().get("items", [])

            nuevos = 0
            for item in items:
                url_i  = item.get("link", "")
                titulo = item.get("title", "")
                desc   = item.get("snippet", "")
                if not url_i or not titulo:
                    continue
                url_c = url_i.split("?")[0].split("#")[0]
                lid   = f"gcs_{abs(hash(url_c + kw))}"
                if not es_nuevo(con, lid, "google"):
                    continue
                marcar_visto(con, lid, "google")
                resultados.append({
                    "id":        lid,
                    "fuente":    "Web",
                    "tipo":      tipo,
                    "titulo":    titulo[:200],
                    "precio":    None,
                    "moneda":    "ARS",
                    "url":       url_c,
                    "imagen":    "",
                    "ubicacion": "AR",
                    "keyword":   kw,
                    "raw":       json.dumps({
                        "title":       titulo,
                        "description": desc[:300],
                        "url":         url_c,
                        "tipo":        tipo,
                    }, ensure_ascii=False)[:600],
                })
                nuevos += 1

            log.info(f"Google '{kw[:45]}': {len(items)} resultados, {nuevos} nuevos")
            time.sleep(0.5)

        except Exception as e:
            try:
                log.warning(f"Google CSE error body: {r.text[:300]}")
            except:
                pass
            log.warning(f"Google error: {e}")
            time.sleep(2.0)

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()
    log.info(f"Google CSE — total nuevos: {len(resultados)} (queries {inicio}–{(inicio+QUERIES_POR_CICLO-1)%n}/{n})")
    return resultados


def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()
    todos = fetch_google(con)
    con.close()
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r[:3], ensure_ascii=False, indent=2))
    print(f"Total: {len(r)}")
