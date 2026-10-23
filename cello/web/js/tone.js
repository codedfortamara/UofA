// Sound the app makes itself: a reference drone, and a metronome.
//
// One subtlety drives both designs. The microphone is open while these play,
// so anything we emit is heard by our own detector. The drone is only used in
// play along steps where nothing is being graded. The metronome, though, runs
// during rhythm grading, so its click is deliberately pitched at 2.6 kHz,
// above the detector's 1320 Hz ceiling and well into the roll off of its
// 1200 Hz low pass, and kept to 12 ms, far shorter than the four consecutive
// frames the note segmenter needs before it will call something a note.

export class Drone {
  constructor(ctx) {
    this.ctx = ctx;
    this.nodes = null;
  }

  /** Additive synthesis, roughly a bowed string: strong odd harmonics. */
  start(hz, gain = 0.12) {
    this.stop();
    const ctx = this.ctx;
    const out = ctx.createGain();
    out.gain.value = 0;
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = Math.min(6000, hz * 14);
    filter.Q.value = 0.7;
    out.connect(filter);
    filter.connect(ctx.destination);

    const partials = [1, 0.62, 0.45, 0.28, 0.18, 0.11, 0.07];
    const oscs = [];
    partials.forEach((amp, i) => {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      // A touch of detune on the upper partials stops it sounding like a
      // synthesiser and closer to a bowed string.
      osc.frequency.value = hz * (i + 1) * (1 + (i > 1 ? (i % 2 ? 0.0008 : -0.0008) : 0));
      const g = ctx.createGain();
      g.gain.value = amp;
      osc.connect(g);
      g.connect(out);
      osc.start();
      oscs.push(osc);
    });

    const now = ctx.currentTime;
    out.gain.linearRampToValueAtTime(gain, now + 0.25);
    this.nodes = { out, filter, oscs };
  }

  stop() {
    if (!this.nodes) return;
    const { out, oscs } = this.nodes;
    const now = this.ctx.currentTime;
    try {
      out.gain.cancelScheduledValues(now);
      out.gain.setValueAtTime(out.gain.value, now);
      out.gain.linearRampToValueAtTime(0, now + 0.12);
    } catch { /* context may be closing */ }
    for (const o of oscs) {
      try { o.stop(now + 0.15); } catch { /* already stopped */ }
    }
    this.nodes = null;
  }

  get playing() { return !!this.nodes; }
}

export class Metronome {
  constructor(ctx) {
    this.ctx = ctx;
    this.bpm = 60;
    this.running = false;
    this.beat = 0;
    this.nextBeatTime = 0;
    this.timer = null;
    this.onBeat = null;
    this.beatsPerBar = 4;
    this.clickTimes = [];     // AudioContext times of emitted clicks
    this.startCtxTime = 0;
    this.startPerfTime = 0;
  }

  /** Map an AudioContext time to the performance.now() clock the frames use. */
  toPerformanceTime(ctxTime) {
    if (this.ctx.getOutputTimestamp) {
      const ts = this.ctx.getOutputTimestamp();
      if (ts && ts.contextTime != null && ts.performanceTime != null) {
        return ts.performanceTime + (ctxTime - ts.contextTime) * 1000;
      }
    }
    return this.startPerfTime + (ctxTime - this.startCtxTime) * 1000;
  }

  start(bpm = 60, { beatsPerBar = 4, countIn = 0 } = {}) {
    this.stop();
    this.bpm = bpm;
    this.beatsPerBar = beatsPerBar;
    this.beat = 0;
    this.running = true;
    this.clickTimes = [];
    this.startCtxTime = this.ctx.currentTime;
    this.startPerfTime = performance.now();
    // A little lead in so the first click is never late.
    this.nextBeatTime = this.ctx.currentTime + 0.15;
    this.countIn = countIn;
    this.firstPlayedBeatTime = this.nextBeatTime + (countIn * 60) / bpm;
    this._schedule();
    return this.firstPlayedBeatTime;
  }

  _schedule() {
    if (!this.running) return;
    const lookahead = 0.25;
    const period = 60 / this.bpm;
    while (this.nextBeatTime < this.ctx.currentTime + lookahead) {
      const accent = this.beat % this.beatsPerBar === 0;
      const isCountIn = this.beat < this.countIn;
      this._click(this.nextBeatTime, accent, isCountIn);
      this.clickTimes.push(this.nextBeatTime);
      if (this.onBeat) {
        const b = this.beat, t = this.nextBeatTime;
        this.onBeat({ beat: b, accent, countIn: isCountIn, ctxTime: t });
      }
      this.beat++;
      this.nextBeatTime += period;
    }
    this.timer = setTimeout(() => this._schedule(), 60);
  }

  _click(at, accent, isCountIn) {
    const ctx = this.ctx;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    // Above the detector's range, so our own click cannot be mistaken for the
    // cello. The count in is pitched lower purely so it sounds different.
    osc.frequency.value = isCountIn ? 1800 : accent ? 3000 : 2600;
    const peak = accent ? 0.3 : 0.2;
    gain.gain.setValueAtTime(0, at);
    gain.gain.linearRampToValueAtTime(peak, at + 0.001);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.012);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(at);
    osc.stop(at + 0.03);
  }

  /** True when a frame landed close enough to a click to be contaminated. */
  nearClick(perfTime, windowMs = 70) {
    for (const t of this.clickTimes) {
      if (Math.abs(perfTime - this.toPerformanceTime(t)) < windowMs) return true;
    }
    return false;
  }

  stop() {
    this.running = false;
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
  }
}

/** A short reference pitch, for "this is what the note sounds like". */
export function playReference(ctx, hz, seconds = 2.0, gain = 0.16) {
  const out = ctx.createGain();
  out.gain.value = 0;
  out.connect(ctx.destination);
  const partials = [1, 0.6, 0.4, 0.25, 0.15];
  const oscs = partials.map((amp, i) => {
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = hz * (i + 1);
    const g = ctx.createGain();
    g.gain.value = amp;
    osc.connect(g);
    g.connect(out);
    return osc;
  });
  const now = ctx.currentTime;
  out.gain.linearRampToValueAtTime(gain, now + 0.05);
  out.gain.setValueAtTime(gain, now + seconds - 0.2);
  out.gain.linearRampToValueAtTime(0, now + seconds);
  for (const o of oscs) { o.start(now); o.stop(now + seconds + 0.05); }
}
