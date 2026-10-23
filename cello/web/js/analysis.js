// Turning a stream of pitch frames into note events, and note events into
// feedback a beginner can act on.
//
// The design principle here: never tell someone "that was wrong". Measure the
// symptom, then name the physical cause, because on a cello almost every
// audible fault has one. A wavering pitch on an open string is a bow drifting
// out of parallel. A wavering pitch on a stopped note is finger pressure
// easing. An uneven volume is bow speed changing mid stroke. A beginner who is
// told which of those is happening can fix it; one who is told "out of tune"
// cannot.

import { cents, noteToFreq, stringFreq, spokenNote } from './music.js';

export const SEGMENT_DEFAULTS = {
  minConfidence: 0.5,
  onsetFrames: 2,      // consecutive good frames before a note is real
  offsetFrames: 4,     // consecutive bad frames before it has ended
  rmsFloor: 0.006,     // above the detector gate, so quiet scrapes do not count
  jumpCents: 150,      // a move this big means a new note, not the same one
  minFrames: 4,
  // Close a note that has gone on this long instead of waiting for it to
  // stop. Without this, someone holding a long steady bow gets no feedback
  // at all, which is precisely backwards: a long steady bow is the thing the
  // early lessons are asking for. Zero disables it.
  maxNoteSec: 0,
};

/**
 * Collects frames and emits note events. Push frames in order; the consumer
 * gets a callback when a note finishes, plus a live view of the note in
 * progress so the interface can show something while a note is held.
 */
export class NoteSegmenter {
  constructor(opts = {}) {
    this.cfg = { ...SEGMENT_DEFAULTS, ...opts };
    this.reset();
  }

  reset() {
    this.current = null;
    this.goodRun = 0;
    this.badRun = 0;
    this.events = [];
    // After a note is closed for length rather than for stopping, we wait for
    // an actual gap before opening another, so one continuous bow cannot burn
    // through every attempt in a set.
    this.awaitingGap = false;
  }

  /**
   * @param {{hz:number|null, confidence:number, rms:number, at:number}} f
   * @returns {object|null} a completed note event, if this frame ended one
   */
  push(f) {
    const good = !!f.hz && f.confidence >= this.cfg.minConfidence && f.rms >= this.cfg.rmsFloor;

    if (good) {
      this.badRun = 0;
      this.goodRun++;
      if (!this.current && !this.awaitingGap && this.goodRun >= this.cfg.onsetFrames) {
        this.current = { frames: [], startAt: f.at };
      }
      if (this.current) {
        const held = (f.at - this.current.startAt) / 1000;
        if (this.cfg.maxNoteSec > 0 && held >= this.cfg.maxNoteSec) {
          this.current.frames.push(f);
          const done = this._close(f.at);
          this.awaitingGap = true;
          if (done) return done;
        }
      }
      if (this.current) {
        // A large, immediate pitch move means the player changed note without
        // a gap. Close the old event and open a new one.
        const last = this.current.frames[this.current.frames.length - 1];
        if (last && Math.abs(cents(f.hz, last.hz)) > this.cfg.jumpCents) {
          const done = this._close(f.at);
          this.current = { frames: [f], startAt: f.at };
          if (done) return done;
        } else {
          this.current.frames.push(f);
        }
      }
      return null;
    }

    this.goodRun = 0;
    this.badRun++;
    if (this.badRun >= this.cfg.offsetFrames) this.awaitingGap = false;
    if (this.current && this.badRun >= this.cfg.offsetFrames) {
      return this._close(f.at);
    }
    return null;
  }

  /** Force the current note to end, e.g. when a step stops. */
  flush(at = null) {
    return this.current ? this._close(at) : null;
  }

  _close(endAt) {
    const note = this.current;
    this.current = null;
    if (!note || note.frames.length < this.cfg.minFrames) return null;
    const ev = summariseNote(note.frames, endAt);
    this.events.push(ev);
    return ev;
  }

  /** The note being played right now, if any, for live display. */
  live() {
    if (!this.current || this.current.frames.length < 2) return null;
    const f = this.current.frames;
    return { hz: median(f.map((x) => x.hz)), frames: f.length, startAt: this.current.startAt };
  }
}

function median(xs) {
  if (!xs.length) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function stdev(xs) {
  if (xs.length < 2) return 0;
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const v = xs.reduce((a, b) => a + (b - mean) * (b - mean), 0) / (xs.length - 1);
  return Math.sqrt(v);
}

/**
 * Reduce a note's frames to the numbers that matter. The attack and release
 * are deliberately excluded: every bowed note starts and ends unstable, and
 * judging someone on the scrape at the start of a stroke would be unfair and
 * unhelpful.
 */
export function summariseNote(frames, endAt = null) {
  const n = frames.length;
  const from = Math.min(Math.floor(n * 0.25), Math.max(0, n - 3));
  const to = Math.max(from + 1, Math.ceil(n * 0.9));
  const core = frames.slice(from, to);

  const hzs = core.map((f) => f.hz);
  const rmss = core.map((f) => f.rms);
  const hzMedian = median(hzs);
  const centsFromOwn = hzs.map((h) => cents(h, hzMedian));
  const rmsMean = rmss.reduce((a, b) => a + b, 0) / rmss.length;

  const last = frames[n - 1];
  const start = frames[0].at;
  const end = endAt != null ? endAt : last.at;

  return {
    hz: hzMedian,
    hzFirst: frames[0].hz,
    hzLast: last.hz,
    frames: n,
    startAt: start,
    endAt: end,
    durationSec: Math.max(0, (end - start) / 1000),
    wobbleCents: stdev(centsFromOwn),
    driftCents: cents(hzs[hzs.length - 1], hzs[0]),
    rmsMean,
    rmsCv: rmsMean > 0 ? stdev(rmss) / rmsMean : 0,
    confidence: median(core.map((f) => f.confidence)),
  };
}

export const GRADE_DEFAULTS = {
  wobbleCents: 22,     // standard deviation of pitch within one note
  rmsCv: 0.38,         // volume variation across one note
  durationFraction: 0.7,
  // Past this, it is not an intonation slip, it is a different note. The two
  // need opposite advice: 25 cents flat means nudge the finger towards the
  // bridge, whereas 100 cents flat means the wrong finger is down, or no
  // finger at all. Telling a beginner to "nudge" when they are a semitone out
  // sends them hunting in the wrong place.
  wrongNoteCents: 70,
};

/** Resolve a step target into a frequency and a label. */
export function resolveTarget(target, a4) {
  if (!target) return null;
  if (target.note) {
    return { hz: noteToFreq(target.note, a4), label: spokenNote(target.note), note: target.note, kind: 'note' };
  }
  if (target.string) {
    return { hz: stringFreq(target.string, a4), label: `the ${target.string} string`, note: target.string, kind: 'string' };
  }
  return null;
}

/**
 * Grade one note event against one step target.
 * @returns {{pass:boolean, issue:string, detail:string, measures:object}}
 */
export function gradeNote(ev, targetHz, spec = {}, grade = {}) {
  const g = { ...GRADE_DEFAULTS, ...grade };
  const tolerance = spec.toleranceCents != null ? spec.toleranceCents : 35;
  const wants = new Set(spec.metrics || ['pitch', 'duration']);
  const hold = spec.holdSec || 0;

  const off = cents(ev.hz, targetHz);
  const measures = {
    centsOff: off,
    durationSec: ev.durationSec,
    wobbleCents: ev.wobbleCents,
    rmsCv: ev.rmsCv,
  };

  const wrongNoteAt = Math.max(g.wrongNoteCents, tolerance * 1.6);
  const isWrongNote = wants.has('pitch') && Math.abs(off) >= wrongNoteAt;
  measures.semitonesOff = off / 100;
  measures.wrongNote = isWrongNote;

  const checks = [];
  if (wants.has('pitch')) checks.push({ name: 'pitch', ok: Math.abs(off) <= tolerance });
  if (wants.has('duration') && hold) {
    checks.push({ name: 'duration', ok: ev.durationSec >= hold * g.durationFraction });
  }
  if (wants.has('stability')) checks.push({ name: 'stability', ok: ev.wobbleCents <= g.wobbleCents });
  if (wants.has('tone')) checks.push({ name: 'tone', ok: ev.rmsCv <= g.rmsCv });

  const pass = checks.every((c) => c.ok);

  // Priority order for which single thing to mention. Pitch first because it
  // is what the lesson asked for; then length, because a note too short to
  // judge makes the other numbers meaningless.
  let issue = 'good';
  if (!pass) {
    const failed = new Set(checks.filter((c) => !c.ok).map((c) => c.name));
    if (failed.has('pitch')) issue = isWrongNote ? 'wrongNote' : off < 0 ? 'flat' : 'sharp';
    else if (failed.has('duration')) issue = 'short';
    else if (failed.has('stability')) issue = 'unstable';
    else if (failed.has('tone')) issue = 'uneven';
  }

  return {
    pass,
    issue,
    measures,
    direction: off < 0 ? 'flat' : 'sharp',
    detail: describeMeasures(measures, issue, tolerance),
  };
}

/**
 * Say how far out a wrong note is, in whatever unit is most informative.
 * Under a semitone, cents. Around a whole number of semitones, semitones,
 * because that is the unit that maps onto fingers. In between, both.
 */
function describeGap(absCents) {
  const semis = absCents / 100;
  if (semis < 0.8) return `${Math.round(absCents)} cents`;
  const rounded = Math.round(semis);
  const name = rounded === 1 ? 'a semitone' : `${rounded} semitones`;
  if (Math.abs(semis - rounded) <= 0.2) return name;
  return `${Math.round(absCents)} cents, about ${name}`;
}

function describeMeasures(m, issue, tolerance) {
  const parts = [];
  const a = Math.abs(m.centsOff);
  const dir = m.centsOff < 0 ? 'flat' : 'sharp';
  if (a < 4) parts.push('bang on the note');
  else if (m.wrongNote) parts.push(`${describeGap(a)} ${dir}`);
  else parts.push(`${Math.round(a)} cents ${dir}`);
  if (m.durationSec) parts.push(`held ${m.durationSec.toFixed(1)} s`);
  if (issue === 'unstable' || m.wobbleCents > 15) parts.push(`pitch moved by about ${Math.round(m.wobbleCents)} cents`);
  if (issue === 'uneven' || m.rmsCv > 0.3) parts.push(`volume varied by ${Math.round(m.rmsCv * 100)}%`);
  void tolerance;
  return parts.join(', ') + '.';
}

// Fallback coaching, used when a lesson step has nothing more specific. Every
// line names a cause, not just a symptom.
export const GENERIC_COACH = {
  silence: 'I did not hear a clear note. Check the bow has rosin, is tightened, and is touching the string between the fingerboard and the bridge.',
  flat: 'That was below the note. For a stopped note, slide the finger very slightly towards the bridge. For an open string, check the tuning.',
  sharp: 'That was above the note. For a stopped note, slide the finger very slightly back towards the scroll. For an open string, check the tuning.',
  short: 'The note was too short to judge properly. Slow the bow down and use more of its length so the sound lasts.',
  unstable: 'The pitch moved while the note was sounding. On a stopped note that is usually finger pressure easing off or the finger sliding. On an open string it is usually the bow drifting out of parallel with the bridge.',
  uneven: 'The volume rose and fell during the note. That is the bow changing speed or pressure partway through. Aim for one single speed from one end of the stroke to the other.',
  good: 'That one was good.',
  wrongNote: 'That is a different note, not just a slightly out of tune one. Check you are on the right string, and that the right finger is down in the right place.',
};

/**
 * Pick the coaching line for an issue, preferring the lesson's own wording.
 * For a wrong note we also try the lesson's flat or sharp line, because that
 * is usually where a lesson explains which string you have strayed onto.
 */
export function coachFor(step, issue, direction = null, semitonesOff = null) {
  const own = step && step.coach ? step.coach : null;
  if (own) {
    if (own[issue]) return own[issue];
    // Within about a semitone and a half, a lesson's own flat or sharp line is
    // still the right advice, and usually names the string to check. Beyond
    // that, "nudge the finger" is misleading, so use the generic wording.
    const near = semitonesOff == null || Math.abs(semitonesOff) <= 1.6;
    if (issue === 'wrongNote' && near && direction && own[direction]) return own[direction];
  }
  return GENERIC_COACH[issue] || GENERIC_COACH.good;
}

/**
 * Grade a run of notes against an expected sequence. Notes are matched in
 * order; a note that is nowhere near its expected pitch is reported as the
 * wrong note rather than as a very out of tune right one, because those need
 * different advice.
 */
export function gradeSequence(events, expectedHz, spec = {}) {
  const tolerance = spec.toleranceCents != null ? spec.toleranceCents : 45;
  const results = [];
  const n = Math.min(events.length, expectedHz.length);
  for (let i = 0; i < n; i++) {
    const off = cents(events[i].hz, expectedHz[i]);
    const wrongNote = Math.abs(off) >= Math.max(GRADE_DEFAULTS.wrongNoteCents, tolerance * 1.6);
    results.push({
      index: i,
      centsOff: off,
      pass: !wrongNote && Math.abs(off) <= tolerance,
      wrongNote,
      event: events[i],
    });
  }
  const missing = Math.max(0, expectedHz.length - events.length);
  const extra = Math.max(0, events.length - expectedHz.length);
  const correct = results.filter((r) => r.pass).length;
  return {
    results,
    missing,
    extra,
    correct,
    total: expectedHz.length,
    pass: missing === 0 && correct === expectedHz.length,
  };
}

/**
 * Grade onset times against a metronome grid.
 * @param {number[]} onsets milliseconds, in order
 * @param {number} startAt reference time of beat zero
 */
export function gradeRhythm(onsets, startAt, bpm, beats, { beatsPerNote = 1, toleranceMs = 180 } = {}) {
  const period = (60000 / bpm) * beatsPerNote;
  const expectedCount = Math.max(1, Math.round(beats / beatsPerNote));
  const errors = [];
  for (let i = 0; i < Math.min(onsets.length, expectedCount); i++) {
    errors.push(onsets[i] - (startAt + i * period));
  }
  if (!errors.length) {
    return { pass: false, issue: 'silence', meanMs: NaN, spreadMs: NaN, played: 0, expected: expectedCount, detail: 'I did not hear any notes.' };
  }
  const mean = errors.reduce((a, b) => a + b, 0) / errors.length;
  const spread = stdev(errors);
  const countOk = onsets.length >= expectedCount;
  const pass = countOk && Math.abs(mean) <= toleranceMs && spread <= toleranceMs;

  let issue = 'good';
  if (!pass) {
    if (!countOk) issue = onsets.length === 0 ? 'silence' : 'missing';
    else if (spread > toleranceMs) issue = 'scattered';
    else issue = mean < 0 ? 'early' : 'late';
  }
  const detail = countOk
    ? `${onsets.length} notes, on average ${Math.abs(Math.round(mean))} ms ${mean < 0 ? 'ahead of' : 'behind'} the click, spread ${Math.round(spread)} ms.`
    : `I heard ${onsets.length} of ${expectedCount} notes.`;
  return { pass, issue, meanMs: mean, spreadMs: spread, played: onsets.length, expected: expectedCount, detail };
}

export const RHYTHM_COACH = {
  silence: 'I did not hear any notes. Check the bow is making a sound, and that your device can hear the cello.',
  missing: 'Some notes did not come through. Make sure every stroke actually sounds, and keep going for the full count.',
  early: 'You are arriving ahead of the click. Let the click lead you rather than chasing it.',
  late: 'You are landing behind the click. Start the bow moving a fraction earlier, so the sound arrives on the beat.',
  scattered: 'The timing was uneven rather than consistently early or late. Count out loud, one, two, three, four, while you play.',
  good: 'Steady and in time.',
};
