"""
db.py — Polo Antiguo v2
Utilidades de base de datos compartidas entre todos los módulos.
"""
import sqlite3, os
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "db.sqlite")

def get_con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

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
        );
    """)
    con.commit()
    con.close()

def es_nuevo(con, listing_id: str, fuente: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM vistos WHERE id=? AND fuente=?", (listing_id, fuente)
    ).fetchone()
    return row is None

def marcar_visto(con, listing_id: str, fuente: str):
    ahora = datetime.now(timezone.utc).isoformat()
    con.execute(
        "INSERT OR IGNORE INTO vistos(id,fuente,visto_en) VALUES(?,?,?)",
        (listing_id, fuente, ahora)
    )
    con.commit()

def guardar_listado(item: dict):
    con = get_con()
    ahora = datetime.now(timezone.utc).isoformat()
    con.execute("""
        INSERT OR REPLACE INTO listados
        (id,fuente,tipo,titulo,precio,moneda,url,imagen,ubicacion,keyword,
         relevante,score,categoria,razon,mensaje_wa,visto_en)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
