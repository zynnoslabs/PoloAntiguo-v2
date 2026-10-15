/* app.js — Polo Antiguo v2 */

// ─── Toast ───────────────────────────────────────────────────────────────────
function showToast(msg) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 2600);
}

// ─── Copiar mensaje WhatsApp ──────────────────────────────────────────────────
function copiarWA(btn) {
  const card = btn.closest('.card');
  const msgEl = card.querySelector('.wa-msg');
  if (!msgEl) return;
  const texto = msgEl.textContent.trim();
  navigator.clipboard.writeText(texto)
    .then(() => showToast('✓ Mensaje copiado'))
    .catch(() => {
      // Fallback para HTTP
      const ta = document.createElement('textarea');
      ta.value = texto;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showToast('✓ Mensaje copiado');
    });
  marcarLeido(btn, card);
}

// ─── Marcar como leído ───────────────────────────────────────────────────────
function marcarLeido(btn, card) {
  if (!card) card = btn.closest('.card');
  const lid = card.dataset.id;
  if (!lid) return;
  fetch(`/api/marcar-leido/${lid}`, { method: 'POST' })
    .then(r => r.json())
    .then(() => {
      card.classList.add('leido');
      const badge = document.getElementById('oportunidades-count');
      if (badge) {
        const n = parseInt(badge.textContent) || 0;
        if (n > 0) badge.textContent = n - 1;
      }
    })
    .catch(() => showToast('Error al marcar'));
}

// ─── Filtros ─────────────────────────────────────────────────────────────────
function activarFiltro(btn) {
  const group = btn.closest('.filter-group');
  group.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  aplicarFiltros();
}

function aplicarFiltros() {
  const tipoActivo    = document.querySelector('.filter-tipo .pill.active')?.dataset.val    || 'todos';
  const catActiva     = document.querySelector('.filter-cat .pill.active')?.dataset.val     || 'todas';
  const soloNuevos    = document.getElementById('chk-nuevos')?.checked;

  document.querySelectorAll('.card').forEach(card => {
    const tipo = card.dataset.tipo || '';
    const cat  = card.dataset.cat  || '';
    const leido = card.classList.contains('leido');

    const okTipo  = tipoActivo  === 'todos'  || tipo === tipoActivo;
    const okCat   = catActiva   === 'todas'  || cat  === catActiva;
    const okNuevo = !soloNuevos || !leido;

    card.style.display = (okTipo && okCat && okNuevo) ? '' : 'none';
  });
}

// ─── Correr ciclo manual (admin) ─────────────────────────────────────────────
// ### CAMBIO AQUÍ ### timer visible + polling hasta que lleguen resultados
function correrCiclo() {
  const btn  = document.getElementById('btn-ciclo');
  const info = document.getElementById('ciclo-status');
  if (!btn) return;

  btn.disabled = true;
  btn.textContent = '⏳ Buscando…';

  let segundos = 0;
  let serpBase = null;
  let polling  = null;

  // Capturar el valor base antes de lanzar
  fetch('/api/stats').then(r => r.json()).then(s => {
    serpBase = s.serp_hoy || 0;
  }).catch(() => { serpBase = 0; });

  // Timer visible cada 1 segundo
  const timer = setInterval(() => {
    segundos++;
    const mm = String(Math.floor(segundos / 60)).padStart(2, '0');
    const ss = String(segundos % 60).padStart(2, '0');
    btn.textContent = '⏳ ' + mm + ':' + ss;
    if (info) {
      if (segundos < 30)       info.textContent = 'Consultando DuckDuckGo…';
      else if (segundos < 90)  info.textContent = 'IA analizando resultados con Groq…';
      else                     info.textContent = 'Guardando en base de datos…';
    }
    if (segundos >= 300) {
      clearInterval(timer);
      if (polling) clearInterval(polling);
      if (info) info.textContent = 'Tardó mucho — recargando igual.';
      setTimeout(() => location.reload(), 1500);
    }
  }, 1000);

  // Lanzar el ciclo
  fetch('/api/correr-ciclo', { method: 'POST' })
    .then(r => r.json())
    .then(() => {
      // Polling cada 15s hasta detectar que terminó
      polling = setInterval(() => {
        fetch('/api/stats').then(r => r.json()).then(s => {
          if (serpBase !== null && s.serp_hoy > serpBase) {
            clearInterval(timer);
            clearInterval(polling);
            btn.textContent = '✓ ¡Listo!';
            if (info) info.textContent = 'Ciclo terminado — ' + s.serp_hoy + ' búsquedas hoy. Recargando…';
            setTimeout(() => location.reload(), 2000);
          }
        }).catch(() => {});
      }, 15000);
    })
    .catch(() => {
      clearInterval(timer);
      if (info) info.textContent = 'Error al conectar con el servidor.';
      btn.disabled = false;
      btn.textContent = 'Correr ciclo ahora';
    });
}

// ─── Reloj animado (logo) ─────────────────────────────────────────────────────
// ### CAMBIO AQUÍ ### — mueve las agujas del reloj SVG con la hora real
function tickReloj() {
  const now = new Date();
  const s = now.getSeconds();
  const m = now.getMinutes() + s / 60;
  const h = (now.getHours() % 12) + m / 60;
  const cx = 16, cy = 21;   // centro geométrico del watch face en el SVG

  const rotar = (id, deg) => {
    const el = document.getElementById(id);
    if (el) el.setAttribute('transform', `rotate(${deg}, ${cx}, ${cy})`);
  };

  rotar('watch-second', s * 6);
  rotar('watch-minute', m * 6);
  rotar('watch-hour',   h * 30);
}

// ─── Init ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Arrancar reloj inmediatamente y luego cada segundo
  tickReloj();
  setInterval(tickReloj, 1000);
  // Activar filtros con pills existentes
  document.querySelectorAll('.pill').forEach(p => {
    p.addEventListener('click', () => activarFiltro(p));
  });

  // Checkbox "solo no leídos"
  const chk = document.getElementById('chk-nuevos');
  if (chk) chk.addEventListener('change', aplicarFiltros);

  // Botón ciclo admin
  const btnCiclo = document.getElementById('btn-ciclo');
  if (btnCiclo) btnCiclo.addEventListener('click', correrCiclo);

  // Auto-dismiss flash messages
  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => el.remove(), 4000);
  });
});
