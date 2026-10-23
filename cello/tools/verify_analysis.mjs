// Validation of note segmentation, grading and rhythm scoring.
// Run: node cello/tools/verify_analysis.mjs
//
// These feed the engine synthetic frame streams that stand for specific
// playing faults, and assert it reaches the diagnosis a teacher would.

import { NoteSegmenter, gradeNote, gradeSequence, gradeRhythm, coachFor } from '../web/js/analysis.js';
import { noteToFreq, cents } from '../web/js/music.js';

const HOP_MS = 1024 / 48000 * 1000; // 21.33 ms, matching the real pipeline

let t = 0;
function resetClock() { t = 0; }

/** A stream of frames for one bowed note. */
function noteFrames({ hz, seconds, rms = 0.05, wobbleCents = 0, rmsCv = 0, conf = 0.95, driftCents = 0 }) {
  const frames = [];
  const n = Math.round((seconds * 1000) / HOP_MS);
  for (let i = 0; i < n; i++) {
    const phase = i / Math.max(1, n - 1);
    const wob = wobbleCents ? wobbleCents * Math.sin(i * 1.7) : 0;
    const drift = driftCents * phase;
    const amp = rms * (1 + (rmsCv ? rmsCv * Math.sin(i * 0.9) : 0));
    frames.push({
      hz: hz * Math.pow(2, (wob + drift) / 1200),
      confidence: conf,
      rms: amp,
      at: t,
    });
    t += HOP_MS;
  }
  return frames;
}

function silenceFrames(seconds) {
  const frames = [];
  const n = Math.round((seconds * 1000) / HOP_MS);
  for (let i = 0; i < n; i++) {
    frames.push({ hz: null, confidence: 0, rms: 0.0005, at: t });
    t += HOP_MS;
  }
  return frames;
}

function run(frames) {
  const seg = new NoteSegmenter();
  const out = [];
  for (const f of frames) {
    const ev = seg.push(f);
    if (ev) out.push(ev);
  }
  const tail = seg.flush(t);
  if (tail) out.push(tail);
  return out;
}

let failures = 0;
function assert(label, cond, extra = '') {
  if (!cond) failures++;
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${extra ? '   ' + extra : ''}`);
}

console.log('\nNote segmentation\n');
resetClock();
{
  const D = noteToFreq('D3');
  const events = run([...silenceFrames(0.3), ...noteFrames({ hz: D, seconds: 3 }), ...silenceFrames(0.4)]);
  assert('one bowed note yields one event', events.length === 1, `got ${events.length}`);
  if (events[0]) {
    assert('its duration is about right', Math.abs(events[0].durationSec - 3) < 0.25, `${events[0].durationSec.toFixed(2)} s`);
    assert('its pitch is the played pitch', Math.abs(cents(events[0].hz, D)) < 1, `${Math.abs(cents(events[0].hz, D)).toFixed(2)}c`);
  }
}

resetClock();
{
  const D = noteToFreq('D3');
  const A = noteToFreq('A3');
  const events = run([
    ...silenceFrames(0.2), ...noteFrames({ hz: D, seconds: 1.5 }),
    ...silenceFrames(0.3), ...noteFrames({ hz: A, seconds: 1.5 }),
    ...silenceFrames(0.3), ...noteFrames({ hz: D, seconds: 1.5 }), ...silenceFrames(0.3),
  ]);
  assert('three separated notes yield three events', events.length === 3, `got ${events.length}`);
}

resetClock();
{
  // Notes played legato, with no silence between them, must still separate.
  const events = run([
    ...silenceFrames(0.2),
    ...noteFrames({ hz: noteToFreq('D3'), seconds: 1.2 }),
    ...noteFrames({ hz: noteToFreq('E3'), seconds: 1.2 }),
    ...noteFrames({ hz: noteToFreq('F#3'), seconds: 1.2 }),
    ...silenceFrames(0.3),
  ]);
  assert('slurred notes split on the pitch change', events.length === 3, `got ${events.length}`);
}

resetClock();
{
  const events = run([...silenceFrames(0.2), ...noteFrames({ hz: noteToFreq('D3'), seconds: 0.05 }), ...silenceFrames(0.3)]);
  assert('a momentary scrape is not a note', events.length === 0, `got ${events.length}`);
}

{
  // A note held far longer than asked for must still be graded, and must not
  // be allowed to count as several attempts at once.
  resetClock();
  const seg = new NoteSegmenter({ maxNoteSec: 3 });
  const out = [];
  for (const f of [...silenceFrames(0.2), ...noteFrames({ hz: noteToFreq('D3'), seconds: 12 })]) {
    const ev = seg.push(f);
    if (ev) out.push(ev);
  }
  assert('a continuously held note is graded without stopping', out.length === 1, `got ${out.length}`);
  if (out[0]) assert('and it is capped near the limit', out[0].durationSec >= 2.9 && out[0].durationSec <= 3.2, `${out[0].durationSec.toFixed(2)} s`);
}
{
  // After the gap, a new note starts normally.
  resetClock();
  const seg = new NoteSegmenter({ maxNoteSec: 3 });
  const out = [];
  for (const f of [...silenceFrames(0.2), ...noteFrames({ hz: noteToFreq('D3'), seconds: 12 }),
                   ...silenceFrames(0.5), ...noteFrames({ hz: noteToFreq('D3'), seconds: 2 }), ...silenceFrames(0.4)]) {
    const ev = seg.push(f);
    if (ev) out.push(ev);
  }
  assert('a gap then a new note gives a second event', out.length === 2, `got ${out.length}`);
}

console.log('\nGrading a single note\n');
const spec = { toleranceCents: 35, holdSec: 3, metrics: ['pitch', 'duration', 'stability', 'tone'] };
const D3 = noteToFreq('D3');

function gradeOne(opts) {
  resetClock();
  const events = run([...silenceFrames(0.2), ...noteFrames(opts), ...silenceFrames(0.4)]);
  if (!events.length) return { pass: false, issue: 'silence', measures: {}, detail: 'no note' };
  return gradeNote(events[0], D3, spec);
}

{
  const r = gradeOne({ hz: D3, seconds: 3.2 });
  assert('a clean, in tune, steady note passes', r.pass && r.issue === 'good', r.detail);
}
{
  const r = gradeOne({ hz: D3 * Math.pow(2, -60 / 1200), seconds: 3.2 });
  assert('a note 60 cents low reads as flat', !r.pass && r.issue === 'flat', r.detail);
}
{
  const r = gradeOne({ hz: D3 * Math.pow(2, 55 / 1200), seconds: 3.2 });
  assert('a note 55 cents high reads as sharp', !r.pass && r.issue === 'sharp', r.detail);
}
{
  const r = gradeOne({ hz: D3, seconds: 1.0 });
  assert('a note cut short reads as short', !r.pass && r.issue === 'short', r.detail);
}
{
  const r = gradeOne({ hz: D3, seconds: 3.2, wobbleCents: 45 });
  assert('a wavering note reads as unstable', !r.pass && r.issue === 'unstable', r.detail);
}
{
  const r = gradeOne({ hz: D3, seconds: 3.2, rmsCv: 0.75 });
  assert('a note with surging volume reads as uneven', !r.pass && r.issue === 'uneven', r.detail);
}
{
  // Tolerance must be respected: 20 cents off with a 35 cent tolerance passes.
  const r = gradeOne({ hz: D3 * Math.pow(2, 20 / 1200), seconds: 3.2 });
  assert('20 cents off inside a 35 cent tolerance passes', r.pass, r.detail);
}
{
  // A note that is in tune but drifts away during the stroke.
  const r = gradeOne({ hz: D3, seconds: 3.2, driftCents: 70 });
  assert('a note that slides during the stroke is caught', !r.pass, r.detail);
}

console.log('\nHow far out a wrong note is, said in useful units\n');
{
  const cases = [
    [-90, 'a semitone'],
    [-55, '55 cents'],
    [150, 'about 2 semitones'],
    [-100, 'a semitone'],
    [200, '2 semitones'],
    [470, 'about 5 semitones'],
    [-700, '7 semitones'],
  ];
  for (const [off, expect] of cases) {
    resetClock();
    const r = gradeOne({ hz: D3 * Math.pow(2, off / 1200), seconds: 3.2 });
    assert(`${off} cents is described as "${expect}"`, r.detail.includes(expect), r.detail);
  }
}

console.log('\nCoaching text is specific to the lesson when provided\n');
{
  const step = { coach: { flat: 'Slide the finger a touch towards the bridge.' } };
  assert('lesson wording wins', coachFor(step, 'flat') === 'Slide the finger a touch towards the bridge.');
  assert('generic wording is the fallback', coachFor(step, 'uneven').includes('bow changing speed'));
  // A near miss can borrow the lesson's own flat wording; a huge miss must not,
  // because "nudge the finger" is wrong advice when you are four notes away.
  const nudge = { coach: { sharp: 'Slide the finger very slightly back.' } };
  assert('a near miss borrows the lesson wording', coachFor(nudge, 'wrongNote', 'sharp', 0.9).includes('very slightly'));
  assert('a large miss does not', !coachFor(nudge, 'wrongNote', 'sharp', 4.7).includes('very slightly'),
         coachFor(nudge, 'wrongNote', 'sharp', 4.7).slice(0, 60));
}

console.log('\nGrading a sequence of notes\n');
{
  const scale = ['D3', 'E3', 'F#3', 'G3'].map((n) => noteToFreq(n));
  resetClock();
  const frames = [];
  for (const hz of scale) { frames.push(...silenceFrames(0.25), ...noteFrames({ hz, seconds: 1.3 })); }
  frames.push(...silenceFrames(0.3));
  const events = run(frames);
  const r = gradeSequence(events, scale, { toleranceCents: 40 });
  assert('a correct four note scale passes', r.pass && r.correct === 4, `${r.correct}/${r.total}`);
}
{
  const scale = ['D3', 'E3', 'F#3', 'G3'].map((n) => noteToFreq(n));
  resetClock();
  const played = ['D3', 'E3', 'G3', 'G3'].map((n) => noteToFreq(n)); // third note wrong
  const frames = [];
  for (const hz of played) { frames.push(...silenceFrames(0.25), ...noteFrames({ hz, seconds: 1.3 })); }
  frames.push(...silenceFrames(0.3));
  const r = gradeSequence(run(frames), scale, { toleranceCents: 40 });
  assert('a wrong note is reported as a wrong note', !r.pass && r.results[2].wrongNote, `index 2 off by ${Math.round(r.results[2].centsOff)}c`);
}
{
  // The band boundary matters: poor intonation and a wrong finger must not be
  // conflated, because the advice for each is different.
  resetClock();
  const near = gradeOne({ hz: D3 * Math.pow(2, -45 / 1200), seconds: 3.2 });
  assert('45 cents out is an intonation slip, not a wrong note', near.issue === 'flat', near.detail);
  resetClock();
  const semitone = gradeOne({ hz: D3 * Math.pow(2, -100 / 1200), seconds: 3.2 });
  assert('a semitone out is reported as the wrong note', semitone.issue === 'wrongNote', semitone.detail);
  resetClock();
  const openString = gradeOne({ hz: noteToFreq('D3'), seconds: 3.2 });
  void openString;
  const twoSemis = gradeOne({ hz: D3 * Math.pow(2, 200 / 1200), seconds: 3.2 });
  assert('two semitones out says so in semitones', twoSemis.issue === 'wrongNote' && twoSemis.detail.includes('semitones'), twoSemis.detail);
}
{
  const scale = ['D3', 'E3', 'F#3', 'G3'].map((n) => noteToFreq(n));
  resetClock();
  const frames = [];
  for (const hz of scale.slice(0, 3)) { frames.push(...silenceFrames(0.25), ...noteFrames({ hz, seconds: 1.3 })); }
  frames.push(...silenceFrames(0.3));
  const r = gradeSequence(run(frames), scale, { toleranceCents: 40 });
  assert('a missing note is counted', r.missing === 1, `missing ${r.missing}`);
}

console.log('\nGrading rhythm\n');
{
  const bpm = 60, beats = 8, period = 60000 / bpm;
  const onTime = Array.from({ length: beats }, (_, i) => i * period);
  const r = gradeRhythm(onTime, 0, bpm, beats, { toleranceMs: 180 });
  assert('exactly on the click passes', r.pass && r.issue === 'good', r.detail);

  const early = onTime.map((x) => x - 250);
  const re = gradeRhythm(early, 0, bpm, beats, { toleranceMs: 180 });
  assert('consistently ahead reads as early', !re.pass && re.issue === 'early', re.detail);

  const late = onTime.map((x) => x + 300);
  const rl = gradeRhythm(late, 0, bpm, beats, { toleranceMs: 180 });
  assert('consistently behind reads as late', !rl.pass && rl.issue === 'late', rl.detail);

  const scattered = onTime.map((x, i) => x + (i % 2 ? 420 : -380));
  const rs = gradeRhythm(scattered, 0, bpm, beats, { toleranceMs: 180 });
  assert('inconsistent timing reads as scattered', !rs.pass && rs.issue === 'scattered', rs.detail);

  const few = onTime.slice(0, 5);
  const rf = gradeRhythm(few, 0, bpm, beats, { toleranceMs: 180 });
  assert('too few notes is reported', !rf.pass && rf.issue === 'missing', rf.detail);

  const rn = gradeRhythm([], 0, bpm, beats, { toleranceMs: 180 });
  assert('no notes at all is reported as silence', !rn.pass && rn.issue === 'silence', rn.detail);

  // Slightly loose but acceptable playing should still pass, or the app nags.
  const human = onTime.map((x, i) => x + [20, -35, 60, -20, 45, -50, 15, 30][i]);
  const rh = gradeRhythm(human, 0, bpm, beats, { toleranceMs: 180 });
  assert('ordinary human unevenness still passes', rh.pass, rh.detail);
}

console.log(`\n${failures === 0 ? 'All checks passed.' : failures + ' check(s) failed.'}\n`);
process.exit(failures === 0 ? 0 : 1);
