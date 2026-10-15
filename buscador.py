"""
buscador.py — Polo Antiguo v2
Fuente: MercadoLibre API (OAuth Client Credentials — app gratuita).
~32 queries cubriendo todas las categorías. Rota 8 por ciclo.
Requiere: ML_CLIENT_ID y ML_CLIENT_SECRET en variables de entorno Render.
"""
import os, json, time, logging, requests
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

ML_TOKEN_URL  = "https://api.mercadolibre.com/oauth/token"
ML_SEARCH_URL = "https://api.mercadolibre.com/sites/{site}/search"

# Cache del token en memoria (expira cada ~6h, ML lo renueva automático)
_ml_token: str | None = None
_ml_token_expires: float = 0.0


def _get_ml_token() -> str | None:
    """Obtiene o renueva el access token de MercadoLibre."""
    global _ml_token, _ml_token_expires
    if _ml_token and time.time() < _ml_token_expires - 300:
        return _ml_token
    cid     = os.environ.get("ML_CLIENT_ID", "")
    csecret = os.environ.get("ML_CLIENT_SECRET", "")
    if not cid or not csecret:
        log.error("ML_CLIENT_ID / ML_CLIENT_SECRET no configurados en Render.")
        return None
    try:
        r = requests.post(
            ML_TOKEN_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     cid,
                "client_secret": csecret,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        _ml_token         = data["access_token"]
        _ml_token_expires = time.time() + data.get("expires_in", 21600)
        log.info("ML token renovado OK")
        return _ml_token
    except Exception as e:
        log.error(f"Error obteniendo ML token: {e}")
        return None


# ### CAMBIO AQUÍ ### 32 queries MercadoLibre Argentina + España
QUERIES_ML = [
    # ═══ RELOJES Y JOYERÍA ═══
    ("reloj longines antiguo bolsillo",          "MLA", "reloj"),
    ("reloj omega antiguo bolsillo",             "MLA", "reloj"),
    ("reloj suizo antiguo pulsera",              "MLA", "reloj"),
    ("reloj de bolsillo antiguo coleccion",      "MLA", "reloj"),
    ("reloj iwc vacheron antiguo",               "MLA", "reloj"),
    ("joyeria plata antigua collar pulsera",     "MLA", "joyeria"),

    # ═══ MILITARIA ═══
    ("sable militar antiguo argentina",          "MLA", "militaria"),
    ("militaria condecoracion medalla antigua",  "MLA", "militaria"),
    ("pistola antigua ejercito argentino",       "MLA", "militaria"),
    ("uniforme militar antiguo",                 "MLA", "militaria"),

    # ═══ PLATERÍA ═══
    ("mate plata antiguo",                       "MLA", "plata"),
    ("plateria criolla bombilla plata",          "MLA", "plata"),
    ("cubiertos plata antigua",                  "MLA", "plata"),
    ("candelabro plata antiguo",                 "MLA", "plata"),

    # ═══ AUDIO ═══
    ("radio valvulas antigua",                   "MLA", "radio"),
    ("gramofono antiguo vitrola",                "MLA", "radio"),
    ("fonografo antiguo",                        "MLA", "radio"),

    # ═══ NÁUTICA ═══
    ("brujula nautica antigua",                  "MLA", "nautica"),
    ("sextante antiguo",                         "MLA", "nautica"),
    ("cronometro marino antiguo",                "MLA", "nautica"),

    # ═══ ARTE Y BRONCE ═══
    ("bronce decorativo antiguo figura",         "MLA", "arte"),
    ("escultura marmol antigua",                 "MLA", "arte"),
    ("cuadro pintura antigua firma",             "MLA", "arte"),

    # ═══ MUEBLES E ILUMINACIÓN ═══
    ("mueble antiguo luis xv estilo europeo",    "MLA", "mueble"),
    ("lampara art nouveau antigua",              "MLA", "iluminacion"),
    ("arana cristal antigua",                    "MLA", "iluminacion"),

    # ═══ NUMISMÁTICA ═══
    ("monedas argentinas antiguas coleccion",    "MLA", "monedas"),
    ("billetes antiguos argentina",              "MLA", "monedas"),

    # ═══ PORCELANA ═══
    ("porcelana meissen limoges antigua",        "MLA", "porcelana"),
    ("cristal baccarat antiguo",                 "MLA", "porcelana"),

    # ═══ EXTRAS ESPAÑA ═══
    ("reloj longines antiguo bolsillo",          "MLE", "reloj"),
    ("militaria antigua sable espada coleccion", "MLE", "militaria"),
]

QUERIES_POR_CICLO = 8


def fetch_mercadolibre(con) -> list[dict]:
    token = _get_ml_token()
    if not token:
        log.warning("Sin token ML — saltando ciclo.")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    sess = requests.Session()
    sess.headers.update(headers)

    # Calcular rotación
    row = con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM serp_uso").fetchone()
    total_ciclos = row[0] or 0
    n = len(QUERIES_ML)
    inicio = (total_ciclos * QUERIES_POR_CICLO) % n
    indices = [(inicio + i) % n for i in range(QUERIES_POR_CICLO)]
    queries_ciclo = [QUERIES_ML[i] for i in indices]

    resultados = []
    for kw, site, cat_hint in queries_ciclo:
        try:
            params = {"q": kw, "limit": 20}
            if site == "MLA":
                params["condition"] = "used"
            r = sess.get(ML_SEARCH_URL.format(site=site), params=params, timeout=15)
            r.raise_for_status()
            items = r.json().get("results", [])

            nuevos_query = 0
            for item in items:
                ml_id = item.get("id", "")
                lid = f"ml_{ml_id}"
                if not ml_id or not es_nuevo(con, lid, "mercadolibre"):
                    continue
                marcar_visto(con, lid, "mercadolibre")
                precio    = item.get("price")
                moneda    = item.get("currency_id", "ARS")
                ubicacion = (item.get("seller_address") or {}).get("state", {}).get("name", "")
                resultados.append({
                    "id":        lid,
                    "fuente":    "MercadoLibre",
                    "tipo":      "vendedor",
                    "titulo":    item.get("title", ""),
                    "precio":    precio,
                    "moneda":    moneda,
                    "url":       item.get("permalink", ""),
                    "imagen":    item.get("thumbnail", ""),
                    "ubicacion": ubicacion,
                    "keyword":   kw,
                    "raw":       json.dumps({
                        "title": item.get("title"), "price": precio,
                        "currency": moneda, "url": item.get("permalink"),
                        "ubicacion": ubicacion, "site": site,
                    }, ensure_ascii=False)[:600],
                })
                nuevos_query += 1

            log.info(f"ML [{site}] '{kw}': {len(items)} items, {nuevos_query} nuevos")
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
    log.info(f"ML total nuevos: {len(resultados)} (queries {inicio}–{(inicio + QUERIES_POR_CICLO - 1) % n} de {n})")
    return resultados


def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()
    todos = fetch_mercadolibre(con)
    con.close()
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r, ensure_ascii=False, indent=2))
