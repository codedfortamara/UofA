// Monophonic pitch detection for cello, built on YIN (de Cheveigne and
// Kawahara, 2002) with the difference function computed through an FFT so it
// stays cheap enough to run every 21 ms on a phone.
//
// Why YIN rather than plain autocorrelation: a cello is extremely rich in
// harmonics, and raw autocorrelation happily locks onto the second harmonic
// and reports an octave too high. YIN's cumulative mean normalised difference
// function, combined with "take the first dip below threshold", picks the true
// period instead.
//
// Range is set for a cello: 55 Hz sits below a badly flat C string (65.4 Hz),
// and 1320 Hz is far above anything reachable in first position, which leaves
// headroom without inviting harmonic confusion.

/** In-place iterative radix-2 complex FFT with precomputed twiddles. */
class Fft {
  constructor(n) {
    if ((n & (n - 1)) !== 0) throw new Error('FFT size must be a power of two');
    this.n = n;
    this.cos = new Float64Array(n / 2);
    this.sin = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) {
      this.cos[i] = Math.cos((-2 * Math.PI * i) / n);
      this.sin[i] = Math.sin((-2 * Math.PI * i) / n);
    }
    this.rev = new Uint32Array(n);
    for (let i = 1, j = 0; i < n; i++) {
      let bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      this.rev[i] = j;
    }
  }

  transform(re, im, inverse = false) {
    const n = this.n;
    for (let i = 1; i < n; i++) {
      const j = this.rev[i];
      if (i < j) {
        let t = re[i]; re[i] = re[j]; re[j] = t;
        t = im[i]; im[i] = im[j]; im[j] = t;
      }
    }
    for (let len = 2; len <= n; len <<= 1) {
      const half = len >> 1;
      const stride = n / len;
      for (let i = 0; i < n; i += len) {
        for (let k = 0; k < half; k++) {
          const tw = k * stride;
          const wr = this.cos[tw];
          const wi = inverse ? -this.sin[tw] : this.sin[tw];
          const a = i + k;
          const b = a + half;
          const vr = re[b] * wr - im[b] * wi;
          const vi = re[b] * wi + im[b] * wr;
          re[b] = re[a] - vr;
          im[b] = im[a] - vi;
          re[a] += vr;
          im[a] += vi;
        }
      }
    }
    if (inverse) {
      for (let i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
    }
  }
}

function nextPow2(x) {
  let n = 1;
  while (n < x) n <<= 1;
  return n;
}

export const DEFAULTS = {
  minHz: 55,
  maxHz: 1320,
  threshold: 0.12,     // YIN absolute threshold on the normalised difference
  rmsGate: 0.0035,     // roughly -49 dBFS; below this we report silence
  octaveGuard: 0.80,   // prefer 2*tau when its dip is this much deeper
  maxPeriods: 16,      // periods to average over when refining the lag
  lowpassHz: 1200,     // gentle, to suppress high harmonics before detection
  highpassHz: 35,      // remove DC and handling rumble
};

export class PitchDetector {
  /**
   * @param {number} sampleRate
   * @param {number} windowSize analysis window W; tau can reach W, so the
   *   detector needs 2*W samples of input per frame.
   */
  constructor(sampleRate, windowSize = 2048, opts = {}) {
    this.sampleRate = sampleRate;
    this.W = windowSize;
    this.cfg = { ...DEFAULTS, ...opts };

    this.bufLen = windowSize * 2;
    this.tauMax = windowSize;
    this.fftSize = nextPow2(this.bufLen * 2);
    this.fft = new Fft(this.fftSize);

    this.re1 = new Float64Array(this.fftSize);
    this.im1 = new Float64Array(this.fftSize);
    this.re2 = new Float64Array(this.fftSize);
    this.im2 = new Float64Array(this.fftSize);
    this.filtered = new Float64Array(this.bufLen);
    this.cumSq = new Float64Array(this.bufLen + 1);
    this.diff = new Float64Array(this.tauMax + 2);
    this.cmnd = new Float64Array(this.tauMax + 2);

    this.tauFloor = Math.max(2, Math.floor(sampleRate / this.cfg.maxHz));
    this.tauCeil = Math.min(this.tauMax - 2, Math.ceil(sampleRate / this.cfg.minHz));

    this._initFilters();
  }

  _initFilters() {
    // One pole high pass for DC, plus a two pole Butterworth low pass.
    const hpK = Math.exp((-2 * Math.PI * this.cfg.highpassHz) / this.sampleRate);
    this.hpA = hpK;
    this.hpZ = 0;
    this.hpPrev = 0;

    const w0 = (2 * Math.PI * this.cfg.lowpassHz) / this.sampleRate;
    const cosw = Math.cos(w0);
    const alpha = Math.sin(w0) / (2 * Math.SQRT1_2);
    const b0 = (1 - cosw) / 2, b1 = 1 - cosw, b2 = (1 - cosw) / 2;
    const a0 = 1 + alpha, a1 = -2 * cosw, a2 = 1 - alpha;
    this.lp = { b0: b0 / a0, b1: b1 / a0, b2: b2 / a0, a1: a1 / a0, a2: a2 / a0 };
    this.lpState = { x1: 0, x2: 0, y1: 0, y2: 0 };
  }

  /** Parabolic vertex of the difference function around an integer lag. */
  _interpolate(d, t, limit) {
    if (t <= 0 || t >= limit) return t;
    const s0 = d[t - 1], s1 = d[t], s2 = d[t + 1];
    const denom = s0 - 2 * s1 + s2;
    if (denom === 0) return t;
    const shift = (s0 - s2) / (2 * denom);
    return shift > -1 && shift < 1 ? t + shift : t;
  }

  /** Reset filter history. Call when the input stream restarts. */
  reset() {
    this.hpZ = 0; this.hpPrev = 0;
    this.lpState = { x1: 0, x2: 0, y1: 0, y2: 0 };
  }

  /**
   * @param {Float32Array} samples exactly 2*windowSize samples.
   * @returns {{hz:number|null, confidence:number, rms:number, reason:string}}
   */
  detect(samples) {
    const n = this.bufLen;
    if (samples.length < n) throw new Error(`need ${n} samples, got ${samples.length}`);

    // Raw RMS first: the gate should reflect what the microphone actually
    // heard, not what survived the filters.
    let sumSq = 0;
    for (let i = 0; i < n; i++) sumSq += samples[i] * samples[i];
    const rms = Math.sqrt(sumSq / n);
    if (rms < this.cfg.rmsGate) {
      return { hz: null, confidence: 0, rms, reason: 'quiet' };
    }

    // Filter into the working buffer.
    const f = this.filtered;
    const lp = this.lp, st = this.lpState;
    let hpPrev = this.hpPrev, hpZ = this.hpZ;
    let x1 = st.x1, x2 = st.x2, y1 = st.y1, y2 = st.y2;
    for (let i = 0; i < n; i++) {
      const raw = samples[i];
      hpZ = raw - hpPrev + this.hpA * hpZ;
      hpPrev = raw;
      const x0 = hpZ;
      const y0 = lp.b0 * x0 + lp.b1 * x1 + lp.b2 * x2 - lp.a1 * y1 - lp.a2 * y2;
      x2 = x1; x1 = x0; y2 = y1; y1 = y0;
      f[i] = y0;
    }
    this.hpPrev = hpPrev; this.hpZ = hpZ;
    st.x1 = x1; st.x2 = x2; st.y1 = y1; st.y2 = y2;

    // Cumulative sum of squares, for the two power terms of the difference
    // function without an inner loop.
    const cs = this.cumSq;
    cs[0] = 0;
    for (let i = 0; i < n; i++) cs[i + 1] = cs[i] + f[i] * f[i];

    // r[tau] = sum_{j<W} f[j] * f[j+tau], via FFT cross correlation.
    const N = this.fftSize, W = this.W;
    const re1 = this.re1, im1 = this.im1, re2 = this.re2, im2 = this.im2;
    re1.fill(0); im1.fill(0); re2.fill(0); im2.fill(0);
    for (let i = 0; i < W; i++) re1[i] = f[i];
    for (let i = 0; i < n; i++) re2[i] = f[i];
    this.fft.transform(re1, im1);
    this.fft.transform(re2, im2);
    for (let i = 0; i < N; i++) {
      // conj(F1) * F2
      const ar = re1[i], ai = -im1[i];
      const br = re2[i], bi = im2[i];
      re1[i] = ar * br - ai * bi;
      im1[i] = ar * bi + ai * br;
    }
    this.fft.transform(re1, im1, true);

    const p1 = cs[W];
    const d = this.diff;
    const tauLimit = this.tauMax;
    for (let tau = 0; tau <= tauLimit; tau++) {
      const p2 = cs[tau + W] - cs[tau];
      const v = p1 + p2 - 2 * re1[tau];
      d[tau] = v > 0 ? v : 0;
    }

    // Cumulative mean normalised difference.
    const dp = this.cmnd;
    dp[0] = 1;
    let running = 0;
    for (let tau = 1; tau <= tauLimit; tau++) {
      running += d[tau];
      dp[tau] = running > 0 ? (d[tau] * tau) / running : 1;
    }

    // First dip below threshold inside the cello range, then descend to the
    // bottom of that dip.
    const lo = this.tauFloor, hi = this.tauCeil;
    let tau = -1;
    for (let t = lo; t <= hi; t++) {
      if (dp[t] < this.cfg.threshold) {
        while (t + 1 <= hi && dp[t + 1] < dp[t]) t++;
        tau = t;
        break;
      }
    }
    let periodic = true;
    if (tau < 0) {
      // Nothing clearly periodic. Fall back to the best dip available so the
      // tuner can still show something, but flag the low confidence.
      periodic = false;
      let bestT = lo, bestV = Infinity;
      for (let t = lo; t <= hi; t++) {
        if (dp[t] < bestV) { bestV = dp[t]; bestT = t; }
      }
      tau = bestT;
    }

    // Octave guard. If the period at twice this lag dips noticeably deeper,
    // we locked onto a harmonic and the real fundamental is an octave down.
    const twice = tau * 2;
    if (twice <= hi && dp[twice] < dp[tau] * this.cfg.octaveGuard) {
      let t = twice;
      while (t + 1 <= hi && dp[t + 1] < dp[t]) t++;
      tau = t;
    }

    // Multi-period refinement.
    //
    // Parabolic interpolation on a single period leaves a sub-sample residual,
    // and the higher the note the more that residual is worth in cents: at
    // 220 Hz one sample of lag is already 8 cents, so a 0.5 sample error is
    // audible on a tuner. Measuring across k periods at once divides that
    // error by k. We take the largest k whose lag still fits in the analysis
    // window, find the dip near k*tau, and interpolate there instead.
    const refineMax = tauLimit - 2;
    let k = Math.floor(refineMax / tau);
    if (k > this.cfg.maxPeriods) k = this.cfg.maxPeriods;
    if (k < 1) k = 1;

    let refined = this._interpolate(d, tau, tauLimit);
    if (k > 1) {
      const centre = tau * k;
      const span = Math.max(2, Math.round(tau * 0.25));
      let lo2 = centre - span, hi2 = centre + span;
      if (lo2 < 1) lo2 = 1;
      if (hi2 > refineMax) hi2 = refineMax;
      let bestT = centre, bestV = Infinity;
      for (let t = lo2; t <= hi2; t++) {
        if (d[t] < bestV) { bestV = d[t]; bestT = t; }
      }
      const refinedK = this._interpolate(d, bestT, tauLimit);
      // Only trust it if it genuinely lands near k whole periods, otherwise we
      // have wandered onto a neighbouring dip and the single period estimate
      // is the safer answer.
      if (Math.abs(refinedK / k - tau) <= tau * 0.1) refined = refinedK / k;
    }

    const hz = this.sampleRate / refined;
    if (!(hz >= this.cfg.minHz && hz <= this.cfg.maxHz)) {
      return { hz: null, confidence: 0, rms, reason: 'out-of-range' };
    }
    const confidence = Math.max(0, Math.min(1, 1 - dp[tau]));
    return {
      hz,
      confidence: periodic ? confidence : confidence * 0.5,
      rms,
      reason: periodic ? 'ok' : 'weak',
    };
  }
}

/**
 * Display smoothing. A tuner needle that twitches is unreadable, but one that
 * lags is useless, so this takes a median of recent frames (which rejects
 * single frame glitches outright) and rejects large jumps unless they persist.
 */
export class PitchSmoother {
  constructor({ size = 5, jumpCents = 120, jumpFrames = 3 } = {}) {
    this.size = size;
    this.jumpCents = jumpCents;
    this.jumpFrames = jumpFrames;
    this.history = [];
    this.pending = [];
  }

  reset() { this.history = []; this.pending = []; }

  push(hz) {
    if (!hz) {
      this.history = [];
      this.pending = [];
      return null;
    }
    const current = this.value();
    if (current) {
      const jump = Math.abs(1200 * Math.log2(hz / current));
      if (jump > this.jumpCents) {
        this.pending.push(hz);
        if (this.pending.length >= this.jumpFrames) {
          this.history = this.pending.slice();
          this.pending = [];
        }
        return current;
      }
    }
    this.pending = [];
    this.history.push(hz);
    if (this.history.length > this.size) this.history.shift();
    return this.value();
  }

  value() {
    if (!this.history.length) return null;
    const s = [...this.history].sort((a, b) => a - b);
    return s[Math.floor(s.length / 2)];
  }
}
