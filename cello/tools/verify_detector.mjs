// Offline validation of the pitch detector against synthesised cello tones.
// Run: node cello/tools/verify_detector.mjs
//
// The point of this harness is that a tuner which is confidently wrong is
// worse than no tuner. Every case below has a known true frequency, so the
// error is measurable rather than a matter of opinion.

import { PitchDetector } from '../web/js/pitch.js';
import { noteToFreq, cents, STRINGS } from '../web/js/music.js';

const SR = 48000;
const W = 2048;

function synth(hz, { harmonics, seconds = 0.5, noise = 0, vibCents = 0, vibHz = 5, amp = 0.25 }) {
  const n = Math.round(SR * seconds);
  const out = new Float32Array(n);
  let phase = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    const detune = vibCents ? Math.pow(2, (vibCents * Math.sin(2 * Math.PI * vibHz * t)) / 1200) : 1;
    phase += (2 * Math.PI * hz * detune) / SR;
    let v = 0;
    for (let h = 0; h < harmonics.length; h++) v += harmonics[h] * Math.sin(phase * (h + 1));
    if (noise) v += noise * (Math.random() * 2 - 1);
    out[i] = v * amp;
  }
  return out;
}

// Amplitude profiles. "cello" is a realistic bowed spectrum; "weakFundamental"
// is the trap that makes naive autocorrelation report an octave too high, and
// is exactly what a real C string on a small cello looks like.
const PROFILES = {
  sine: [1],
  cello: [1.0, 0.7, 0.5, 0.35, 0.22, 0.15, 0.1, 0.07],
  weakFundamental: [0.18, 1.0, 0.8, 0.5, 0.3, 0.2, 0.12],
  bright: [0.5, 0.9, 1.0, 0.85, 0.6, 0.4, 0.3, 0.2, 0.12],
};

function measure(signal, trueHz) {
  const det = new PitchDetector(SR, W);
  const frame = new Float32Array(W * 2);
  const errs = [];
  let detected = 0, frames = 0;
  // Skip the first hop so the filters have settled.
  for (let off = 1024; off + W * 2 <= signal.length; off += 1024) {
    frame.set(signal.subarray(off, off + W * 2));
    const r = det.detect(frame);
    frames++;
    if (r.hz) {
      detected++;
      errs.push(cents(r.hz, trueHz));
    }
  }
  if (!errs.length) return { detectRate: 0, medianCents: NaN, maxAbsCents: NaN, frames };
  const sorted = [...errs].sort((a, b) => a - b);
  return {
    detectRate: detected / frames,
    medianCents: sorted[Math.floor(sorted.length / 2)],
    maxAbsCents: Math.max(...errs.map(Math.abs)),
    frames,
  };
}

let failures = 0;
function check(label, result, { maxMedian, maxWorst, minRate = 0.9 }) {
  const ok =
    result.detectRate >= minRate &&
    Math.abs(result.medianCents) <= maxMedian &&
    result.maxAbsCents <= maxWorst;
  if (!ok) failures++;
  const rate = (result.detectRate * 100).toFixed(0).padStart(3);
  const med = result.medianCents.toFixed(2).padStart(7);
  const worst = result.maxAbsCents.toFixed(2).padStart(7);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label.padEnd(44)} detect ${rate}%  median ${med}c  worst ${worst}c`);
}

console.log(`\nPitch detector validation, ${SR} Hz, window ${W} (${((W * 2) / SR * 1000).toFixed(0)} ms)\n`);

console.log('Open strings, realistic bowed spectrum');
for (const s of STRINGS) {
  const hz = noteToFreq(s.note);
  check(`${s.note} (${hz.toFixed(2)} Hz) cello spectrum`, measure(synth(hz, { harmonics: PROFILES.cello }), hz), { maxMedian: 0.5, maxWorst: 2.5 });
}

console.log('\nWeak fundamental, the octave error trap');
for (const s of STRINGS) {
  const hz = noteToFreq(s.note);
  check(`${s.note} weak fundamental`, measure(synth(hz, { harmonics: PROFILES.weakFundamental }), hz), { maxMedian: 0.5, maxWorst: 2.5 });
}

console.log('\nBright, harmonic heavy tone');
for (const s of STRINGS) {
  const hz = noteToFreq(s.note);
  check(`${s.note} bright`, measure(synth(hz, { harmonics: PROFILES.bright }), hz), { maxMedian: 0.5, maxWorst: 2.5 });
}

console.log('\nStopped notes used in the lessons');
for (const n of ['E3', 'F#3', 'G3', 'A3', 'B3', 'C#4', 'D4', 'A2', 'D2']) {
  const hz = noteToFreq(n);
  check(`${n} (${hz.toFixed(2)} Hz)`, measure(synth(hz, { harmonics: PROFILES.cello }), hz), { maxMedian: 0.5, maxWorst: 2.5 });
}

console.log('\nDetuned strings, which is the whole point of a tuner');
for (const off of [-250, -100, -50, -20, -5, 5, 20, 50, 100, 250]) {
  const hz = noteToFreq('D3') * Math.pow(2, off / 1200);
  const r = measure(synth(hz, { harmonics: PROFILES.cello }), hz);
  check(`D3 offset by ${String(off).padStart(4)} cents`, r, { maxMedian: 0.5, maxWorst: 2.5 });
}

console.log('\nAdverse conditions');
{
  const hz = noteToFreq('D3');
  check('D3 with 10% broadband noise', measure(synth(hz, { harmonics: PROFILES.cello, noise: 0.1 }), hz), { maxMedian: 2, maxWorst: 10 });
  check('D3 with 30% broadband noise', measure(synth(hz, { harmonics: PROFILES.cello, noise: 0.3 }), hz), { maxMedian: 3, maxWorst: 20 });
  check('D3 quiet (amp 0.02)', measure(synth(hz, { harmonics: PROFILES.cello, amp: 0.02 }), hz), { maxMedian: 2, maxWorst: 6 });
  check('D3 with 25 cent vibrato', measure(synth(hz, { harmonics: PROFILES.cello, vibCents: 25 }), hz), { maxMedian: 4, maxWorst: 32 });
  const c2 = noteToFreq('C2');
  check('C2 with 15% noise (worst case string)', measure(synth(c2, { harmonics: PROFILES.weakFundamental, noise: 0.15 }), c2), { maxMedian: 3, maxWorst: 15 });
}

console.log('\nSilence and noise must not produce a confident pitch');
{
  const det = new PitchDetector(SR, W);
  const silence = new Float32Array(W * 2);
  const r1 = det.detect(silence);
  const ok1 = r1.hz === null;
  if (!ok1) failures++;
  console.log(`${ok1 ? 'PASS' : 'FAIL'}  ${'digital silence returns no pitch'.padEnd(44)} ${r1.hz === null ? 'null' : r1.hz.toFixed(1) + ' Hz'}`);

  const det2 = new PitchDetector(SR, W);
  const noiseOnly = new Float32Array(W * 2);
  for (let i = 0; i < noiseOnly.length; i++) noiseOnly[i] = (Math.random() * 2 - 1) * 0.2;
  let confident = 0;
  for (let k = 0; k < 20; k++) {
    for (let i = 0; i < noiseOnly.length; i++) noiseOnly[i] = (Math.random() * 2 - 1) * 0.2;
    const r = det2.detect(noiseOnly);
    if (r.hz && r.confidence > 0.6) confident++;
  }
  const ok2 = confident <= 2;
  if (!ok2) failures++;
  console.log(`${ok2 ? 'PASS' : 'FAIL'}  ${'white noise rarely looks confident'.padEnd(44)} ${confident}/20 frames above 0.6`);
}

// Throughput: this has to be comfortable inside a 21 ms hop.
{
  const det = new PitchDetector(SR, W);
  const sig = synth(noteToFreq('D3'), { harmonics: PROFILES.cello, seconds: 2 });
  const frame = new Float32Array(W * 2);
  frame.set(sig.subarray(0, W * 2));
  const iterations = 300;
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < iterations; i++) det.detect(frame);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6 / iterations;
  const ok = ms < 10;
  if (!ok) failures++;
  console.log(`\n${ok ? 'PASS' : 'FAIL'}  ${'cost per frame'.padEnd(44)} ${ms.toFixed(2)} ms (hop is 21.3 ms)`);
}

console.log(`\n${failures === 0 ? 'All checks passed.' : failures + ' check(s) failed.'}\n`);
process.exit(failures === 0 ? 0 : 1);
