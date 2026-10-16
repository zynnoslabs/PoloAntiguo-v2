"""
db.py — Polo Antiguo v2
Base de datos: PostgreSQL via Neon (psycopg2).
Conexión: variable de entorno DATABASE_URL.
"""
import os, psycopg2, logging
from datetime import datetime, timezone

log = logging.getLogger("db")

DATABASE_URL = os.environ.get("DATABASE_URL", "")


# ── Emulación de sqlite3.Row ──────────────────────────────────────────────────
# Permite acceso por índice entero, por nombre de columna y dict()
# sin cambiar ningún otro archivo del proyecto.

class _Row:
    def __init__(self, row_tuple, cols):
        self._t = row_tuple
        self._c = cols

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._t[key]
        return self._t[self._c.index(key)]

    def keys(self):           return list(self._c)
    def __iter__(self):       return iter(self._t)
    def __len__(self):        return len(self._t)


class _Cursor:
    def __init__(self, pg_cur):
        self._cur = pg_cur

    def _cols(self):
        return [d[0] for d in self._cur.description] if self._cur.description else []

    def fetchone(self):
        row = self._cur.fetchone()
        return _Row(row, self._cols()) if row is not None else None

    def fetchall(self):
        cols = self._cols()
        return [_Row(r, cols) for r in self._cur.fetchall()]

    def __iter__(self):
        cols = self._cols()
        for r in self._cur:
            yield _Row(r, cols)


class _Con:
    """Wrapper que expone la misma API que sqlite3.Connection."""
    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql: str, params=()):
        cur = self._conn.cursor()
        cur.execute(sql.replace("?", "%s"), params)   # ### CAMBIO AQUÍ ### — ? → %s
        return _Cursor(cur)

    def executescript(self, script: str):
        cur = self._conn.cursor()
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        self._conn.commit()

    def commit(self):    self._conn.commit()
    def close(self):     self._conn.close()


# ── Conexión ──────────────────────────────────────────────────────────────────

def get_con() -> _Con:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no configurada — agregala en Render → Environment.")
    conn = psycopg2.connect(DATABASE_URL)
    return _Con(conn)


# ── Tablas ────────────────────────────────────────────────────────────────────

def init_db():
    con = get_con()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS listados (
            id          TEXT PRIMARY KEY,
            fuente      TEXT,
            tipo        TEXT,
            titulo      TEXT,
            precio      REAL,
            moneda      TEXT DEFAULT 'ARS',
            url         TEXT,
            imagen      TEXT,
            ubicacion   TEXT,
            keyword     TEXT,
            relevante   INTEGER DEFAULT 0,
            score       INTEGER DEFAULT 0,
            categoria   TEXT DEFAULT 'otro',
            razon       TEXT,
            mensaje_wa  TEXT,
            visto_en    TEXT,
            leido       INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS vistos (
            id       TEXT,
            fuente   TEXT,
            visto_en TEXT,
            PRIMARY KEY (id, fuente)
        );
        CREATE TABLE IF NOT EXISTS serp_uso (
            fecha    TEXT PRIMARY KEY,
            cantidad INTEGER DEFAULT 0
        )
    """)
    con.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def es_nuevo(con, listing_id: str, fuente: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM vistos WHERE id=? AND fuente=?", (listing_id, fuente)
    ).fetchone()
    return row is None


def marcar_visto(con, listing_id: str, fuente: str):
    ahora = datetime.now(timezone.utc).isoformat()
    con.execute(
        # ### CAMBIO AQUÍ ### — INSERT OR IGNORE → ON CONFLICT DO NOTHING (PostgreSQL)
        "INSERT INTO vistos(id,fuente,visto_en) VALUES(?,?,?) ON CONFLICT DO NOTHING",
        (listing_id, fuente, ahora)
    )
    con.commit()


def guardar_listado(item: dict):
    con = get_con()
    ahora = datetime.now(timezone.utc).isoformat()
    con.execute("""
        INSERT INTO listados
        (id,fuente,tipo,titulo,precio,moneda,url,imagen,ubicacion,keyword,
         relevante,score,categoria,razon,mensaje_wa,visto_en)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT (id) DO UPDATE SET
            relevante  = EXCLUDED.relevante,
            score      = EXCLUDED.score,
            categoria  = EXCLUDED.categoria,
            razon      = EXCLUDED.razon,
            mensaje_wa = EXCLUDED.mensaje_wa,
            visto_en   = EXCLUDED.visto_en
    """, (
        item.get("id"), item.get("fuente"), item.get("tipo"),
        item.get("titulo"), item.get("precio"), item.get("moneda","ARS"),
        item.get("url"), item.get("imagen",""), item.get("ubicacion",""),
        item.get("keyword",""), int(item.get("relevante", False)),
        item.get("score",0), item.get("categoria","otro"),
        item.get("razon",""), item.get("mensaje_wa",""), ahora
    ))
    con.commit()
    con.close()
