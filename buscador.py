"""
buscador.py — Polo Antiguo v2
Fuente: DuckDuckGo (gratuito, sin límite, sin API key).
~48 queries cubriendo TODAS las categorías de poloantiguoia.com.
Rota 8 queries por ciclo → rotación completa cada ~6 ciclos (4-5 horas a 45min/ciclo).
"""
import json, time, logging
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

# ─── Queries DuckDuckGo ───────────────────────────────────────────────────────
# Tuplas: (keyword, region_ddg, tipo_forzado_o_None)
# Regiones DDG: "ar-es", "es-es", "uy-es", "wt-wt" (mundial)
# Tipos: vendedor / comprador / herencia / tasacion / remate

### CAMBIO AQUÍ ### 48 queries cubriendo todas las categorías de poloantiguoia.com
QUERIES_DDG = [
    # ═══ RELOJES Y JOYERÍA ═══
    ("heredé reloj longines antiguo vendo argentina",           "ar-es", "herencia"),
    ("vendo reloj de bolsillo suizo antiguo argentina",         "ar-es", "vendedor"),
    ("busco comprar reloj longines bolsillo antiguo argentina",  "ar-es", "comprador"),
    ("tasación reloj antiguo longines omega buenos aires",      "ar-es", "tasacion"),
    ("remate reloj antiguo colección buenos aires",             "ar-es", "remate"),
    ("vendo joyería plata antigua collares pulseras argentina", "ar-es", "vendedor"),
    ("vendo reloj antiguo bolsillo longines españa",            "es-es", "vendedor"),
    ("busco reloj suizo antiguo coleccionista",                 "wt-wt", "comprador"),

    # ═══ MILITARIA Y ARMAS ═══
    ("heredé sable militar antiguo argentina vendo",            "ar-es", "herencia"),
    ("vendo militaria pistola antigua ejército argentino",      "ar-es", "vendedor"),
    ("busco militaria sable argentino siglo xix colección",     "ar-es", "comprador"),
    ("condecoración medalla militar antigua argentina vendo",   "ar-es", "vendedor"),
    ("uniforme militar antiguo argentina vendo sucesión",       "ar-es", "herencia"),
    ("compro militaria condecoraciones armas antiguas",         "ar-es", "comprador"),

    # ═══ PLATERÍA CRIOLLA ═══
    ("heredé mate de plata antiguo vendo argentina",            "ar-es", "herencia"),
    ("vendo platería criolla mate bombilla plata",              "ar-es", "vendedor"),
    ("busco mate plata antiguo argentina colección",            "ar-es", "comprador"),
    ("cubiertos plata antigua vendo argentina",                 "ar-es", "vendedor"),
    ("candelabro bandeja plata antigua argentina vendo",        "ar-es", "vendedor"),
    ("compro platería criolla argentina piezas antiguas",       "ar-es", "comprador"),

    # ═══ AUDIO ANTIGUO ═══
    ("vendo radio antigua válvulas argentina",                  "ar-es", "vendedor"),
    ("heredé gramófono vitrola antiguo vendo argentina",        "ar-es", "herencia"),
    ("vendo fonógrafo gramophone antiguo funcionando",          "ar-es", "vendedor"),
    ("busco radio antigua válvulas coleccionista argentina",    "ar-es", "comprador"),
    ("vitrola victor antigua vendo argentina",                  "ar-es", "vendedor"),

    # ═══ NÁUTICA ANTIGUA ═══
    ("vendo brújula náutica antigua argentina",                 "ar-es", "vendedor"),
    ("sextante antiguo vendo argentina colección",              "ar-es", "vendedor"),
    ("instrumentos navegación antiguos vendo buenos aires",     "ar-es", "vendedor"),
    ("busco náutica antigua brújula sextante coleccionista",    "ar-es", "comprador"),
    ("cronómetro marino antiguo vendo argentina",               "ar-es", "vendedor"),

    # ═══ ARTE ANTIGUO ═══
    ("bronce decorativo antiguo vendo argentina",               "ar-es", "vendedor"),
    ("escultura mármol antigua vendo buenos aires",             "ar-es", "vendedor"),
    ("cuadro pintura antigua argentina vendo",                  "ar-es", "vendedor"),
    ("busco arte antiguo bronce mármol argentina",              "ar-es", "comprador"),
    ("heredé objetos arte antiguo vendo sucesión argentina",    "ar-es", "herencia"),

    # ═══ MUEBLES E ILUMINACIÓN ═══
    ("vendo mueble antiguo luis xv xvi buenos aires",           "ar-es", "vendedor"),
    ("lámpara antigua art nouveau art deco vendo argentina",    "ar-es", "vendedor"),
    ("araña cristal antigua vendo argentina",                   "ar-es", "vendedor"),
    ("muebles antiguos estilo europeo sucesión vendo",          "ar-es", "herencia"),
    ("busco muebles antigüedades europeas iluminación antigua", "ar-es", "comprador"),

    # ═══ NUMISMÁTICA ═══
    ("vendo monedas argentinas antiguas colección",             "ar-es", "vendedor"),
    ("billetes antiguos argentina vendo coleccionista",         "ar-es", "vendedor"),
    ("busco monedas argentinas antiguas compro",                "ar-es", "comprador"),
    ("heredé colección monedas billetes antiguos argentina",    "ar-es", "herencia"),
    ("remate numismática argentina monedas antiguas 2026",      "ar-es", "remate"),

    # ═══ SEÑALES GENÉRICAS — HERENCIA / REMATE ═══
    ("heredé contenido casa antigua vendo todo argentina",      "ar-es", "herencia"),
    ("sucesión vendo antigüedades muebles plata argentina",     "ar-es", "herencia"),
    ("remate judicial antigüedades buenos aires 2026",          "ar-es", "remate"),
    ("subasta antigüedades argentina 2026",                     "ar-es", "remate"),
    ("vaciamos casa antigua antigüedades plata relojes vendo",  "ar-es", "herencia"),
]

QUERIES_POR_CICLO = 8   # 8 queries × 45 min ciclo = rotación completa en ~5-6 horas


def _detectar_tipo(titulo, snippet, tipo_forzado):
    if tipo_forzado:
        return tipo_forzado
    texto = (titulo + " " + snippet).lower()
    if any(w in texto for w in ["heredé", "herencia", "sucesión", "contenido casa", "vaciamos"]):
        return "herencia"
    if any(w in texto for w in ["tasación", "tasar", "qué vale", "cuánto vale"]):
        return "tasacion"
    if any(w in texto for w in ["remate", "subasta", "lote", "martillo"]):
        return "remate"
    if any(w in texto for w in ["busco", "compro", "wanted", "looking for", "se busca"]):
        return "comprador"
    return "vendedor"


def fetch_duckduckgo(con) -> list[dict]:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        log.error("duckduckgo-search no instalado. Ejecutá: pip install duckduckgo-search")
        return []

    # Calcular qué queries correr en este ciclo (rotación por total acumulado)
    row = con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM serp_uso").fetchone()
    total_ciclos = row[0] or 0
    n = len(QUERIES_DDG)
    inicio = (total_ciclos * QUERIES_POR_CICLO) % n
    indices = [(inicio + i) % n for i in range(QUERIES_POR_CICLO)]
    queries_ciclo = [QUERIES_DDG[i] for i in indices]

    resultados = []
    ddgs = DDGS()

    for kw, region, tipo_forzado in queries_ciclo:
        try:
            hits = ddgs.text(kw, region=region, max_results=10) or []
            for res in hits:
                url_res = res.get("href", "")
                lid = f"ddg_{abs(hash(url_res + kw))}"
                if not es_nuevo(con, lid, "duckduckgo"):
                    continue
                marcar_visto(con, lid, "duckduckgo")
                titulo  = res.get("title", "")
                snippet = res.get("body", "")
                tipo    = _detectar_tipo(titulo, snippet, tipo_forzado)
                resultados.append({
                    "id":        lid,
                    "fuente":    "Web",
                    "tipo":      tipo,
                    "titulo":    titulo,
                    "precio":    None,
                    "moneda":    "ARS",
                    "url":       url_res,
                    "imagen":    "",
                    "ubicacion": region.split("-")[0].upper(),
                    "keyword":   kw,
                    "raw":       json.dumps({
                        "title":   titulo,
                        "snippet": snippet,
                        "url":     url_res,
                        "region":  region,
                        "tipo":    tipo,
                    }, ensure_ascii=False)[:600],
                })
            time.sleep(1.5)
        except Exception as e:
            log.warning(f"DDG '{kw}': {e}")
            time.sleep(3.0)

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()

    log.info(
        f"DDG: {len(resultados)} nuevos "
        f"(queries {inicio}-{(inicio + QUERIES_POR_CICLO - 1) % n} de {n} total)"
    )
    return resultados


def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()
    todos = fetch_duckduckgo(con)
    con.close()
    log.info(f"TOTAL nuevos este ciclo: {len(todos)}")
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r, ensure_ascii=False, indent=2))
