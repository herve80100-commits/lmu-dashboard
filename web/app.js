/* Dashboard LMU : écran de volant LMP2 / LMP3 (1280×720 mis à l'échelle).
   Données : pont Python (/stream) ou simulateur intégré (demo.js), même format. */
(() => {
  "use strict";

  // ---- Réglages ---------------------------------------------------------------
  const CFG = {
    leds: 12,
    ledStart: 0.78,      // première LED à 78 % du régime max
    shiftAt: 0.965,      // tout passe au bleu : change de rapport
    water: { warn: 105, crit: 112 },
    oil: { warn: 120, crit: 130 },
    brake: { warn: 850, crit: 1000 },
    tyreOptimal: 85,
    fuelLaps: { warn: 3.5, crit: 2 },
    wear: { warn: 0.7, crit: 0.85 },
  };

  const $ = (id) => document.getElementById(id);
  const txt = (n, v) => { v = String(v); if (n.textContent !== v) n.textContent = v; };
  const stage = $("stage");

  // Mise à l'échelle de l'écran 1280×720 dans la fenêtre
  const fit = () => {
    const k = Math.min(innerWidth / 1280, innerHeight / 720);
    stage.style.transform = `translate(-50%, -50%) scale(${k})`;
  };
  addEventListener("resize", fit); fit();

  const leds = [];
  for (let i = 0; i < CFG.leds; i++) {
    const d = document.createElement("div");
    d.className = "led " + (i < CFG.leds * 0.42 ? "g" : i < CFG.leds * 0.75 ? "y" : "r");
    $("leds").appendChild(d); leds.push(d);
  }

  const tyres = [...document.querySelectorAll(".tyre")].map((t) => {
    t.innerHTML = `<div class="hd"><b></b><span></span></div><div class="t"><div></div><div></div><div></div></div>
      <div class="wr"><div></div></div><div class="ft"><span class="w"></span><span class="br"></span></div>`;
    return { root: t, name: t.querySelector(".hd b"), press: t.querySelector(".hd span"), cells: [...t.querySelectorAll(".t div")],
      wr: t.querySelector(".wr div"), w: t.querySelector(".w"), br: t.querySelector(".br") };
  });

  // ---- Formatage ----------------------------------------------------------------
  const fmtLap = (s) => {
    if (s == null || s <= 0) return "-:--.---";
    const m = Math.floor(s / 60);
    return `${m}:${(s - m * 60).toFixed(3).padStart(6, "0")}`;
  };
  const hms = (s, withH = true) => {
    if (s == null) return "-";
    s = Math.max(0, Math.round(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60, p = (n) => String(n).padStart(2, "0");
    return withH || h ? `${p(h)}:${p(m)}:${p(x)}` : `${p(m)}:${p(x)}`;
  };
  const hm = (s) => (s == null ? "-" : `${String(Math.floor(s / 3600) % 24).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`);
  const tempColor = (t, opt) => {
    if (t == null) return "#222";
    const d = Math.max(-30, Math.min(30, t - opt));
    return `hsl(${d < 0 ? 120 + (-d / 30) * 85 : 120 - (d / 30) * 120}, 95%, 52%)`;
  };
  const levelColor = (f) => `hsl(${Math.max(0, Math.min(1, f)) * 120}, 90%, 50%)`;
  const lim = (v, l) => (v >= l.crit ? "var(--red)" : v >= l.warn ? "var(--orange)" : "");
  const arc = (id, frac) => {
    const v = Math.max(0, Math.min(1, frac || 0)), n = $(id);
    n.style.strokeDasharray = `${(v * 100).toFixed(2)} 100`;
    n.style.opacity = v > 0.005 ? 1 : 0;
  };
  const sign = (v, d = 1) => (v == null ? "-" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`);

  function tile(id, v, max) {
    const n = $(id);
    const has = max == null || max > 0;
    txt(n.querySelector("b"), has ? v : "–");
    n.classList.toggle("off", !has);
    if (n.dataset.v !== String(v)) {  // brève surbrillance quand un réglage change
      if (n.dataset.v !== undefined) { n.classList.add("flash"); clearTimeout(n._t); n._t = setTimeout(() => n.classList.remove("flash"), 900); }
      n.dataset.v = v;
    }
  }

  // ---- Rendu --------------------------------------------------------------------
  function render(s) {
    const c = s.car, lap = s.lap, r = s.race, f = s.fuel;

    // Régime : LED, arc gauche, rapport
    const ratio = c.maxRpm > 0 ? c.rpm / c.maxRpm : 0;
    const shift = ratio >= CFG.shiftAt;
    const lit = shift ? CFG.leds : Math.floor(((ratio - CFG.ledStart) / (CFG.shiftAt - CFG.ledStart)) * CFG.leds);
    $("leds").classList.toggle("shift", shift);
    leds.forEach((d, i) => d.classList.toggle("on", i < lit));
    $("arcs").classList.toggle("shift", shift);
    arc("arc-rpm", (ratio - 0.35) / 0.65);
    arc("arc-brake", c.brake);
    arc("arc-thr", c.throttle);
    const g = c.gear, gname = (n) => (n < 0 ? "R" : n === 0 ? "N" : String(n));
    txt($("gear"), gname(g));
    $("gear").className = shift ? "b" : lit > CFG.leds * 0.75 ? "r" : lit > CFG.leds * 0.42 ? "y" : "";
    txt($("gear-prev"), g > 0 ? gname(g - 1) : "");
    txt($("gear-next"), g >= 0 && g < (c.maxGears || 6) ? gname(g + 1) : "");
    txt($("speed"), Math.round(c.speed));
    txt($("rpm"), Math.round(c.rpm));

    // Réglages
    tile("t-tc", c.tc, c.tcMax);
    tile("t-slip", c.tcSlip ?? "-", c.tcSlipMax);
    tile("t-cut", c.tcCut ?? "-", c.tcCutMax);
    tile("t-bias", c.brakeBias != null ? c.brakeBias.toFixed(1) : "-");
    tile("t-abs", c.abs, c.absMax);
    tile("t-map", c.motorMap, c.motorMapMax);
    $("limiter").classList.toggle("hidden", !c.limiter);

    // Session / tours / position
    txt($("session"), (r.session || "SESSION").toUpperCase());
    txt($("clock"), hms(r.elapsed));
    txt($("lap"), `L${r.lapsDone + 1}`);
    txt($("lap-total"), r.maxLaps || (r.lapsLeft != null ? r.lapsDone + 1 + r.lapsLeft : "-"));
    txt($("class-tag"), (r.className || "-").toUpperCase());
    txt($("pos"), `P${r.classPosition || r.position || "-"}`);
    txt($("pos-total"), r.classTotal || r.total || "-");
    txt($("overall"), `GÉNÉRAL P${r.position || "-"} / ${r.total || "-"}`);
    if (r.startPos == null && r.classPosition) r.startPos = r.classPosition;
    const gain = window.__startPos ??= r.classPosition, diff = gain && r.classPosition ? gain - r.classPosition : 0;
    txt($("gain"), diff > 0 ? `▲ ${diff}` : diff < 0 ? `▼ ${-diff}` : "= 0");
    $("gain").style.color = diff > 0 ? "var(--green)" : diff < 0 ? "var(--red)" : "var(--dim)";
    txt($("laps-left"), r.lapsLeft != null ? `${r.lapsLeft} T rest.` : "");

    // Carburant
    const ff = f.capacity ? f.level / f.capacity : 0;
    arc("arc-fuel", ff);
    txt($("fuel-pct"), `${Math.round(ff * 100)}%`);
    txt($("fuel-level"), f.level != null ? `${f.level.toFixed(1)} L` : "-");
    txt($("fuel-per-lap"), f.perLap != null ? `${f.perLap.toFixed(2)} L` : "calcul…");
    txt($("fuel-laps"), f.lapsLeft != null ? f.lapsLeft.toFixed(1) : "-");
    $("fuel-laps").style.color = f.lapsLeft == null ? "" : f.lapsLeft <= CFG.fuelLaps.crit ? "var(--red)" : f.lapsLeft <= CFG.fuelLaps.warn ? "var(--orange)" : "var(--green)";

    // Chrono
    txt($("lap-best"), fmtLap(lap.best));
    txt($("lap-last"), fmtLap(lap.last));
    txt($("lap-current"), fmtLap(lap.current));
    $("lap-current").style.color = lap.invalid ? "var(--red)" : "";
    txt($("lap-pred"), fmtLap(lap.predicted));
    const db = $("b-delta");
    if (lap.delta == null) { txt($("delta"), "±0.000"); db.className = "box"; }
    else { txt($("delta"), sign(lap.delta, 3)); db.className = "box " + (lap.delta < 0 ? "faster" : "slower"); }

    // Rivaux
    rival("ahead", r.ahead, r.gapAhead != null ? -r.gapAhead : null);
    rival("behind", r.behind, r.gapBehind);

    // Pneus
    s.tyres.forEach((t, i) => {
      const e = tyres[i], opt = t.optimal || CFG.tyreOptimal;
      txt(e.name, t.name);
      txt(e.press, t.pressure != null ? t.pressure.toFixed(0) : "");
      const vals = i % 2 === 0 ? [t.outer, t.center, t.inner] : [t.inner, t.center, t.outer];
      vals.forEach((v, k) => { txt(e.cells[k], v != null ? Math.round(v) : "-"); e.cells[k].style.background = tempColor(v, opt); });
      const w = t.wear ?? 0;
      e.wr.style.width = `${((1 - w) * 100).toFixed(1)}%`;
      e.wr.style.background = levelColor(1 - w / CFG.wear.crit);
      txt(e.w, `${Math.round((1 - w) * 100)}%`);
      txt(e.br, t.brake != null ? `${Math.round(t.brake)}°` : "");
      e.br.style.color = t.brake != null ? lim(t.brake, CFG.brake) : "";
      e.root.classList.toggle("flat", !!(t.flat || t.detached));
    });

    // Météo / temps
    txt($("air"), s.weather?.air != null ? `${s.weather.air.toFixed(1)}°` : "-");
    txt($("trk"), s.weather?.track != null ? `${s.weather.track.toFixed(1)}°` : "-");
    $("wet").classList.toggle("hidden", !(s.weather && ((s.weather.wet ?? 0) > 0.1 || (s.weather.rain ?? 0) > 0.1)));
    txt($("time-left"), r.timeLeft != null ? hms(r.timeLeft, false) : r.lapsLeft != null ? `${r.lapsLeft} T` : "-");
    txt($("tod"), hm(r.timeOfDay));

    // Incidents / pénalités
    const inc = s.flags.penalties > 0 || (r.trackLimits ?? 0) > 0;
    $("inc").classList.toggle("hidden", !inc);
    txt($("inc"), s.flags.penalties > 0 ? `◆ PÉNALITÉ ${s.flags.penalties}` : `◆ LIMITES ${r.trackLimits}`);

    flag(s.flags);
    alerts(s);
    txt($("info"), [s.track, s.vehicle].filter(Boolean).join(" · "));
  }

  function rival(which, car, gap) {
    txt($(`${which}-name`), car?.name ? car.name.toUpperCase() : "-");
    txt($(`${which}-pos`), car?.pos ? `P${car.pos}` : "-");
    $(`${which}-pos`).style.visibility = car ? "" : "hidden";
    txt($(`gap-${which}`), car ? sign(gap ?? car.gap) : "-");
  }

  function flag(f) {
    let cls = "flag-none", text = "";
    if (f.red) [cls, text] = ["flag-red", "DRAPEAU ROUGE"];
    else if (f.checkered) [cls, text] = ["flag-checkered", "ARRIVÉE"];
    else if (f.fcy) [cls, text] = ["flag-fcy", "FULL COURSE YELLOW"];
    else if (f.yellow) [cls, text] = ["flag-yellow", "DRAPEAU JAUNE"];
    else if (f.blue) [cls, text] = ["flag-blue", "DRAPEAU BLEU"];
    else if (f.penalties > 0) [cls, text] = ["flag-penalty", "PÉNALITÉ"];
    else if (f.yellowAhead) [cls, text] = ["flag-yellow-ahead", "JAUNE DEVANT"];
    else if (f.formation) [cls, text] = ["flag-formation", "FORMATION"];
    if (stage.className !== cls) stage.className = cls;
    txt($("flag-text"), text);
  }

  function alerts(s) {
    const c = s.car, f = s.fuel, list = [];
    const add = (level, text) => list.push({ level, text });
    if (c.overheating) add("crit", "SURCHAUFFE");
    if (c.waterTemp >= CFG.water.crit) add("crit", `EAU ${Math.round(c.waterTemp)}°`);
    else if (c.waterTemp >= CFG.water.warn) add("warn", `EAU ${Math.round(c.waterTemp)}°`);
    if (c.oilTemp >= CFG.oil.crit) add("crit", `HUILE ${Math.round(c.oilTemp)}°`);
    else if (c.oilTemp >= CFG.oil.warn) add("warn", `HUILE ${Math.round(c.oilTemp)}°`);
    s.tyres.forEach((t) => {
      if (t.flat) add("crit", `CREVAISON ${t.name}`);
      if (t.detached) add("crit", `ROUE ${t.name}`);
      if (t.brake >= CFG.brake.crit) add("crit", `FREIN ${t.name}`);
      if (t.wear >= CFG.wear.crit) add("crit", `PNEU ${t.name} USÉ`);
    });
    if (f.lapsLeft != null && f.lapsLeft <= CFG.fuelLaps.crit) add("crit", "ESSENCE !");
    else if (f.lapsLeft != null && f.lapsLeft <= CFG.fuelLaps.warn) add("warn", "ESSENCE BASSE");
    if (s.lap.invalid) add("warn", "TOUR INVALIDÉ");
    if (c.damage > 0 || c.detached) add("warn", "DÉGÂTS");
    if (s.race.inPits) add("info", "STANDS");
    const order = { crit: 0, warn: 1, info: 2 };
    list.sort((a, b) => order[a.level] - order[b.level]);
    const html = list.slice(0, 4).map((a) => `<div class="${a.level}">${a.text}</div>`).join("");
    if ($("alerts").innerHTML !== html) $("alerts").innerHTML = html;
  }

  // ---- Sources de données ---------------------------------------------------------
  let demo = null, latest = null, demoMode = false;
  const status = (cls, t) => { $("status").className = "status " + cls; txt($("status"), t); $("bar").classList.toggle("show", cls !== "status-on"); };

  function connectBridge() {
    if (location.protocol === "file:") return;
    const es = new EventSource("/stream");
    es.onmessage = (ev) => {
      if (demoMode) return;
      const s = JSON.parse(ev.data);
      if (s.connected) { latest = s; status("status-on", "LMU connecté"); }
      else status("status-wait", s.message || "En attente…");
    };
    es.onerror = () => { if (!demoMode) status("status-off", "Pont injoignable"); };
  }

  function toggleDemo(on) {
    demoMode = on;
    $("btn-demo").classList.toggle("on", on);
    demo = on ? new DemoSim() : null;
    window.__startPos = undefined;
    if (!on) latest = null;
    status(on ? "status-demo" : "status-wait", on ? "Mode démo" : "En attente de LMU…");
  }

  let prev = performance.now();
  function frame(now) {
    const dt = Math.min(0.1, (now - prev) / 1000);
    prev = now;
    if (demoMode && demo) latest = demo.step(dt);
    if (latest) render(latest);
    requestAnimationFrame(frame);
  }

  $("btn-demo").addEventListener("click", () => toggleDemo(!demoMode));
  $("btn-full").addEventListener("click", () => {
    if (window.pywebview && window.pywebview.api) return window.pywebview.api.toggle_fullscreen();
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  });
  addEventListener("keydown", (e) => {
    if (e.key === "F11") { e.preventDefault(); $("btn-full").click(); }
    if (e.key === "d" || e.key === "D") toggleDemo(!demoMode);
  });

  connectBridge();
  if (new URLSearchParams(location.search).has("demo") || location.protocol === "file:") toggleDemo(true);
  requestAnimationFrame(frame);
})();
