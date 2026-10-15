"""
buscador.py — Polo Antiguo v2
Fuente: MercadoLibre API pública (gratuita, sin key, sin auth).
~30 queries cubriendo todas las categorías. Rota 8 por ciclo.
"""
import json, time, logging, requests
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

ML_SEARCH_URL = "https://api.mercadolibre.com/sites/{site}/search"

# ### CAMBIO AQUÍ ### Queries para MercadoLibre Argentina (MLA) y España (MLE)
# Tuplas: (keyword, site_ml, categoria_hint)
QUERIES_ML = [
    # ═══ RELOJES Y JOYERÍA ═══
    ("reloj longines antiguo bolsillo",        "MLA", "reloj"),
    ("reloj omega antiguo bolsillo",           "MLA", "reloj"),
    ("reloj suizo antiguo pulsera",            "MLA", "reloj"),
    ("reloj de bolsillo antiguo coleccion",    "MLA", "reloj"),
    ("reloj iwc vacheron antiguo",             "MLA", "reloj"),
    ("joyeria plata antigua collar pulsera",   "MLA", "joyeria"),
    ("reloj longines antiguo bolsillo",        "MLE", "reloj"),

    # ═══ MILITARIA ═══
    ("sable militar antiguo argentina",        "MLA", "militaria"),
    ("militaria antigua condecoracion medalla","MLA", "militaria"),
    ("pistola antigua ejercito argentino",     "MLA", "militaria"),
    ("uniforme militar antiguo",               "MLA", "militaria"),
    ("arma antigua coleccion siglo xix",       "MLA", "militaria"),

    # ═══ PLATERÍA ═══
    ("mate plata antiguo",                     "MLA", "plata"),
    ("plateria criolla bombilla plata",        "MLA", "plata"),
    ("cubiertos plata antigua",                "MLA", "plata"),
    ("candelabro plata antiguo",               "MLA", "plata"),

    # ═══ AUDIO ═══
    ("radio valvulas antigua",                 "MLA", "radio"),
    ("gramofono antiguo vitrola",              "MLA", "radio"),
    ("fonografo antiguo",                      "MLA", "radio"),

    # ═══ NÁUTICA ═══
    ("brujula nautica antigua",                "MLA", "nautica"),
    ("sextante antiguo",                       "MLA", "nautica"),
    ("cronometro marino antiguo",              "MLA", "nautica"),

    # ═══ ARTE Y BRONCE ═══
    ("bronce decorativo antiguo figura",       "MLA", "arte"),
    ("escultura marmol antigua",               "MLA", "arte"),
    ("cuadro pintura antigua firma",           "MLA", "arte"),

    # ═══ MUEBLES E ILUMINACIÓN ═══
    ("mueble antiguo luis xv estilo europeo",  "MLA", "mueble"),
    ("lampara art nouveau antigua",            "MLA", "iluminacion"),
    ("arana cristal antigua",                  "MLA", "iluminacion"),

    # ═══ NUMISMÁTICA ═══
    ("monedas argentinas antiguas coleccion",  "MLA", "monedas"),
    ("billetes antiguos argentina",            "MLA", "monedas"),

    # ═══ PORCELANA ═══
    ("porcelana meissen limoges antigua",      "MLA", "porcelana"),
    ("cristal baccarat antiguo",               "MLA", "porcelana"),
]

QUERIES_POR_CICLO = 8


def fetch_mercadolibre(con) -> list[dict]:
    """Busca en MercadoLibre API (sin auth, sin key)."""
    # Calcular rotación
    row = con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM serp_uso").fetchone()
    total_ciclos = row[0] or 0
    n = len(QUERIES_ML)
    inicio = (total_ciclos * QUERIES_POR_CICLO) % n
    indices = [(inicio + i) % n for i in range(QUERIES_POR_CICLO)]
    queries_ciclo = [QUERIES_ML[i] for i in indices]

    resultados = []
    sess = requests.Session()
    sess.headers.update({"User-Agent": "PoloAntiguoBot/2.0"})

    for kw, site, cat_hint in queries_ciclo:
        try:
            r = sess.get(
                ML_SEARCH_URL.format(site=site),
                params={"q": kw, "limit": 20, "condition": "used"},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("results", [])

            for item in items:
                ml_id = item.get("id", "")
                lid = f"ml_{ml_id}"
                if not ml_id or not es_nuevo(con, lid, "mercadolibre"):
                    continue
                marcar_visto(con, lid, "mercadolibre")

                precio = item.get("price")
                moneda = item.get("currency_id", "ARS")
                ubicacion = ""
                addr = item.get("seller_address", {})
                if addr.get("state"):
                    ubicacion = addr["state"].get("name", "")

                resultados.append({
                    "id":        lid,
                    "fuente":    "MercadoLibre",
                    "tipo":      "vendedor",   # ML = siempre alguien vendiendo
                    "titulo":    item.get("title", ""),
                    "precio":    precio,
                    "moneda":    moneda,
                    "url":       item.get("permalink", ""),
                    "imagen":    item.get("thumbnail", ""),
                    "ubicacion": ubicacion,
                    "keyword":   kw,
                    "raw":       json.dumps({
                        "title":     item.get("title"),
                        "price":     precio,
                        "currency":  moneda,
                        "condition": item.get("condition"),
                        "url":       item.get("permalink"),
                        "ubicacion": ubicacion,
                        "keyword":   kw,
                        "site":      site,
                    }, ensure_ascii=False)[:600],
                })

            log.info(f"ML [{site}] '{kw}': {len(items)} resultados, {sum(1 for r in resultados if r['keyword']==kw)} nuevos")
            time.sleep(1.0)

        except Exception as e:
            log.warning(f"ML '{kw}': {e}")
            time.sleep(2.0)

    # Registrar ciclo
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()

    log.info(f"ML total nuevos este ciclo: {len(resultados)} (queries {inicio}–{(inicio + QUERIES_POR_CICLO - 1) % n} de {n})")
    return resultados


def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()
    todos = fetch_mercadolibre(con)
    con.close()
    log.info(f"TOTAL nuevos este ciclo: {len(todos)}")
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r, ensure_ascii=False, indent=2))
