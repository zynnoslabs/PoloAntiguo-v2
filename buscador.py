"""
buscador.py — Polo Antiguo v2
Fuente: MercadoLibre web (HTML scraping, sin API ni OAuth)
Costo: $0 — sin registro, sin variables de entorno extra.
4 queries × ciclo de 90min → cobertura amplia, sin saturar ML.
"""
import re, json, time, logging, requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

# ### CAMBIO AQUÍ ### Headers para que ML nos trate como browser normal
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
}

# ### CAMBIO AQUÍ ### 28 queries para ML — cosas que la gente LISTA en ML
QUERIES = [
    # ═══ RELOJES ═══
    ("reloj longines bolsillo antiguo",          "vendedor"),
    ("reloj omega antiguo usado coleccion",      "vendedor"),
    ("reloj suizo bolsillo antiguo plata",       "vendedor"),
    ("reloj iwc vacheron antiguo",               "vendedor"),
    ("reloj de bolsillo antiguo dorado",         "vendedor"),
    ("reloj pulsera antiguo art deco",           "vendedor"),
    # ═══ JOYERÍA ═══
    ("joyeria plata antigua collar pulsera",     "vendedor"),
    ("pulsera plata antigua artesanal",          "vendedor"),
    ("anillo plata antiguo piedra",              "vendedor"),
    # ═══ MILITARIA ═══
    ("sable militar antiguo",                    "vendedor"),
    ("pistola antigua coleccion argentina",      "vendedor"),
    ("condecoración medalla militar antigua",    "vendedor"),
    ("kepis uniforme militar antiguo",           "vendedor"),
    # ═══ PLATERÍA CRIOLLA ═══
    ("mate plata antiguo bombilla",              "vendedor"),
    ("plateria criolla antigua cubiertos",       "vendedor"),
    ("bandeja plata antigua argentina",          "vendedor"),
    ("candelabro plata antiguo",                 "vendedor"),
    # ═══ AUDIO / RADIO ═══
    ("radio antigua valvulas coleccion",         "vendedor"),
    ("gramofono vitrola antiguo",                "vendedor"),
    ("parlante antiguo vintage",                 "vendedor"),
    # ═══ ARTE Y DECORACIÓN ═══
    ("bronce decorativo antiguo figura",         "vendedor"),
    ("cuadro pintura antigua firma",             "vendedor"),
    ("lampara antiguo art nouveau deco",         "vendedor"),
    ("aranha cristal antigua antigua",           "vendedor"),
    # ═══ MUEBLES ═══
    ("mueble antiguo luis xv xvi",               "vendedor"),
    ("escritorio antiguo madera",                "vendedor"),
    # ═══ NUMISMÁTICA ═══
    ("monedas argentinas antiguas coleccion",    "vendedor"),
    ("billetes antiguos argentina coleccionista","vendedor"),
]

QUERIES_POR_CICLO = 4   # 16 ciclos/día × 4 = 64 requests/día — muy razonable para ML


def _slug(kw: str) -> str:
    """'reloj longines antiguo' → 'reloj-longines-antiguo'"""
    s = re.sub(r'[^a-záéíóúñüa-z0-9\s]', '', kw.lower())
    return re.sub(r'\s+', '-', s.strip())


def _extraer_items(soup: BeautifulSoup, kw: str, tipo: str, con) -> list[dict]:
    """Extrae listados de una página de resultados de ML."""
    resultados = []

    # ML usa <li class="ui-search-layout__item ..."> para cada producto
    items = soup.find_all('li', class_=re.compile(r'ui-search-layout__item'))
    if not items:
        # Fallback: cualquier <article> con precio
        items = soup.find_all('article')

    for item in items[:12]:
        # ── URL y Título ────────────────────────────────────────────────
        link = (
            item.find('a', class_=re.compile(r'poly-component__title|ui-search-item__title')) or
            item.find('a', class_=re.compile(r'title')) or
            item.find('a', href=re.compile(r'mercadolibre'))
        )
        if not link:
            continue

        url_item = link.get('href', '')
        titulo   = link.get_text(strip=True) or link.get('aria-label', '')

        # Limpiar URL (quitar parámetros de tracking)
        url_clean = re.split(r'[?#]', url_item)[0] if url_item else ''
        if not url_clean or 'mercadolibre' not in url_clean:
            continue

        lid = f"ml_{abs(hash(url_clean))}"
        if not es_nuevo(con, lid, 'ml'):
            continue
        marcar_visto(con, lid, 'ml')

        # ── Precio ──────────────────────────────────────────────────────
        precio_tag = item.find('span', class_=re.compile(r'fraction|amount__fraction'))
        precio = precio_tag.get_text(strip=True) if precio_tag else None

        resultados.append({
            "id":        lid,
            "fuente":    "MercadoLibre",
            "tipo":      tipo,
            "titulo":    titulo[:200],
            "precio":    precio,
            "moneda":    "ARS",
            "url":       url_clean,
            "imagen":    "",
            "ubicacion": "AR",
            "keyword":   kw,
            "raw":       json.dumps({
                "title": titulo,
                "price": precio,
                "url":   url_clean,
                "tipo":  tipo,
            }, ensure_ascii=False)[:600],
        })

    return resultados


def fetch_ml(con) -> list[dict]:
    """Scrapea ML web para las queries del ciclo actual."""
    row    = con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM serp_uso").fetchone()
    total  = row[0] or 0
    n      = len(QUERIES)
    inicio = (total * QUERIES_POR_CICLO) % n
    indices = [(inicio + i) % n for i in range(QUERIES_POR_CICLO)]

    sess = requests.Session()
    sess.headers.update(HEADERS)

    resultados = []

    for idx in indices:
        kw, tipo = QUERIES[idx]
        slug = _slug(kw)
        url  = f"https://listado.mercadolibre.com.ar/{slug}"

        try:
            r = sess.get(url, timeout=15)
            r.raise_for_status()

            soup  = BeautifulSoup(r.text, 'html.parser')
            items = _extraer_items(soup, kw, tipo, con)
            resultados.extend(items)
            log.info(f"ML '{kw[:45]}': {len(items)} nuevos")

        except Exception as e:
            log.warning(f"ML '{kw[:45]}': {e}")

        time.sleep(2.5)   # pausa entre requests para no saturar ML

    # Registrar ciclo
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()

    log.info(f"ML web — total nuevos este ciclo: {len(resultados)} "
             f"(queries {inicio}–{(inicio + QUERIES_POR_CICLO - 1) % n} de {n})")
    return resultados


def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()
    todos = fetch_ml(con)
    con.close()
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r[:3], ensure_ascii=False, indent=2))
    print(f"Total: {len(r)}")
