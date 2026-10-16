"""
buscador.py — Polo Antiguo v2
Fuente: Google News RSS — sin API key, sin cuota, accesible desde Render.
Nota: ML API (api.mercadolibre.com) bloquea las IPs de Render con 403.
"""
import json, time, logging, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

GNEWS_URL = "https://news.google.com/rss/search"

# Queries orientadas a encontrar vendedores reales en foros/redes, no noticias.
# GNews indexa también Taringa, Reddit, MercadoLibre, clasificados y blogs de venta.
QUERIES = [
    # ═══ RELOJES ═══
    ("\"vendo\" reloj longines bolsillo antiguo argentina",        "vendedor"),
    ("\"vendo\" reloj omega antiguo coleccion argentina",          "vendedor"),
    ("\"vendo\" reloj suizo antiguo bolsillo coleccion argentina", "vendedor"),
    ("\"vendo\" reloj iwc vacheron antiquo argentina",             "vendedor"),
    ("\"vendo\" reloj art deco pulsera antiguo argentina",         "vendedor"),
    ("\"heredé\" OR \"herencia\" reloj longines antiguo argentina","herencia"),
    ("\"heredé\" relojes antiguos vendo argentina",                "herencia"),
    ("\"busco comprar\" reloj longines bolsillo antiguo",          "comprador"),
    ("\"busco\" reloj suizo antiguo coleccionista argentina",      "comprador"),
    # ═══ JOYERÍA ═══
    ("\"vendo\" joyeria plata antigua argentina",                  "vendedor"),
    ("\"vendo\" pulsera collar plata antigua argentina",           "vendedor"),
    ("\"herencia\" joyeria antigua plata vendo argentina",         "herencia"),
    # ═══ MILITARIA ═══
    ("\"vendo\" sable militar antiguo argentina",                  "vendedor"),
    ("\"vendo\" militaria antigua pistola coleccion argentina",    "vendedor"),
    ("\"herencia\" militaria antigua vendo argentina",             "herencia"),
    # ═══ PLATERÍA ═══
    ("\"vendo\" mate plata antiguo argentina",                     "vendedor"),
    ("\"vendo\" plateria criolla antigua argentina",               "vendedor"),
    ("\"herencia\" plateria antigua vendo argentina",              "herencia"),
    # ═══ AUDIO ═══
    ("\"vendo\" radio valvulas antigua argentina",                 "vendedor"),
    ("\"vendo\" gramofono vitrola antiguo argentina",              "vendedor"),
    # ═══ ARTE ═══
    ("\"vendo\" cuadro pintura antigua argentina",                 "vendedor"),
    ("\"vendo\" bronce decorativo antiguo argentina",              "vendedor"),
    ("\"vendo\" lampara antigua art nouveau argentina",            "vendedor"),
    # ═══ MUEBLES ═══
    ("\"vendo\" mueble antiguo luis xv xvi argentina",             "vendedor"),
    ("\"herencia\" muebles antiguos vendo argentina",              "herencia"),
    # ═══ NUMISMÁTICA ═══
    ("\"vendo\" monedas antiguas coleccion argentina",             "vendedor"),
    ("\"vendo\" billetes antiguos argentina coleccion",            "vendedor"),
    # ═══ SUCESIONES ═══
    ("\"sucesion\" OR \"liquidacion\" antiguedades lote argentina","herencia"),
    ("\"liquido\" antiguedades herencia argentina",                "herencia"),
]

QUERIES_POR_CICLO = 4   # 4 × 16 ciclos/día = 64 búsquedas/día


def _calcular_indices(con) -> tuple[list[int], int]:
    n     = len(QUERIES)
    total = con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM serp_uso").fetchone()[0] or 0
    ini   = (total * QUERIES_POR_CICLO) % n
    return [(ini + i) % n for i in range(QUERIES_POR_CICLO)], ini


def fetch_gnews(con, indices: list[int]) -> list[dict]:
    """Google News RSS — sin API key, sin límite de cuota."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; PoloAntiguoBot/1.0)",
        "Accept":     "application/xml,text/xml",
    })
    resultados = []

    for idx in indices:
        kw, tipo = QUERIES[idx]
        try:
            r = sess.get(GNEWS_URL, params={
                "q":    kw,
                "hl":   "es-419",
                "gl":   "AR",
                "ceid": "AR:es",
            }, timeout=15)
            r.raise_for_status()

            root  = ET.fromstring(r.content)
            items = root.findall(".//item")

            nuevos = 0
            for it in items:
                titulo = it.findtext("title", "")
                url_i  = it.findtext("link", "")
                desc   = it.findtext("description", "")
                if not url_i or not titulo:
                    continue
                url_c = url_i.split("?")[0].split("#")[0]
                lid   = f"gn_{abs(hash(url_c + kw))}"
                if not es_nuevo(con, lid, "gnews"):
                    continue
                marcar_visto(con, lid, "gnews")
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

            log.info(f"GNews '{kw[:50]}': {len(items)} resultados, {nuevos} nuevos")
            time.sleep(0.3)

        except Exception as e:
            log.warning(f"GNews error '{kw[:50]}': {e}")
            time.sleep(2.0)

    return resultados


def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()

    indices, inicio = _calcular_indices(con)
    n = len(QUERIES)

    todos = fetch_gnews(con, indices)

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()

    log.info(f"Ciclo GNews: {len(todos)} nuevos — queries {inicio}–{(inicio+QUERIES_POR_CICLO-1)%n}/{n}")
    con.close()
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r[:3], ensure_ascii=False, indent=2))
    print(f"Total: {len(r)}")
