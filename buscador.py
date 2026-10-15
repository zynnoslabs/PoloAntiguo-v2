"""
buscador.py — Polo Antiguo v2
Fuente: OLX Argentina (clasificados.olx.com.ar) — sin bot-blocking, gratis, sin auth.
4 queries por ciclo de 90 min.
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
}

# ### CAMBIO AQUÍ ### OLX tiene mejores vendedores de herencias y colecciones
QUERIES = [
    # ═══ RELOJES ═══
    ("reloj longines antiguo",               "vendedor"),
    ("reloj omega antiguo bolsillo",         "vendedor"),
    ("reloj suizo antiguo coleccion",        "vendedor"),
    ("reloj bolsillo antiguo plata",         "vendedor"),
    ("reloj antiguo art deco pulsera",       "vendedor"),
    # ═══ JOYERÍA ═══
    ("joyeria plata antigua",                "vendedor"),
    ("pulsera plata antigua artesanal",      "vendedor"),
    ("collar plata antiguo",                 "vendedor"),
    # ═══ MILITARIA ═══
    ("sable militar antiguo",                "vendedor"),
    ("militaria antigua argentina",          "vendedor"),
    ("pistola antigua coleccion",            "vendedor"),
    ("medalla militar antigua",              "vendedor"),
    # ═══ PLATERÍA ═══
    ("mate plata antiguo",                   "vendedor"),
    ("plateria criolla antigua",             "vendedor"),
    ("cubiertos plata antigua",              "vendedor"),
    ("bandeja plata antigua",                "vendedor"),
    # ═══ AUDIO ═══
    ("radio antigua valvulas",               "vendedor"),
    ("gramofono vitrola antiguo",            "vendedor"),
    # ═══ ARTE ═══
    ("bronce decorativo antiguo",            "vendedor"),
    ("cuadro pintura antigua",               "vendedor"),
    ("lampara antigua art nouveau",          "vendedor"),
    # ═══ MUEBLES ═══
    ("mueble antiguo luis xv",               "vendedor"),
    ("escritorio antiguo madera",            "vendedor"),
    # ═══ NUMISMÁTICA ═══
    ("monedas antiguas coleccion argentina", "vendedor"),
    ("billetes antiguos argentina",          "vendedor"),
    # ═══ HERENCIAS / SUCESIONES ═══
    ("antiguedades vendo lote herencia",     "herencia"),
    ("sucesion vendo antiguedades",          "herencia"),
    ("liquido contenido casa antigua",       "herencia"),
]

QUERIES_POR_CICLO = 4


def _slug(kw: str) -> str:
    s = re.sub(r'[áä]','a', re.sub(r'[éë]','e', re.sub(r'[íï]','i',
        re.sub(r'[óö]','o', re.sub(r'[úü]','u', re.sub(r'[ñ]','n', kw.lower()))))))
    s = re.sub(r'[^a-z0-9\s]', '', s)
    return re.sub(r'\s+', '-', s.strip())


def _extraer_olx(soup: BeautifulSoup, kw: str, tipo: str, con) -> list[dict]:
    title_tag = soup.find('title')
    page_title = title_tag.get_text(strip=True) if title_tag else '(sin título)'

    # ### CAMBIO AQUÍ ### OLX links tienen /item/ en la URL
    olx_links = soup.find_all('a', href=re.compile(r'/item/', re.I))
    log.info(f"  '{kw[:40]}' → '{page_title[:50]}' | items OLX: {len(olx_links)}")

    if not olx_links:
        # Fallback: links con dominio olx
        olx_links = [a for a in soup.find_all('a', href=True)
                     if 'olx.com.ar' in a.get('href','') and '/item/' in a.get('href','')]

    resultados = []
    seen = set()

    for link in olx_links[:15]:
        href = link.get('href', '')
        # Construir URL absoluta si es relativa
        if href.startswith('/'):
            href = 'https://www.olx.com.ar' + href
        url_clean = re.split(r'[?#]', href)[0]
        if not url_clean or url_clean in seen:
            continue
        seen.add(url_clean)

        # Título: texto del link o heading cercano
        titulo = link.get_text(strip=True)
        if not titulo or len(titulo) < 5:
            h = link.find(['h2', 'h3', 'span'])
            titulo = h.get_text(strip=True) if h else ''
        if not titulo or len(titulo) < 5:
            continue

        lid = f"olx_{abs(hash(url_clean))}"
        if not es_nuevo(con, lid, 'olx'):
            continue
        marcar_visto(con, lid, 'olx')

        # Precio: buscar en el contenedor del item
        container = link.find_parent(['li', 'article', 'div'])
        precio = None
        if container:
            p = container.find(string=re.compile(r'\$\s*[\d\.]+'))
            if p:
                precio = str(p).strip()

        resultados.append({
            "id":        lid,
            "fuente":    "OLX",
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


def fetch_olx(con) -> list[dict]:
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
        url  = f"https://www.olx.com.ar/q-{slug}/"

        try:
            r = sess.get(url, timeout=20)
            r.raise_for_status()
            soup  = BeautifulSoup(r.text, 'html.parser')
            items = _extraer_olx(soup, kw, tipo, con)
            resultados.extend(items)
            log.info(f"OLX '{kw[:45]}': {len(items)} nuevos")
        except Exception as e:
            log.warning(f"OLX '{kw[:45]}': {e}")

        time.sleep(2.0)

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con.execute("""
        INSERT INTO serp_uso(fecha, cantidad) VALUES(?, 1)
        ON CONFLICT(fecha) DO UPDATE SET cantidad = cantidad + 1
    """, (hoy,))
    con.commit()
    log.info(f"OLX — total nuevos ciclo: {len(resultados)} (queries {inicio}–{(inicio+QUERIES_POR_CICLO-1)%n}/{n})")
    return resultados


def buscar_todo() -> list[dict]:
    from db import init_db
    init_db()
    con = get_con()
    todos = fetch_olx(con)
    con.close()
    return todos


if __name__ == "__main__":
    r = buscar_todo()
    print(json.dumps(r[:3], ensure_ascii=False, indent=2))
    print(f"Total: {len(r)}")
