/* Simulateur de démonstration : produit les mêmes données que le pont LMU,
   pour tester le dashboard sans lancer le jeu. */
class DemoSim {
  constructor() {
    this.L = 5200;                 // longueur du circuit (m)
    this.maxRpm = 8400;
    this.ratios = [0, 100, 140, 178, 214, 248, 285]; // vitesse max par rapport (km/h)
    this.d = 0; this.lapTime = 0; this.lap = 1; this.et = 0;
    this.speed = 120; this.gear = 3; this.event = null;
    this.best = null; this.last = null; this.bestTrace = null; this.trace = [];
    this.pace = 1; this.fuel = 70; this.ve = 0.97;
    this.wear = [0.02, 0.025, 0.018, 0.022];
    this.tyreT = [80, 82, 78, 80];
    this.brakeT = [400, 400, 380, 380];
    this.water = 88; this.oil = 98;
    this.pos = 7; this.classPos = 3; this.timeLeft = 2 * 3600;
    this.s1 = null; this.s2 = null; this.bs = [null, null, null];
    this.fuelLaps = []; this.veLaps = []; this.fuelStart = this.fuel; this.veStart = this.ve;
    this.event = null; this.eventT = 8; this.invalid = false;
  }

  // Vitesse cible le long du tour : lignes droites et virages
  target(d) {
    const x = d / this.L;
    const corners = [0.12, 0.27, 0.35, 0.52, 0.64, 0.78, 0.9];
    const mins = [95, 140, 75, 120, 160, 85, 130];
    let v = 300;
    corners.forEach((c, i) => {
      const dist = Math.abs(x - c) * this.L;
      v = Math.min(v, mins[i] + dist * 0.55);
    });
    return v * this.pace;
  }

  step(dt) {
    this.et += dt;
    // Dynamique simplifiée
    const tgt = this.target(this.d);
    const ahead = this.target((this.d + this.speed * 2) % this.L);
    let throttle = 0, brake = 0;
    if (ahead < this.speed - 8) { brake = Math.min(1, (this.speed - ahead) / 40); this.speed -= 95 * brake * dt * 1.6; }
    else if (tgt > this.speed) { throttle = 1; this.speed += (this.speed < 200 ? 32 : 18) * dt; }
    else { throttle = 0.35; }
    this.speed = Math.max(60, this.speed);

    // Boîte : on monte quand le régime atteint ~97 %, on descend en freinant
    const top = this.ratios[this.gear];
    if (this.speed > top * 0.985 && this.gear < 6) this.gear++;
    else if (this.gear > 1 && this.speed < this.ratios[this.gear - 1] * 0.82) this.gear--;
    const low = this.ratios[this.gear - 1] * 0.6;
    const rpm = 4200 + Math.max(0, Math.min(1, (this.speed - low) / (this.ratios[this.gear] - low))) * (this.maxRpm - 4200);

    // Avancement
    const prevD = this.d;
    this.d += (this.speed / 3.6) * dt;
    this.lapTime += dt;
    if (prevD < this.L / 3 && this.d >= this.L / 3) this.s1 = this.lapTime;
    if (prevD < (2 * this.L) / 3 && this.d >= (2 * this.L) / 3) this.s2 = this.lapTime - this.s1;
    if (this.trace.length === 0 || this.d > this.trace[this.trace.length - 1][0]) this.trace.push([this.d, this.lapTime]);
    if (this.d >= this.L) this.finishLap();

    // Thermique & usure
    for (let i = 0; i < 4; i++) {
      const load = throttle * 0.6 + brake * 1.2 + (this.speed / 300);
      this.tyreT[i] += ((70 + load * 28 + (i < 2 ? 3 : 0)) - this.tyreT[i]) * dt * 0.25;
      this.brakeT[i] += ((brake > 0 ? 760 : 360) - this.brakeT[i]) * dt * (brake > 0 ? 1.2 : 0.35) * (i < 2 ? 1 : 0.8);
      this.wear[i] = Math.min(1, this.wear[i] + dt * 0.00018 * (1 + load));
    }
    this.water += ((88 + throttle * 9) - this.water) * dt * 0.05;
    this.oil += ((98 + throttle * 12) - this.oil) * dt * 0.04;
    this.fuel = Math.max(0, this.fuel - dt * (0.012 + throttle * 0.05));
    this.ve = Math.max(0, this.ve - dt * (0.00012 + throttle * 0.00045));
    this.timeLeft = Math.max(0, this.timeLeft - dt);

    // Événements de course pour montrer les drapeaux et alertes
    this.eventT -= dt;
    if (this.eventT <= 0) {
      if (this.event) { this.event = null; this.eventT = 10 + Math.random() * 10; }
      else {
        const pool = ["yellow", "blue", "yellowAhead", "fcy", "penalty", "blue", "yellow"];
        this.event = pool[Math.floor(Math.random() * pool.length)];
        this.eventT = 5 + Math.random() * 3;
        if (Math.random() < 0.3) this.pos = Math.max(1, Math.min(24, this.pos + (Math.random() < 0.5 ? -1 : 1)));
        this.classPos = Math.max(1, Math.min(8, Math.ceil(this.pos / 3)));
      }
    }
    if (Math.random() < dt * 0.002) this.invalid = true; // ~1 tour sur 5

    return this.state(rpm, throttle, brake);
  }

  finishLap() {
    this.d -= this.L;
    const t = this.lapTime;
    const s3 = t - this.s1 - this.s2;
    this.last = t;
    if (!this.invalid && (this.best == null || t < this.best)) {
      this.best = t;
      this.bestTrace = this.trace.slice();
    }
    [this.s1, this.s2, s3].forEach((v, i) => { if (this.bs[i] == null || v < this.bs[i]) this.bs[i] = v; });
    this.fuelLaps = [...this.fuelLaps, this.fuelStart - this.fuel].slice(-5);
    this.veLaps = [...this.veLaps, this.veStart - this.ve].slice(-5);
    this.fuelStart = this.fuel; this.veStart = this.ve;
    if (this.fuel < 8) { this.fuel = 70; this.fuelStart = 82; this.ve = 0.97; this.veStart = 0.97; this.wear = this.wear.map(() => 0.01); }
    this.lap++; this.lapTime = 0; this.trace = []; this.s1 = this.s2 = null; this.invalid = false;
    this.pace = 0.985 + Math.random() * 0.03;
  }

  delta() {
    const tr = this.bestTrace;
    if (!tr) return null;
    let lo = 0, hi = tr.length - 1;
    if (this.d >= tr[hi][0]) return null;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (tr[m][0] < this.d) lo = m; else hi = m; }
    const [d0, t0] = tr[lo], [d1, t1] = tr[hi];
    return this.lapTime - (t0 + (t1 - t0) * ((this.d - d0) / (d1 - d0 || 1)));
  }

  state(rpm, throttle, brake) {
    const avg = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
    const fpl = avg(this.fuelLaps), vpl = avg(this.veLaps);
    const delta = this.delta();
    const sector = this.d < this.L / 3 ? 1 : this.d < (2 * this.L) / 3 ? 2 : 3;
    const ev = this.event;
    const names = ["AVG", "AVD", "ARG", "ARD"];
    return {
      connected: true, source: "demo",
      track: "Circuit de la Sarthe (démo)", vehicle: "Oreca 07 · LMP2", driver: "Démo",
      car: {
        gear: this.gear, rpm, maxRpm: this.maxRpm, speed: this.speed, throttle, brake, clutch: 0,
        waterTemp: this.water, oilTemp: this.oil, overheating: false, limiter: false,
        tc: 4, tcMax: 11, tcSlip: 3, tcSlipMax: 11, tcCut: 5, tcCutMax: 11, abs: 0, absMax: 0, motorMap: 1, motorMapMax: 3,
        brakeBias: 55.5, maxGears: 6, battery: null, damage: 0, detached: false,
      },
      lap: {
        number: this.lap, current: this.lapTime, last: this.last, best: this.best,
        delta, predicted: this.best != null && delta != null ? this.best + delta : null,
        invalid: this.invalid, sector,
        curS1: this.s1, curS2: this.s2, bestS1: this.bs[0], bestS2: this.bs[1], bestS3: this.bs[2],
      },
      fuel: {
        level: this.fuel, capacity: 75, perLap: fpl, lapsLeft: fpl ? this.fuel / fpl : null,
        ve: null, vePerLap: null, veLapsLeft: null,
      },
      tyres: names.map((name, i) => {
        const t = this.tyreT[i];
        return {
          name, inner: t + 6, center: t + 2, outer: t - 3, pressure: 168 + (t - 80) * 0.35,
          wear: this.wear[i], brake: this.brakeT[i], optimal: 85, flat: false, detached: false,
        };
      }),
      race: {
        session: "Course", isRace: true, position: this.pos, total: 24,
        classPosition: this.classPos, classTotal: 12, className: "LMP2",
        lapsDone: this.lap - 1, maxLaps: null,
        lapsLeft: this.best || this.last ? Math.ceil(this.timeLeft / (this.best || this.last)) : null,
        timeLeft: this.timeLeft, elapsed: this.et, gapAhead: 1.2 + Math.sin(this.et / 9) * 0.8,
        gapBehind: 2.1 + Math.cos(this.et / 11) * 1.1, pitstops: 0, inPits: false,
        ahead: { name: "R. Kubica", pos: this.pos - 1 }, behind: { name: "P. Hanson", pos: this.pos + 1 },
        timeOfDay: 15 * 3600 + this.et, trackLimits: 0,
      },
      flags: {
        phase: ev === "fcy" ? 6 : 5, green: !ev, yellow: ev === "yellow", yellowAhead: ev === "yellowAhead",
        fcy: ev === "fcy", blue: ev === "blue", red: false, checkered: this.timeLeft <= 0, formation: false,
        penalties: ev === "penalty" ? 1 : 0,
      },
      weather: { air: 21.5, track: 27.6, rain: 0, wet: 0 },
    };
  }
}
window.DemoSim = DemoSim;
