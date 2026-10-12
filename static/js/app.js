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
function correrCiclo() {
  const btn = document.getElementById('btn-ciclo');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Buscando…';
  fetch('/api/correr-ciclo', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      showToast(`Ciclo lanzado — ${d.nuevos || 0} nuevos resultados`);
      setTimeout(() => location.reload(), 3500);
    })
    .catch(() => {
      showToast('Error al lanzar ciclo');
      btn.disabled = false;
      btn.textContent = 'Correr ciclo ahora';
    });
}

// ─── Init ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
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
