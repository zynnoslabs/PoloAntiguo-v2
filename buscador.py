"""
buscador.py — Polo Antiguo v2

Fuentes (en orden de prioridad):
  1. MercadoLibre API  — listings reales con precio.  Requiere cuenta ML gratis:
       - Registrar app en https://developers.mercadolibre.com.ar
       - Agregar MELI_CLIENT_ID y MELI_CLIENT_SECRET en Render → Environment
       - Sin esas vars, ML queda deshabilitado sin error.
  2. Google News RSS   — sin API key, sin cuota, siempre activo como respaldo.
       - Encuentra artículos y posts; la IA filtra lo irrelevante.
"""
import os, json, time, logging, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_SEARCH_URL = "https://api.mercadolibre.com/sites/MLA/search"
GNEWS_URL     = "https://news.google.com/rss/search"

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
    ("liquidacion antiguedades herencia argentina",       "herencia"),
]

QUERIES_POR_CICLO = 4   # 4 × 16 ciclos/día = 64 llamadas/día por fuente


def _calcular_indices(con) -> tuple[list[int], int]:
    n     = len(QUERIES)
    total = con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM serp_uso").fetchone()[0] or 0
    ini   = (total * QUERIES_POR_CICLO) % n
    return [(ini + i) % n for i in range(QUERIES_POR_CICLO)], ini


# ── MercadoLibre ──────────────────────────────────────────────────────────────

def _ml_token(client_id: str, client_secret: str) -> str:
    """Obtiene access_token via client_credentials (dura ~6 h)."""
    try:
        r = requests.post(ML_TOKEN_URL, data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
        }, timeout=10)
        r.raise_for_status()
        return r.json().get("access_token", "")
    except Exception as e:
        log.warning(f"ML token error: {e}")
        return ""


def fetch_ml(con, indices: list[int]) -> list[dict]:
    """MercadoLibre — activo solo si MELI_CLIENT_ID y MELI_CLIENT_SECRET están configurados."""
    client_id     = os.environ.get("MELI_CLIENT_ID", "")
    client_secret = os.environ.get("MELI_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        log.info("ML deshabilitado (MELI_CLIENT_ID/SECRET no configurados — ver /admin)")
        return []

    token = _ml_token(client_id, client_secret)
    if not token:
        log.warning("ML: no se pudo obtener token OAuth")
        return []

    sess = requests.Session()
    sess.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
        "User-Agent":    "PoloAntiguoBot/1.0",
    })
    resultados = []

    for idx in indices:
        kw, tipo = QUERIES[idx]
        try:
            r = sess.get(ML_SEARCH_URL, params={
                "q":     kw,
                "limit": 50,
                "sort":  "date_asc",
            }, timeout=15)
            r.raise_for_status()
            items = r.json().get("results", [])

            nuevos = 0
            for it in items:
                url_i  = it.get("permalink", "")
                titulo = it.get("title", "")
                if not url_i or not titulo:
                    continue
                url_c    = url_i.split("?")[0]
                precio   = it.get("price")
                moneda   = it.get("currency_id", "ARS")
                imagen   = it.get("thumbnail", "")
                ubicacion = (it.get("address") or {}).get("state_name", "AR")
                lid      = f"ml_{it.get('id', abs(hash(url_c)))}"
                if not es_nuevo(con, lid, "ml"):
                    continue
                marcar_visto(con, lid, "ml")
                resultados.append({
                    "id":        lid,
                    "fuente":    "ML",
                    "tipo":      tipo,
                    "titulo":    titulo[:200],
                    "precio":    precio,
                    "moneda":    moneda,
                    "url":       url_c,
                    "imagen":    imagen,
                    "ubicacion": ubicacion,
                    "keyword":   kw,
                    "raw":       json.dumps({
                        "title":    titulo,
                        "price":    precio,
                        "currency": moneda,
                        "url":      url_c,
                        "tipo":     tipo,
                        "location": ubicacion,
                    }, ensure_ascii=False)[:600],
                })
                nuevos += 1

            log.info(f"ML '{kw[:42]}': {len(items)} resultados, {nuevos} nuevos")
            time.sleep(0.3)

        except Exception as e:
            log.warning(f"ML error '{kw[:42]}': {e}")
            time.sleep(2.0)

    return resultados


# ── Google News RSS ───────────────────────────────────────────────────────────

def fetch_gnews(con, indices: list[int]) -> list[dict]:
    """Google News RSS — siempre activo, sin API key ni cuota."""
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

            log.info(f"GNews '{kw[:42]}': {len(items)} resultados, {nuevos} nuevos")
            time.sleep(0.3)

        except Exception as e:
            log.warning(f"GNews error '{kw[:42]}': {e}")
            time.sleep(2.0)

    return resultados


# ── Orquestador ───────────────────────────────────────────────────────────────

def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()

    indices, inicio = _calcular_indices(con)
    n = len(QUERIES)

    todos  = fetch_ml(con, indices)
    todos += fetch_gnews(con, indices)

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()

    log.info(f"Ciclo total: {len(todos)} nuevos — queries {inicio}–{(inicio+QUERIES_POR_CICLO-1)%n}/{n}")
    con.close()
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r[:3], ensure_ascii=False, indent=2))
    print(f"Total: {len(r)}")
