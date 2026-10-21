/* LMU Analyzer : rendu temps réel du flux /stream (Server-Sent Events). */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const MINUS = '−';
  const params = new URLSearchParams(location.search);
  const FLIP = params.get('flip') || ''; // ?flip=x, y ou xy si la carte apparaît en miroir

  const SECTIONS = {
    brake: { name: 'Freinage' },
    traction: { name: 'Accélération' },
    corner: { name: 'Vitesse en courbe' },
    tyres: { name: 'Pneus' },
    energy: { name: 'Énergie' },
    consistency: { name: 'Régularité' },
  };
  const CAT = { brake: 'FREINAGE', traction: 'ACCÉLÉRATION', corner: 'VITESSE EN COURBE', consistency: 'RÉGULARITÉ' };
  const BADGE = { good: '✓ Bon', warn: '● Correct', bad: '▲ À travailler' };

  // ── Formatage ────────────────────────────────────────────────────────────
  const num = (v) => typeof v === 'number' && isFinite(v);
  const fmtLap = (s) => {
    if (!num(s) || s <= 0) return '—';
    const m = Math.floor(s / 60);
    const r = s - m * 60;
    return m > 0 ? `${m}:${r.toFixed(3).padStart(6, '0')}` : r.toFixed(3);
  };
  const fmtSigned = (v, digits = 3) => {
    if (!num(v)) return '—';
    const a = Math.abs(v).toFixed(digits);
    if (Number(a) === 0) return (0).toFixed(digits);
    return (v < 0 ? MINUS : '+') + a;
  };
  const fmtClock = (s) => {
    if (!num(s)) return '—';
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  };
  const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const deltaClass = (d) => (!num(d) || Math.abs(d) < 0.0005 ? '' : d < 0 ? 'good-t' : 'bad-t');
  const segColor = (d) => (d <= -0.08 ? 'var(--gain2)' : d < -0.02 ? 'var(--gain1)' : d >= 0.08 ? 'var(--loss2)' : d > 0.02 ? 'var(--loss1)' : 'var(--neutral)');
  const setText = (id, t) => { const el = $(id); if (el.textContent !== t) el.textContent = t; };

  function svg(tag, attrs = {}, text) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    if (text !== undefined) el.textContent = text;
    return el;
  }

  // ── Mise à l'échelle de la scène 1920×1080 ──────────────────────────────
  function fit() {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    const stage = $('stage');
    stage.style.transform = `scale(${s})`;
    stage.style.left = `${(innerWidth - 1920 * s) / 2}px`;
    stage.style.top = `${(innerHeight - 1080 * s) / 2}px`;
  }
  addEventListener('resize', fit);
  fit();

  // Barre de régime : 13 segments
  for (let i = 0; i < 13; i++) $('c-rpmbar').appendChild(document.createElement('i'));

  // ── Barre haute ──────────────────────────────────────────────────────────
  function renderTop(d) {
    const s = d.session;
    setText('s-track', `${s.track || '—'} · ${s.track_km.toFixed(3).replace('.', ',')} km`);
    setText('s-vehicle', [s.vehicle, s.vehicle_class].filter(Boolean).join(' · ') || '—');
    setText('s-session', `${s.type || 'Session'} · Tour ${s.lap}`);
    setText('s-pos', s.position ? `P${s.position}` : '—');
    setText('s-cars', s.num_cars ? `/ ${s.num_cars}` : '');
    setText('s-ahead-l', s.ahead ? `Devant · ${s.ahead}` : 'Devant');
    setText('s-behind-l', s.behind ? `Derrière · ${s.behind}` : 'Derrière');
    const ah = $('s-ahead'), bh = $('s-behind');
    ah.textContent = num(s.gap_ahead) ? `+${s.gap_ahead.toFixed(3)}` : '—';
    ah.className = 'mono bad-t';
    bh.textContent = num(s.gap_behind) ? `${MINUS}${s.gap_behind.toFixed(3)}` : '—';
    bh.className = 'mono good-t';
    setText('s-weather', `${s.track_temp} °C / ${s.air_temp} °C · ${s.raining ? 'Pluie' : 'Sec'}`);
    setText('s-remaining', fmtClock(s.time_remaining));
  }

  // ── Chrono ───────────────────────────────────────────────────────────────
  function renderTiming(d) {
    const l = d.live;
    setText('t-lap', fmtLap(l.lap_time) === '—' ? '0.000' : fmtLap(l.lap_time));
    const el = $('t-delta');
    if (num(l.delta)) {
      const faster = l.delta < 0;
      el.innerHTML = `${fmtSigned(l.delta)} <small>${faster ? '▼ plus rapide' : l.delta > 0 ? '▲ plus lent' : ''}</small>`;
      el.style.color = Math.abs(l.delta) < 0.0005 ? 'var(--t2)' : faster ? 'var(--good)' : 'var(--bad)';
    } else {
      el.innerHTML = `— <small>${d.best_lap ? '' : 'en attente du meilleur tour'}</small>`;
      el.style.color = 'var(--t3)';
    }
    const pred = $('t-pred');
    pred.textContent = fmtLap(l.predicted);
    pred.className = num(l.delta) ? (l.delta < 0 ? 'good-t' : 'bad-t') : '';
    setText('t-last', fmtLap(l.last_lap));
    setText('t-best', fmtLap(l.best_lap));
    setText('t-theo', fmtLap(l.theoretical));
  }

  function renderSectors(d) {
    const sec = d.sectors;
    const tiles = $('sec-tiles');
    const colors = { purple: 'var(--purple)', green: 'var(--pb)', yellow: 'var(--slow)' };
    const labels = ['S1', 'S2', 'S3'];
    if (!sec) {
      $('sec-title').innerHTML = 'Secteurs <span class="sub">en attente d\'un tour complet</span>';
      tiles.innerHTML = labels.map((n) => `<div class="st"><div class="n">${n}</div><div class="v mono">—</div><div class="d mono">&nbsp;</div></div>`).join('');
      return;
    }
    $('sec-title').innerHTML = `Secteurs · tour ${sec.lap} <span class="sub">${sec.ref_lap ? `vs meilleur tour (T${sec.ref_lap})` : ''}</span>`;
    tiles.innerHTML = labels.map((n, i) => {
      const st = sec.status ? sec.status[i] : null;
      const c = colors[st] || 'var(--neutral)';
      const dl = sec.deltas ? sec.deltas[i] : null;
      const tag = st === 'purple' ? 'record session' : st === 'green' ? 'record perso' : '';
      return `<div class="st" style="border-color:${c}"><div class="n">${n}<span>${tag}</span></div>
        <div class="v mono">${fmtLap(sec.times[i])}</div>
        <div class="d mono" style="color:${dl === null ? 'var(--t3)' : c}">${dl === null ? '&nbsp;' : fmtSigned(dl)}</div></div>`;
    }).join('');
  }

  function renderCar(d) {
    const l = d.live;
    setText('c-gear', l.gear < 0 ? 'R' : l.gear === 0 ? 'N' : String(l.gear));
    setText('c-speed', String(l.speed));
    setText('c-rpm', l.max_rpm ? `${l.rpm.toLocaleString('fr-FR')} / ${l.max_rpm.toLocaleString('fr-FR')} tr/min` : '');
    const ratio = l.max_rpm ? l.rpm / l.max_rpm : 0;
    [...$('c-rpmbar').children].forEach((seg, i) => {
      const on = ratio >= (i + 1) / 13 - 0.001;
      seg.className = !on ? '' : ratio > 0.97 ? 'on-b' : i < 7 ? 'on-g' : i < 10 ? 'on-y' : 'on-r';
    });
    $('c-thr').style.width = `${l.throttle}%`;
    $('c-brk').style.width = `${l.brake}%`;
    setText('c-thr-v', `${l.throttle}%`);
    setText('c-brk-v', `${l.brake}%`);
    const e = d.sections.energy;
    const chips = [
      num(l.tc) ? ['TC', l.tc] : null,
      num(l.abs) ? ['ABS', l.abs] : null,
      l.brake_bias ? ['Répartition', `${l.brake_bias.toFixed(1)}%`] : null,
      num(l.motor_map) ? ['Moteur', `Map ${l.motor_map}`] : null,
      ['Secteur', `S${l.sector}`],
      l.in_pits ? ['Stand', 'oui'] : (num(e.fuel) && e.kind !== 'virtual' ? ['Carburant', `${e.fuel.toFixed(1)} L`] : null),
    ].filter(Boolean).slice(0, 4);
    $('c-chips').innerHTML = chips.map(([k, v]) => `<span class="chip">${k} <b>${esc(v)}</b></span>`).join('');
  }

  // ── Carte du circuit ─────────────────────────────────────────────────────
  function renderMap(d) {
    const m = d.map;
    const el = $('map');
    el.replaceChildren();
    const a = d.analysis;
    setText('map-sub', a ? `gain / perte par virage · T${a.lap} vs meilleur (T${a.ref_lap})` : 'tracé en cours d\'enregistrement');
    if (!m || m.path.length < 2) {
      el.appendChild(svg('text', { x: 283, y: 186, 'text-anchor': 'middle', fill: '#6d7483', 'font-size': 14 }, 'Le tracé apparaît pendant ton premier tour'));
      return;
    }
    const W = 566, H = 372, PAD = 30;
    const flip = ([x, y]) => [FLIP.includes('x') ? 1 - x : x, FLIP.includes('y') ? 1 - y : y];
    const raw = m.path.map(flip);
    const minX = Math.min(...raw.map((p) => p[0])), maxX = Math.max(...raw.map((p) => p[0]));
    const minY = Math.min(...raw.map((p) => p[1])), maxY = Math.max(...raw.map((p) => p[1]));
    const k = Math.min((W - 2 * PAD) / Math.max(1e-6, maxX - minX), (H - 2 * PAD) / Math.max(1e-6, maxY - minY));
    const ox = (W - (maxX - minX) * k) / 2, oy = (H - (maxY - minY) * k) / 2;
    const P = (pt) => { const [x, y] = flip(pt); return [ox + (x - minX) * k, oy + (y - minY) * k]; };
    const pts = m.path.map(P);
    const line = (from, to) => {
      const seg = [];
      if (to >= from) for (let i = from; i <= to; i++) seg.push(pts[i]);
      else { for (let i = from; i < pts.length; i++) seg.push(pts[i]); for (let i = 0; i <= to; i++) seg.push(pts[i]); }
      return seg.map((p) => p.map((v) => v.toFixed(1)).join(',')).join(' ');
    };
    const all = line(0, pts.length - 1) + (m.complete ? ` ${pts[0].join(',')}` : '');
    const g = svg('g', { fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
    g.appendChild(svg('polyline', { points: all, stroke: '#0c0e13', 'stroke-width': 15 }));
    g.appendChild(svg('polyline', { points: all, stroke: 'var(--neutral)', 'stroke-width': 9 }));
    for (const s of m.segments) g.appendChild(svg('polyline', { points: line(s.from, s.to), stroke: segColor(s.delta), 'stroke-width': 9 }));
    el.appendChild(g);

    // Ligne de départ
    const [sx, sy] = pts[0];
    const fl = svg('g', { transform: `translate(${sx - 5},${sy - 8})` });
    [[0, 0, '#fff'], [5, 0, '#111'], [0, 8, '#111'], [5, 8, '#fff']].forEach(([x, y, c]) => fl.appendChild(svg('rect', { x, y, width: 5, height: 8, fill: c })));
    el.appendChild(fl);

    // Limites de secteurs
    m.sectors.forEach((i, k) => {
      const [x, y] = pts[i];
      el.appendChild(svg('circle', { cx: x, cy: y, r: 5, fill: '#0c0e13', stroke: '#a8aebb', 'stroke-width': 2 }));
      el.appendChild(svg('text', { x: x + 9, y: y + 4, 'font-size': 11, 'font-weight': 700, fill: '#a8aebb' }, `S${k + 2}`));
    });

    // Étiquettes des virages les plus marquants
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    const top = [...m.segments].filter((s) => Math.abs(s.delta) >= 0.02).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 7);
    for (const s of top) {
      const [x, y] = pts[s.apex];
      const dx = x - cx, dy = y - cy, n = Math.hypot(dx, dy) || 1;
      const lx = Math.min(W - 4, Math.max(4, x + (dx / n) * 16)), ly = Math.min(H - 6, Math.max(14, y + (dy / n) * 16));
      const anchor = lx > W - 110 ? 'end' : lx < 110 ? 'start' : dx >= 0 ? 'start' : 'end';
      const col = s.delta < 0 ? '#3fbf66' : '#ff6b6f';
      const t = svg('text', { x: lx, y: ly, 'text-anchor': anchor, 'font-size': 12, 'font-weight': 600 });
      t.appendChild(svg('tspan', { fill: '#eef0f4' }, `${s.name.replace('Virage ', 'V')} `));
      t.appendChild(svg('tspan', { fill: col, class: 'mono' }, `${fmtSigned(s.delta, 2)} s`));
      el.appendChild(t);
    }

    // Voiture
    if (m.car) {
      const [x, y] = P(m.car);
      el.appendChild(svg('circle', { cx: x, cy: y, r: 8, fill: '#fff', stroke: '#0c0e13', 'stroke-width': 3 }));
    }
  }

  // ── Delta cumulé ─────────────────────────────────────────────────────────
  function renderDelta(d) {
    const el = $('delta');
    el.replaceChildren();
    const a = d.analysis;
    const tot = $('delta-total');
    if (!a) {
      tot.textContent = '';
      el.appendChild(svg('text', { x: 328, y: 90, 'text-anchor': 'middle', fill: '#6d7483', 'font-size': 14 }, 'Disponible après 2 tours complets (dont un tour de référence)'));
      return;
    }
    setText('delta-sub', `T${a.lap} vs meilleur tour (T${a.ref_lap}) · sur la distance`);
    tot.textContent = `${fmtSigned(a.total)} s`;
    tot.className = `mono total ${deltaClass(a.total)}`;
    const L = d.session.track_km, X0 = 44, X1 = 652, Y0 = 82;
    const maxAbs = Math.max(0.25, ...a.trace.map((p) => Math.abs(p[1])));
    const range = Math.ceil(maxAbs * 10) / 10;
    const sx = (km) => X0 + (km / L) * (X1 - X0);
    const sy = (v) => Y0 - (v / range) * 60;
    [Y0 - 60, Y0 + 60].forEach((y) => el.appendChild(svg('line', { x1: X0, y1: y, x2: X1, y2: y, stroke: '#232732' })));
    el.appendChild(svg('line', { x1: X0, y1: Y0, x2: X1, y2: Y0, stroke: '#5a6170' }));
    [[range, Y0 - 57], [0, Y0 + 3], [-range, Y0 + 63]].forEach(([v, y]) => el.appendChild(svg('text', { x: 38, y, 'text-anchor': 'end', 'font-size': 10, fill: '#6d7483', class: 'mono' }, v === 0 ? '0' : fmtSigned(v, 1))));
    const marks = [0, ...a.sector_km];
    marks.forEach((km, i) => {
      if (i > 0) el.appendChild(svg('line', { x1: sx(km), y1: 14, x2: sx(km), y2: 150, stroke: '#3a3f4b', 'stroke-dasharray': '3 4' }));
      el.appendChild(svg('text', { x: sx(km) + 6, y: 14, 'font-size': 10, fill: '#6d7483', 'font-weight': 600 }, `S${i + 1}`));
    });
    const pts = a.trace.map(([km, v]) => `${sx(km).toFixed(1)},${sy(v).toFixed(1)}`);
    const area = `M${X0},${Y0} L${pts.join(' L')} L${X1},${Y0} Z`;
    const defs = svg('defs');
    const ca = svg('clipPath', { id: 'clip-above' }); ca.appendChild(svg('rect', { x: 0, y: 0, width: 656, height: Y0 }));
    const cb = svg('clipPath', { id: 'clip-below' }); cb.appendChild(svg('rect', { x: 0, y: Y0, width: 656, height: 166 - Y0 }));
    defs.append(ca, cb);
    el.appendChild(defs);
    el.appendChild(svg('path', { d: area, fill: '#e5484d', 'fill-opacity': 0.22, 'clip-path': 'url(#clip-above)' }));
    el.appendChild(svg('path', { d: area, fill: '#22b14c', 'fill-opacity': 0.22, 'clip-path': 'url(#clip-below)' }));
    el.appendChild(svg('polyline', { points: pts.join(' '), fill: 'none', stroke: '#eef0f4', 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    const at = (km) => {
      const t = a.trace;
      for (let i = 1; i < t.length; i++) if (t[i][0] >= km) {
        const f = (km - t[i - 1][0]) / Math.max(1e-6, t[i][0] - t[i - 1][0]);
        return t[i - 1][1] + f * (t[i][1] - t[i - 1][1]);
      }
      return t[t.length - 1][1];
    };
    const placed = [];
    for (const mk of a.marks) {
      const x = sx(mk.km), y = sy(at(mk.km));
      const col = mk.delta < 0 ? '#22b14c' : '#e5484d';
      el.appendChild(svg('circle', { cx: x, cy: y, r: 4, fill: col, stroke: '#161920', 'stroke-width': 2 }));
      let ty = mk.delta < 0 ? y + 18 : y - 10;
      while (placed.some((p) => Math.abs(p[0] - x) < 110 && Math.abs(p[1] - ty) < 13)) ty += mk.delta < 0 ? 13 : -13;
      ty = Math.min(150, Math.max(24, ty));
      placed.push([x, ty]);
      el.appendChild(svg('text', { x: Math.min(X1, Math.max(X0 + 40, x)), y: ty, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 600, fill: mk.delta < 0 ? '#3fbf66' : '#ff6b6f' }, `${mk.name.replace('Virage ', 'V')} ${fmtSigned(mk.delta, 2)}`));
    }
    [[0, 'start', '0 km'], [L / 2, 'middle', (L / 2).toFixed(1)], [L, 'end', L.toFixed(1)]].forEach(([km, anc, txt]) => el.appendChild(svg('text', { x: sx(km), y: 162, 'text-anchor': anc, 'font-size': 10, fill: '#6d7483', class: 'mono' }, txt)));
  }

  // ── Freinage & accélération (virage le plus coûteux) ─────────────────────
  function renderFocus(d) {
    const el = $('focus');
    el.replaceChildren();
    const f = d.analysis && d.analysis.focus;
    if (!f) {
      setText('focus-sub', 'virage le plus coûteux');
      el.appendChild(svg('text', { x: 328, y: 100, 'text-anchor': 'middle', fill: '#6d7483', 'font-size': 14 }, 'Disponible après 2 tours complets'));
      return;
    }
    setText('focus-sub', `${f.name} · km ${f.km.toFixed(1)} · ${fmtSigned(f.delta)} s · dernier tour vs meilleur`);
    const [r0, r1] = f.range, X0 = 64, X1 = 648, Y0 = 168, Y1 = 28;
    const sx = (m) => X0 + ((m - r0) / (r1 - r0)) * (X1 - X0);
    const sy = (p) => Y0 - (p / 100) * (Y0 - Y1);
    [Y1, (Y0 + Y1) / 2].forEach((y) => el.appendChild(svg('line', { x1: X0, y1: y, x2: X1, y2: y, stroke: '#232732' })));
    el.appendChild(svg('line', { x1: X0, y1: Y0, x2: X1, y2: Y0, stroke: '#3a3f4b' }));
    [[100, Y1], [50, (Y0 + Y1) / 2], [0, Y0]].forEach(([v, y]) => el.appendChild(svg('text', { x: 56, y: y + 3, 'text-anchor': 'end', 'font-size': 10, fill: '#6d7483', class: 'mono' }, `${v}%`)));
    if (r0 < 0 && r1 > 0) {
      el.appendChild(svg('line', { x1: sx(0), y1: 20, x2: sx(0), y2: Y0, stroke: '#3a3f4b', 'stroke-dasharray': '3 4' }));
      el.appendChild(svg('text', { x: sx(0) + 5, y: 46, 'font-size': 10, fill: '#6d7483', 'font-weight': 600 }, 'Point de corde'));
    }
    const step = (r1 - r0) / 6;
    for (let i = 0; i <= 6; i++) {
      const m = Math.round((r0 + i * step) / 10) * 10;
      el.appendChild(svg('text', { x: sx(m), y: 184, 'text-anchor': i === 0 ? 'start' : i === 6 ? 'end' : 'middle', 'font-size': 10, fill: '#6d7483', class: 'mono' }, `${m > 0 ? '+' : m < 0 ? MINUS : ''}${Math.abs(m)}${i === 0 ? ' m' : ''}`));
    }
    const path = (series, color, dashed) => el.appendChild(svg('polyline', {
      points: series.map(([m, p]) => `${sx(m).toFixed(1)},${sy(p).toFixed(1)}`).join(' '),
      fill: 'none', stroke: color, 'stroke-width': dashed ? 2 : 2.5, 'stroke-dasharray': dashed ? '5 4' : 'none', opacity: dashed ? 0.75 : 1, 'stroke-linejoin': 'round',
    }));
    path(f.ref.throttle, '#199e70', true);
    path(f.cur.throttle, '#199e70', false);
    path(f.ref.brake, '#d95926', true);
    path(f.cur.brake, '#d95926', false);

    if (num(f.onset_cur) && num(f.onset_ref) && f.onset_cur !== f.onset_ref) {
      const a = sx(Math.min(f.onset_cur, f.onset_ref)), b = sx(Math.max(f.onset_cur, f.onset_ref));
      el.appendChild(svg('line', { x1: a, y1: 22, x2: b, y2: 22, stroke: '#eef0f4', 'stroke-width': 1.5 }));
      [a, b].forEach((x) => el.appendChild(svg('line', { x1: x, y1: 18, x2: x, y2: 26, stroke: '#eef0f4', 'stroke-width': 1.5 })));
    }
    const hx = num(f.onset_cur) && num(f.onset_ref) ? sx(Math.max(f.onset_cur, f.onset_ref)) + 10 : X0 + 10;
    el.appendChild(svg('text', { x: Math.min(hx, 360), y: 20, 'font-size': 11, 'font-weight': 600, fill: '#eef0f4' }, f.headline));
    const notes = [];
    if (f.coast > 0.05) notes.push(`Roue libre +${f.coast.toFixed(2)} s`);
    if (Math.abs(f.throttle_delta) >= 5) notes.push(`Gaz ${Math.abs(f.throttle_delta)} m ${f.throttle_delta > 0 ? 'trop tard' : 'plus tôt'}`);
    notes.forEach((t, i) => el.appendChild(svg('text', { x: X1 - 4, y: 70 + i * 15, 'text-anchor': 'end', 'font-size': 11, 'font-weight': 600, fill: f.delta > 0 ? '#ff8a8c' : '#3fbf66' }, t)));
  }

  // ── Points forts / faibles ───────────────────────────────────────────────
  function renderLists(d) {
    const item = (it, kind, i) => {
      const val = it.value || `${fmtSigned(it.delta, 2)} s`;
      const ic = kind === 'bad' ? i + 1 : '✓';
      return `<div class="item ${kind}"><div class="ic">${ic}</div><div class="body">
        <div class="t"><span>${esc(it.name)}<span class="tag ${it.category}">${CAT[it.category] || ''}</span></span><span class="val">${esc(val)}</span></div>
        <p title="${esc(it.tip)}">${esc(it.tip)}</p></div></div>`;
    };
    const waiting = !d.analysis;
    $('weak').innerHTML = d.weaknesses.length ? d.weaknesses.map((it, i) => item(it, 'bad', i)).join('')
      : `<div class="empty">${waiting ? 'L\'analyse démarre après ton tour de référence et un tour de comparaison.' : 'Aucune perte notable sur le dernier tour. Bravo !'}</div>`;
    $('strong').innerHTML = d.strengths.length ? d.strengths.map((it, i) => item(it, 'good', i)).join('')
      : `<div class="empty">${waiting ? 'Tes points forts apparaîtront ici.' : 'Aucun gain notable sur le dernier tour.'}</div>`;
  }

  // ── Cartes d'analyse ─────────────────────────────────────────────────────
  const head = (key, right) => `<div class="head"><div class="name"><i class="dot"></i>${SECTIONS[key].name}</div>${right}</div>`;
  const metrics = (rows) => rows.map(([k, v]) => `<div class="m"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
  const badge = (status, text) => `<span class="badge ${status}">${text || BADGE[status]}</span>`;
  const scoreHead = (key, score, unit = '/100') => head(key, `<div class="score mono">${num(score) ? score : '—'}<small>${unit}</small></div>`);

  function renderScored(card, key, sec) {
    if (!sec) {
      card.innerHTML = scoreHead(key, null) + '<div class="sbar"><i style="width:0"></i></div><div class="empty">En attente d\'un tour de référence et d\'un tour de comparaison.</div>';
      return;
    }
    card.innerHTML = scoreHead(key, sec.score) + `<div class="sbar"><i style="width:${sec.score}%"></i></div>${metrics(sec.metrics)}<div class="bottom">${badge(sec.status)}</div>`;
  }

  function renderTyres(card, t) {
    if (!t.wheels) {
      const tiles = ['AVG', 'AVD', 'ARG', 'ARD'].map((p) => `<div class="ty">${p}<b>—</b>&nbsp;<div class="w"><i style="width:0"></i></div></div>`).join('');
      card.innerHTML = head('tyres', `<div class="aside mono">${esc(t.compound || '—')} · ${t.laps} tours</div>`) + `<div class="tyres">${tiles}</div><div class="bottom" style="margin-top:8px">Mesures disponibles une fois en piste</div>`;
      return;
    }
    const tiles = t.wheels.map((w) => {
      const extra = [num(w.surface) && w.surface !== w.temp ? `surf. ${w.surface}°` : null, num(w.optimal) ? `opt. ${w.optimal}°` : null].filter(Boolean).join(' · ');
      return `<div class="ty"><span class="tyh">${w.pos}<small>${extra}</small></span><b class="${w.state === 'ok' ? '' : w.state}">${w.temp} °C</b>${w.pressure.toFixed(2)} bar · ${w.wear.toFixed(0)} %<div class="w"><i style="width:${Math.max(0, 100 - w.wear)}%"></i></div></div>`;
    }).join('');
    const hot = t.wheels.filter((w) => w.state === 'hot').map((w) => w.pos);
    const cold = t.wheels.filter((w) => w.state === 'cold').map((w) => w.pos);
    const b = hot.length ? badge('warn', `● ${hot.join(', ')} chaud`) : cold.length ? badge('warn', `● ${cold.join(', ')} froid`) : badge('good', '✓ Fenêtre idéale');
    const note = t.stale ? 'dernière mesure en piste' : 'usure en %';
    card.innerHTML = head('tyres', `<div class="aside mono">${esc(t.compound || '—')} · ${t.laps} tours</div>`) + `<div class="tyres">${tiles}</div><div class="bottom" style="margin-top:8px">${b} <span>${note}</span></div>`;
  }

  function renderEnergy(card, e, lap) {
    const pct = num(e.pct) ? e.pct : null;
    let b = badge('good', '✓ Autonomie OK');
    if (num(e.laps_left) && e.laps_left < 3) b = badge('bad', '▲ Ravitaillement !');
    else if (num(e.laps_left) && e.laps_left < 6) b = badge('warn', '● Arrêt bientôt');
    else if (!num(e.laps_left)) b = badge('warn', '● Calcul au prochain tour');
    card.innerHTML = head('energy', `<div class="score mono">${pct ?? '—'}<small>%</small></div>`)
      + `<div class="sbar fat"><i style="width:${pct ?? 0}%"></i></div>`
      + metrics([
        e.kind === 'virtual' ? ['Énergie virtuelle', `${pct ?? '—'} %`] : ['Carburant', num(e.fuel) ? `${e.fuel.toFixed(1)} L` : '—'],
        ['Conso. / tour', num(e.per_lap) ? `${e.per_lap.toFixed(2)} ${e.kind === 'virtual' ? '%' : 'L'}` : '—'],
        ['Tours restants', num(e.laps_left) ? e.laps_left.toFixed(1) : '—'],
        ['Arrêt prévu', num(e.pit_lap) ? `Tour ${e.pit_lap}` : '—'],
      ]) + `<div class="bottom">${b}</div>`;
  }

  function renderConsistency(card, c, best) {
    if (!c) {
      card.innerHTML = scoreHead('consistency', null) + '<div class="empty">Il faut au moins 3 tours valides.</div>';
      return;
    }
    const W = 268, H = 96, laps = c.laps;
    const times = laps.map((l) => l.time).concat(best ? [best] : []);
    const lo = Math.min(...times), hi = Math.max(...times);
    const span = Math.max(0.3, hi - lo);
    const sx = (i) => 10 + (i / Math.max(1, laps.length - 1)) * (W - 20);
    const sy = (t) => 12 + ((t - lo) / span) * 54;
    const pts = laps.map((l, i) => `${sx(i).toFixed(1)},${sy(l.time).toFixed(1)}`).join(' ');
    const dots = laps.map((l, i) => `<circle cx="${sx(i).toFixed(1)}" cy="${sy(l.time).toFixed(1)}" r="${l.time === best ? 4.5 : 4}" fill="${l.time === best ? '#a855f7' : '#9085e9'}" stroke="#161920" stroke-width="2"/>`).join('');
    const bestLine = best ? `<line x1="0" y1="${sy(best).toFixed(1)}" x2="${W}" y2="${sy(best).toFixed(1)}" stroke="#a855f7" stroke-dasharray="3 3" opacity=".8"/><text x="${W - 2}" y="${Math.min(H - 16, sy(best) + 12).toFixed(1)}" font-size="9" fill="#a855f7" text-anchor="end" class="mono">meilleur ${fmtLap(best)}</text>` : '';
    const lbl = [0, laps.length - 1].map((i) => `<text x="${sx(i)}" y="92" font-size="9" fill="#6d7483" text-anchor="middle" class="mono">T${laps[i].lap}</text>`).join('');
    card.innerHTML = scoreHead('consistency', c.score)
      + `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="margin-top:6px;max-width:100%">${bestLine}<polyline points="${pts}" fill="none" stroke="#9085e9" stroke-width="2"/>${dots}${lbl}</svg>`
      + metrics([['Écart-type', `${c.sigma.toFixed(2)} s`], ['Écart max', `${c.spread.toFixed(2)} s`]]);
  }

  function renderSections(d) {
    const s = d.sections;
    for (const card of document.querySelectorAll('.sc')) {
      const key = card.dataset.section;
      if (key === 'tyres') renderTyres(card, s.tyres);
      else if (key === 'energy') renderEnergy(card, s.energy, d.session.lap);
      else if (key === 'consistency') renderConsistency(card, s.consistency, d.best_lap);
      else renderScored(card, key, s[key]);
    }
  }

  // ── Boucle de rendu ──────────────────────────────────────────────────────
  let latest = null, lastHeavy = '', pending = false;

  function render() {
    pending = false;
    const d = latest;
    const pill = $('live-pill');
    if (!d || !d.connected) {
      $('overlay').classList.add('show');
      setText('ov-text', d ? 'En attente de Le Mans Ultimate…' : 'Connexion au serveur…');
      setText('ov-status', d && d.status ? `État : ${d.status}` : 'Lance une session dans le jeu : le dashboard se remplit automatiquement.');
      pill.className = 'live off';
      $('f-status').innerHTML = `<b class="off">●</b> ${d ? 'Jeu non détecté · lance une session dans Le Mans Ultimate' : 'Serveur injoignable'}`;
      return;
    }
    $('overlay').classList.remove('show');
    const demo = d.source === 'demo';
    pill.className = demo ? 'live demo' : 'live';
    pill.querySelector('span').textContent = demo ? 'DÉMO' : 'LIVE';
    $('f-status').innerHTML = demo ? '<b class="demo">●</b> Mode démo · télémétrie simulée' : `<b>●</b> Connecté à Le Mans Ultimate · mémoire partagée · ${Math.round(d.hz || 50)} Hz`;
    setText('f-right', `${d.laps_done} tour${d.laps_done > 1 ? 's' : ''} analysé${d.laps_done > 1 ? 's' : ''}`);

    renderTop(d);
    renderTiming(d);
    renderCar(d);
    renderSectors(d);
    renderMap(d);
    // Les blocs d'analyse ne changent qu'à la fin d'un tour : on ne les redessine que s'ils changent.
    const heavyKey = JSON.stringify([d.analysis && d.analysis.lap, d.laps_done, d.session.track_km]);
    if (heavyKey !== lastHeavy) {
      lastHeavy = heavyKey;
      renderDelta(d);
      renderFocus(d);
      renderLists(d);
    }
    renderSections(d);
  }

  function schedule() {
    if (!pending) { pending = true; requestAnimationFrame(render); }
  }

  function connect() {
    const es = new EventSource('stream');
    es.onmessage = (ev) => { latest = JSON.parse(ev.data); schedule(); };
    es.onerror = () => { latest = null; schedule(); };
  }

  render();
  connect();
})();
