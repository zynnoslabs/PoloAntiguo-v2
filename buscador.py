"""
buscador.py — Polo Antiguo v2
Fuente: MercadoLibre web (HTML scraping, sin API ni OAuth)
Costo: $0 — sin registro, sin variables de entorno.
"""
import re, json, time, logging, requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from db import get_con, es_nuevo, marcar_visto

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("buscador")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.mercadolibre.com.ar/",
}

QUERIES = [
    ("reloj longines bolsillo antiguo",           "vendedor"),
    ("reloj omega antiguo usado coleccion",       "vendedor"),
    ("reloj suizo bolsillo antiguo plata",        "vendedor"),
    ("reloj iwc vacheron antiguo",                "vendedor"),
    ("reloj de bolsillo antiguo dorado",          "vendedor"),
    ("reloj pulsera antiguo art deco",            "vendedor"),
    ("joyeria plata antigua collar pulsera",      "vendedor"),
    ("pulsera plata antigua artesanal",           "vendedor"),
    ("anillo plata antiguo piedra",               "vendedor"),
    ("sable militar antiguo",                     "vendedor"),
    ("pistola antigua coleccion argentina",       "vendedor"),
    ("condecoración medalla militar antigua",     "vendedor"),
    ("mate plata antiguo bombilla",               "vendedor"),
    ("plateria criolla antigua cubiertos",        "vendedor"),
    ("bandeja plata antigua argentina",           "vendedor"),
    ("candelabro plata antiguo",                  "vendedor"),
    ("radio antigua valvulas coleccion",          "vendedor"),
    ("gramofono vitrola antiguo",                 "vendedor"),
    ("bronce decorativo antiguo figura",          "vendedor"),
    ("cuadro pintura antigua firma",              "vendedor"),
    ("lampara antiguo art nouveau deco",          "vendedor"),
    ("arania cristal antigua decoracion",         "vendedor"),
    ("mueble antiguo luis xv xvi",                "vendedor"),
    ("escritorio antiguo madera",                 "vendedor"),
    ("monedas argentinas antiguas coleccion",     "vendedor"),
    ("billetes antiguos argentina coleccionista", "vendedor"),
    ("brujula sexante antiguo coleccion",         "vendedor"),
    ("kepis uniforme militar antiguo",            "vendedor"),
]

QUERIES_POR_CICLO = 4


def _slug(kw: str) -> str:
    s = re.sub(r'[^a-záéíóúñüa-z0-9\s]', '', kw.lower())
    return re.sub(r'\s+', '-', s.strip())


def _extraer_items(soup: BeautifulSoup, kw: str, tipo: str, con, page_url: str) -> list[dict]:
    """Extrae listados usando múltiples estrategias."""
    resultados = []

    # ── Diagnóstico: título de página y cantidad de links ─────────────────────
    title_tag = soup.find('title')
    page_title = title_tag.get_text(strip=True) if title_tag else '(sin título)'
    # Buscar links que apunten a páginas de artículo de ML
    # ### CAMBIO AQUÍ ### — múltiples patrones de URL de ML
    ml_links = soup.find_all('a', href=re.compile(
        r'(articulo\.mercadolibre|www\.mercadolibre\.com\.ar/[^"]+MLA|'
        r'www\.mercadolibre\.com\.ar/[^"]+\-_JM)',
        re.I
    ))
    log.info(f"  '{kw[:40]}' → página: '{page_title[:60]}' | links ML: {len(ml_links)}")

    if not ml_links:
        # Última estrategia: CUALQUIER link con mercadolibre en el href
        ml_links = [a for a in soup.find_all('a', href=True)
                    if 'mercadolibre' in a.get('href', '') and len(a.get_text(strip=True)) > 5]
        if ml_links:
            log.info(f"  fallback links ML: {len(ml_links)}")

    seen_urls = set()
    for link in ml_links[:15]:
        url_item = link.get('href', '')
        # Limpiar URL
        url_clean = re.split(r'[?#]', url_item)[0]
        if not url_clean or url_clean in seen_urls:
            continue
        seen_urls.add(url_clean)

        # Título: texto del link, o aria-label, o texto del heading más cercano
        titulo = (
            link.get('aria-label', '') or
            link.get_text(strip=True) or
            link.find_parent(['h2', 'h3', 'h4']) and link.find_parent(['h2', 'h3', 'h4']).get_text(strip=True) or
            ''
        )
        if len(titulo) < 5:
            continue

        lid = f"ml_{abs(hash(url_clean))}"
        if not es_nuevo(con, lid, 'ml'):
            continue
        marcar_visto(con, lid, 'ml')

        # Precio: buscar span de precio cerca del link
        container = link.find_parent(['li', 'article', 'div'], class_=re.compile(r'item|card|product|result', re.I))
        precio = None
        if container:
            p_tag = container.find('span', class_=re.compile(r'fraction|amount|price', re.I))
            if p_tag:
                precio = p_tag.get_text(strip=True)

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
                "title": titulo, "price": precio,
                "url": url_clean, "tipo": tipo,
            }, ensure_ascii=False)[:600],
        })

    return resultados


# ### CAMBIO AQUÍ ### — también busca en JSON-LD incrustado en el HTML
def _extraer_jsonld(soup: BeautifulSoup, kw: str, tipo: str, con) -> list[dict]:
    """Extrae listados del JSON-LD que ML incrusta para SEO."""
    resultados = []
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string or '')
            items = []
            if isinstance(data, list):
                items = data
            elif data.get('@type') == 'ItemList':
                items = data.get('itemListElement', [])

            for item in items:
                thing = item.get('item', item)
                name  = thing.get('name', '')
                url_i = thing.get('url', '')
                price = thing.get('offers', {}).get('price') if isinstance(thing.get('offers'), dict) else None
                if not name or not url_i:
                    continue
                url_c = re.split(r'[?#]', url_i)[0]
                lid   = f"ml_{abs(hash(url_c))}"
                if not es_nuevo(con, lid, 'ml'):
                    continue
                marcar_visto(con, lid, 'ml')
                resultados.append({
                    "id": lid, "fuente": "MercadoLibre",
                    "tipo": tipo, "titulo": name[:200],
                    "precio": str(price) if price else None,
                    "moneda": "ARS", "url": url_c,
                    "imagen": "", "ubicacion": "AR",
                    "keyword": kw,
                    "raw": json.dumps({"title": name, "price": price, "url": url_c, "tipo": tipo}, ensure_ascii=False)[:600],
                })
        except Exception:
            pass
    if resultados:
        log.info(f"  JSON-LD encontró {len(resultados)} items")
    return resultados


def fetch_ml(con) -> list[dict]:
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
            r = sess.get(url, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')

            items = _extraer_jsonld(soup, kw, tipo, con)
            if not items:
                items = _extraer_items(soup, kw, tipo, con, url)
            resultados.extend(items)
            log.info(f"ML '{kw[:45]}': {len(items)} nuevos")
        except Exception as e:
            log.warning(f"ML '{kw[:45]}': {e}")

        time.sleep(2.5)

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()
    log.info(f"ML web — total nuevos ciclo: {len(resultados)} (queries {inicio}–{(inicio+QUERIES_POR_CICLO-1)%n}/{n})")
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
