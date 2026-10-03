/* Choix des ingrédients d'une recette : champ de recherche + création rapide.
   - On tape le nom ou le code → liste filtrée (accents et majuscules ignorés)
   - Flèches ↑ ↓ + Entrée, ou clic / toucher sur mobile
   - « + Créer » → choix de l'unité → l'ingrédient est créé dans le Stock */
(function () {
  const INGS = window.RM_INGREDIENTS || [];
  const UNITS = ['kg', 'g', 'l', 'ml', 'pièce', 'sachet', 'bouteille', 'boîte'];
  const rowsBox = document.getElementById('recipe-rows');
  if (!rowsBox) return;

  const norm = (s) => (s || '').toString().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  const label = (ing) => (ing.code ? ing.code + ' — ' : '') + ing.name;
  const esc = (s) => (s || '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function search(q) {
    const n = norm(q);
    if (!n) return INGS.slice().sort((a, b) => a.name.localeCompare(b.name)).slice(0, 50);
    const scored = [];
    for (const ing of INGS) {
      const name = norm(ing.name), code = norm(ing.code);
      let score = -1;
      if (code && code === n) score = 0;
      else if (name === n) score = 1;
      else if (code && code.startsWith(n)) score = 2;
      else if (name.startsWith(n)) score = 3;
      else if (name.split(/\s+/).some((w) => w.startsWith(n))) score = 4;
      else if (name.includes(n)) score = 5;
      if (score >= 0) scored.push([score, ing]);
    }
    scored.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name));
    return scored.slice(0, 50).map((x) => x[1]);
  }

  function exactMatch(q) {
    const n = norm(q);
    if (!n) return null;
    return INGS.find((i) => norm(i.code) === n || norm(i.name) === n || norm(label(i)) === n) || null;
  }

  function setRow(row, ing) {
    row.querySelector('.rm-ing-search').value = ing ? label(ing) : row.querySelector('.rm-ing-search').value;
    row.querySelector('.rm-ing-id').value = ing ? ing.id : '';
    row.querySelector('.rm-ing-unit').textContent = ing ? (ing.unit || '—') : '—';
    row.querySelector('.rm-ing-search').classList.toggle('is-invalid', false);
  }

  function closeAll(except) {
    rowsBox.querySelectorAll('.rm-ing-menu').forEach((m) => { if (m !== except) m.hidden = true; });
  }

  function render(row) {
    const input = row.querySelector('.rm-ing-search');
    const menu = row.querySelector('.rm-ing-menu');
    const q = input.value.trim();
    const results = search(q);
    const exact = exactMatch(q);
    let html = '';
    results.forEach((ing, i) => {
      html += `<button type="button" class="rm-ing-opt" data-id="${ing.id}" data-i="${i}">
        ${ing.code ? `<span class="rm-code">${esc(ing.code)}</span>` : ''}
        <span class="rm-ing-opt-name">${esc(ing.name)}</span>
        <span class="rm-ing-opt-unit">${esc(ing.unit)}</span></button>`;
    });
    if (!results.length) html += `<div class="rm-ing-empty">Aucun ingrédient « ${esc(q)} » dans le Stock.</div>`;
    if (q && !exact) {
      html += `<button type="button" class="rm-ing-opt rm-ing-create" data-create="1">
        <i class="bi bi-plus-circle"></i> Créer « <strong>${esc(q)}</strong> »</button>`;
    }
    menu.innerHTML = html;
    menu.hidden = false;
    menu.dataset.active = '-1';
    closeAll(menu);
  }

  function showUnitChooser(row, name) {
    const menu = row.querySelector('.rm-ing-menu');
    menu.innerHTML = `<div class="rm-ing-units">
        <div class="small mb-2">Unité pour « <strong>${esc(name)}</strong> » :</div>
        <div class="d-flex flex-wrap gap-1">${UNITS.map((u) =>
          `<button type="button" class="btn btn-sm btn-outline-primary" data-unit="${esc(u)}">${esc(u)}</button>`).join('')}</div>
        <div class="small text-muted mt-2">Le prix et le stock se complètent plus tard (Stock ou Achats).</div>
      </div>`;
    menu.hidden = false;
    menu.querySelectorAll('[data-unit]').forEach((b) => b.addEventListener('mousedown', async (e) => {
      e.preventDefault();
      b.disabled = true;
      try {
        const fd = new FormData();
        fd.append('name', name);
        fd.append('unit', b.dataset.unit);
        const r = await fetch(window.RM_QUICK_ADD_URL, { method: 'POST', body: fd, credentials: 'same-origin' });
        const d = await r.json();
        if (!r.ok || !d.id) throw new Error(d.error || 'Erreur');
        let ing = INGS.find((i) => i.id === d.id);
        if (!ing) { ing = { id: d.id, name: d.name, code: d.code || '', unit: d.unit || '' }; INGS.push(ing); }
        setRow(row, ing);
        menu.hidden = true;
        row.querySelector('input[name="quantity[]"]').focus();
      } catch (err) {
        menu.innerHTML = `<div class="rm-ing-empty text-danger">Création impossible : ${esc(err.message)}</div>`;
      }
    }));
  }

  function choose(row, opt) {
    if (!opt) return;
    if (opt.dataset.create) {
      showUnitChooser(row, row.querySelector('.rm-ing-search').value.trim());
      return;
    }
    const ing = INGS.find((i) => String(i.id) === opt.dataset.id);
    setRow(row, ing);
    row.querySelector('.rm-ing-menu').hidden = true;
    row.querySelector('input[name="quantity[]"]').focus();
  }

  function bindRow(row) {
    const input = row.querySelector('.rm-ing-search');
    const menu = row.querySelector('.rm-ing-menu');

    input.addEventListener('focus', () => render(row));
    input.addEventListener('input', () => {
      row.querySelector('.rm-ing-id').value = '';
      row.querySelector('.rm-ing-unit').textContent = '—';
      render(row);
    });
    input.addEventListener('keydown', (e) => {
      const opts = [...menu.querySelectorAll('.rm-ing-opt')];
      let a = parseInt(menu.dataset.active || '-1', 10);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (menu.hidden) render(row);
        a = e.key === 'ArrowDown' ? Math.min(a + 1, opts.length - 1) : Math.max(a - 1, 0);
        opts.forEach((o, i) => o.classList.toggle('active', i === a));
        menu.dataset.active = a;
        if (opts[a]) opts[a].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault(); // ne pas envoyer le formulaire
        if (!menu.hidden) choose(row, opts[a >= 0 ? a : 0]);
      } else if (e.key === 'Escape') {
        menu.hidden = true;
      }
    });
    input.addEventListener('blur', () => {
      setTimeout(() => {
        if (menu.querySelector('.rm-ing-units')) return; // choix d'unité en cours
        menu.hidden = true;
        if (!row.querySelector('.rm-ing-id').value) {
          const ex = exactMatch(input.value);
          if (ex) setRow(row, ex);
        }
      }, 180);
    });
    // mousedown (et non click) pour passer avant le blur, y compris sur mobile
    menu.addEventListener('mousedown', (e) => {
      const opt = e.target.closest('.rm-ing-opt');
      if (opt) { e.preventDefault(); choose(row, opt); }
    });
    row.querySelector('.rm-row-remove').addEventListener('click', () => {
      if (rowsBox.querySelectorAll('.recipe-row').length > 1) row.remove();
      else { input.value = ''; setRow(row, null); row.querySelector('input[name="quantity[]"]').value = ''; }
    });
  }

  rowsBox.querySelectorAll('.recipe-row').forEach(bindRow);

  document.getElementById('add-row').addEventListener('click', () => {
    const first = rowsBox.querySelector('.recipe-row');
    const clone = first.cloneNode(true);
    clone.querySelectorAll('input').forEach((el) => { el.value = ''; el.classList.remove('is-invalid'); });
    clone.querySelector('.rm-ing-unit').textContent = '—';
    const m = clone.querySelector('.rm-ing-menu'); m.hidden = true; m.innerHTML = '';
    rowsBox.appendChild(clone);
    bindRow(clone);
    clone.querySelector('.rm-ing-search').focus();
  });

  document.addEventListener('click', (e) => { if (!rowsBox.contains(e.target)) closeAll(null); });

  // Avant d'enregistrer : une ligne avec un texte mais sans ingrédient choisi = erreur visible
  const form = rowsBox.closest('form');
  if (form) form.addEventListener('submit', (e) => {
    let bad = null;
    rowsBox.querySelectorAll('.recipe-row').forEach((row) => {
      const input = row.querySelector('.rm-ing-search');
      if (input.value.trim() && !row.querySelector('.rm-ing-id').value) {
        const ex = exactMatch(input.value);
        if (ex) setRow(row, ex);
        else { input.classList.add('is-invalid'); bad = bad || input; }
      }
    });
    if (bad) {
      e.preventDefault();
      bad.focus();
      alert('« ' + bad.value + ' » n\'est pas encore un ingrédient du Stock.\nChoisissez-le dans la liste, ou cliquez sur « + Créer ».');
    }
  });
})();
