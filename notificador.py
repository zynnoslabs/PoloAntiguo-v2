"""
notificador.py — Polo Antiguo v2
Envía email diario a Juan Carlos con las oportunidades del día.
Requiere en Render: EMAIL_FROM, EMAIL_PASS, EMAIL_TO
"""
import os, smtplib, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

log = logging.getLogger("notificador")

CATEGORIA_EMOJI = {
    "reloj": "⌚", "militaria": "⚔️", "plata": "🥈",
    "monedas": "🪙", "mueble": "🪑", "porcelana": "🏺",
    "bronce": "🔔", "radio": "📻", "otro": "📦",
}

def enviar_resumen(relevantes: list[dict]):
    email_from = os.environ.get("EMAIL_FROM","")
    email_pass = os.environ.get("EMAIL_PASS","")
    email_to   = os.environ.get("EMAIL_TO","")
    if not all([email_from, email_pass, email_to]):
        log.info("Notificador: sin credenciales de email, saltando")
        return
    if not relevantes:
        log.info("Notificador: sin relevantes, no se envía email")
        return

    fecha = datetime.now().strftime("%d/%m/%Y")
    n = len(relevantes)

    # HTML del email
    cards_html = ""
    for item in relevantes:
        emoji = CATEGORIA_EMOJI.get(item.get("categoria","otro"), "📦")
        score = item.get("score", 0)
        color = "#7A2E1E" if item.get("tipo") == "vendedor" else "#2E5E4E"
        tipo_label = "VENDEDOR" if item.get("tipo") == "vendedor" else "COMPRADOR"
        precio_str = ""
        if item.get("precio"):
            precio_str = f"{item['moneda']} {item['precio']:,.0f}"

        wa_block = ""
        if item.get("mensaje_wa"):
            wa = item["mensaje_wa"].replace("\n","<br>")
            wa_block = f"""
            <div style="background:#f5f0e8;border-left:3px solid {color};
                        padding:10px 14px;margin-top:12px;font-size:13px;
                        font-family:Georgia,serif;color:#333;line-height:1.6">
              {wa}
            </div>"""

        cards_html += f"""
        <div style="border:1px solid #ddd;border-radius:4px;margin-bottom:16px;
                    border-left:4px solid {color};padding:16px;background:#fff">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:11px;font-weight:600;letter-spacing:.5px;
                         color:{color}">{tipo_label} · {emoji} {item.get('categoria','').upper()}</span>
            <span style="font-size:22px;font-weight:700;color:{color}">{score}<span style="font-size:13px;font-weight:400;color:#999">/10</span></span>
          </div>
          <div style="font-family:Georgia,serif;font-size:16px;margin:8px 0 4px;color:#1E1A17">
            {item.get('titulo','')}
          </div>
          <div style="font-size:12px;color:#888">
            {precio_str} {'· ' if precio_str else ''}{item.get('ubicacion','')}
          </div>
          <div style="font-size:12px;color:#666;margin-top:6px;font-style:italic">
            {item.get('razon','')}
          </div>
          {wa_block}
          <a href="{item.get('url','#')}"
             style="display:inline-block;margin-top:12px;font-size:12px;
                    color:{color};text-decoration:none">Ver publicación →</a>
        </div>"""

    html = f"""<!DOCTYPE html>
<html><body style="font-family:system-ui,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#EDEAE3">
  <div style="text-align:center;padding:24px 0 16px">
    <div style="font-family:Georgia,serif;font-size:28px;color:#1E1A17;letter-spacing:2px">
      POLO ANTIGUO
    </div>
    <div style="font-size:12px;color:#888;margin-top:4px">{fecha}</div>
  </div>
  <div style="background:#7A2E1E;color:#fff;text-align:center;padding:12px;
              border-radius:4px;margin-bottom:24px;font-family:Georgia,serif;font-size:16px">
    {n} oportunidad{'es' if n!=1 else ''} hoy
  </div>
  {cards_html}
  <div style="text-align:center;font-size:11px;color:#aaa;padding:20px 0">
    Polo Antiguo · Sistema automático de búsqueda
  </div>
</body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Polo Antiguo — {n} oportunidad{'es' if n!=1 else ''} · {fecha}"
        msg["From"] = email_from
        msg["To"] = email_to
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_from, email_pass)
            server.sendmail(email_from, email_to, msg.as_string())
        log.info(f"Email enviado a {email_to} con {n} oportunidades")
    except Exception as e:
        log.warning(f"Email error: {e}")
