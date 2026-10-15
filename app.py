"""
app.py — Polo Antiguo v2
Dashboard web para Juan Carlos + API + scheduler automático.
"""
import os, logging
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from db import init_db, get_con
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "polo-antiguo-dev-secret-2024")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "polo2024")

# ─── Scheduler ────────────────────────────────────────────────────────────────
def _ciclo():
    try:
        from main import ciclo_completo
        ciclo_completo()
    except Exception as e:
        log.error(f"Error en ciclo automático: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(_ciclo, "interval", minutes=90, id="ciclo_polo", misfire_grace_time=300)  # ### CAMBIO AQUÍ ### 90min: 4 queries×16 ciclos=64/día < límite Brave
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ─── Helpers DB ───────────────────────────────────────────────────────────────
CATEGORIAS = ["reloj","militaria","plata","monedas","mueble","porcelana","bronce","radio","nautica","arte","iluminacion","otro"]  ### CAMBIO AQUI ###

def get_listados(tipo=None, categoria=None, solo_relevantes=True, limite=150):
    con = get_con()
    q = "SELECT * FROM listados WHERE 1=1"
    params = []
    if solo_relevantes:
        q += " AND relevante=1"
    if tipo and tipo not in ("todos", ""):
        q += " AND tipo=?"
        params.append(tipo)
    if categoria and categoria not in ("todas", "todos", ""):
        q += " AND categoria=?"
        params.append(categoria)
    q += " ORDER BY score DESC, visto_en DESC LIMIT ?"
    params.append(limite)
    rows = con.execute(q, params).fetchall()
    con.close()
    return [dict(r) for r in rows]

def get_stats():
    from datetime import datetime, timezone
    con = get_con()
    total   = con.execute("SELECT COUNT(*) FROM listados").fetchone()[0]
    relev   = con.execute("SELECT COUNT(*) FROM listados WHERE relevante=1").fetchone()[0]
    no_leid = con.execute("SELECT COUNT(*) FROM listados WHERE relevante=1 AND leido=0").fetchone()[0]
    hoy_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hoy_uso = con.execute(
        "SELECT COALESCE(SUM(cantidad),0) FROM serp_uso WHERE fecha=?", (hoy_str,)
    ).fetchone()[0]
    ultima  = con.execute("SELECT MAX(visto_en) FROM listados").fetchone()[0]
    # por_categoria como dict {cat: count}
    rows_cat = con.execute("""
        SELECT categoria, COUNT(*) as n FROM listados
        WHERE relevante=1 GROUP BY categoria ORDER BY n DESC
    """).fetchall()
    por_cat = {r[0]: r[1] for r in rows_cat}
    con.close()
    return {
        "total": total,
        "relevantes": relev,
        "no_leidos": no_leid,
        "serp_hoy": hoy_uso,
        "ultima_busqueda": (ultima or "")[:16].replace("T", " ") if ultima else "—",
        "por_categoria": por_cat,
    }

# ─── Variables de entorno para la tabla admin ─────────────────────────────────
ENV_VARS_INFO = [
    ("GROQ_API_KEY",   "API key de Groq (análisis con IA)"),
    # Sin variables extra — ML web scraping no requiere auth
    ("EMAIL_FROM",     "Cuenta Gmail para enviar resúmenes"),
    ("EMAIL_PASS",     "Contraseña de aplicación Gmail"),
    ("EMAIL_TO",       "Destinatario del resumen por email"),
    ("ADMIN_PASS",     "Contraseña del panel de admin"),
    ("SECRET_KEY",     "Clave secreta Flask (sesiones)"),
]

def get_env_vars():
    return [
        {"name": name, "desc": desc, "set": bool(os.environ.get(name))}
        for name, desc in ENV_VARS_INFO
    ]

# ─── Rutas ────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    tipo      = request.args.get("tipo", "todos")
    categoria = request.args.get("cat", "todas")
    listados  = get_listados(tipo=tipo, categoria=categoria)
    stats     = get_stats()
    return render_template(
        "dashboard.html",
        listados=listados,
        oportunidades_count=stats["no_leidos"],
        ultima_busqueda=stats["ultima_busqueda"],
        categorias=CATEGORIAS,
        tipo_activo=tipo,
        cat_activa=categoria,
    )

@app.route("/api/marcar-leido/<lid>", methods=["POST"])
def marcar_leido_api(lid):
    con = get_con()
    con.execute("UPDATE listados SET leido=1 WHERE id=?", (lid,))
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.route("/api/correr-ciclo", methods=["POST"])
def correr_ciclo():
    if not session.get("admin"):
        return jsonify({"error": "no autorizado"}), 403
    import threading
    t = threading.Thread(target=_ciclo, daemon=True)
    t.start()
    return jsonify({"ok": True, "msg": "Ciclo iniciado en background"})

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Contraseña incorrecta", "error")
        return render_template("login.html")
    if not session.get("admin"):
        return render_template("login.html")
    stats    = get_stats()
    env_vars = get_env_vars()
    return render_template("admin.html", stats=stats, env_vars=env_vars)

@app.route("/api/stats")
def api_stats():
    """Polling del frontend para saber cuándo terminó el ciclo manual."""  # ### CAMBIO AQUÍ ###
    return jsonify(get_stats())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))

# ─── Init & run ───────────────────────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
