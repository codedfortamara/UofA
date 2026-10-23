// The lesson runtime.
//
// Each step type gets its own small renderer and its own listening behaviour.
// Two rules run through all of them:
//
//  1. The player is never trapped. Every listening step offers a way past it,
//     because a beginner whose phone cannot quite hear their cello must still
//     be able to finish the course.
//  2. Feedback always names a cause. "25 cents flat" is a measurement; "slide
//     the finger slightly towards the bridge" is something you can do.

import { noteToFreq, stringById, spokenNote, cents } from './music.js';
import { NoteSegmenter, gradeNote, gradeSequence, gradeRhythm, coachFor, RHYTHM_COACH, resolveTarget } from './analysis.js';
import { Drone, Metronome, playReference } from './tone.js';
import { TunerView } from './tuner.js';

// A detected onset lags the real one: the analysis window covers the previous
// 85 ms of audio, and the segmenter waits for two consecutive confident frames
// before it calls a note real. This constant takes that out of rhythm scoring
// so the app does not accuse a player of being late when it is the detector
// that is behind. Interval spread, the other half of rhythm scoring, is immune
// to this by construction.
const ONSET_LATENCY_MS = 85;

export class LessonsView {
  constructor(root, { curriculum, engine, store, getA4, onProgress }) {
    this.root = root;
    this.curriculum = curriculum;
    this.engine = engine;
    this.store = store;
    this.getA4 = getA4;
    this.onProgress = onProgress || (() => {});
    this.runner = null;
    this.renderList();
  }

  get lessonsById() {
    if (!this._byId) {
      this._byId = new Map(this.curriculum.lessons.map((l) => [l.id, l]));
    }
    return this._byId;
  }

  renderList() {
    this.teardown();
    const state = this.store.get();
    const done = state.completed || {};
    const total = this.curriculum.lessons.length;
    const count = this.curriculum.lessons.filter((l) => done[l.id]).length;

    const units = this.curriculum.units
      .map((u) => {
        const items = u.lessons
          .map((id) => {
            const l = this.lessonsById.get(id);
            if (!l) return '';
            const n = this.curriculum.lessons.findIndex((x) => x.id === id) + 1;
            const isDone = !!done[id];
            return `<button class="lesson-item ${isDone ? 'done' : ''}" data-lesson="${id}">
              <span class="num">${isDone ? '&check;' : n}</span>
              <span class="body"><strong>${esc(l.title)}</strong>
              <span>${l.minutes} min &middot; ${esc(l.goal)}</span></span>
            </button>`;
          })
          .join('');
        return `<div class="unit-title">${esc(u.title)}</div>${items}`;
      })
      .join('');

    this.root.innerHTML = `
      <h2>The course</h2>
      <p>Fourteen lessons, five to ten minutes each, starting from never having held a cello.
      The app listens while you play and tells you what to change.</p>
      <div class="progress-rail"><span style="width:${((count / total) * 100).toFixed(0)}%"></span></div>
      <p class="caps" style="color:var(--gold-deep)">${count} of ${total} lessons done</p>
      ${units}
      <hr class="hairline">
      <div class="card flat">
        <h3 style="margin-top:0">About your instrument</h3>
        <p style="font-size:0.93rem">${esc(this.curriculum.sizeNote)}</p>
        <p style="font-size:0.93rem;margin-bottom:0">${esc(this.curriculum.tuningNote)}</p>
      </div>`;

    for (const b of this.root.querySelectorAll('[data-lesson]')) {
      b.addEventListener('click', () => this.openLesson(b.dataset.lesson));
    }
  }

  openLesson(id) {
    const lesson = this.lessonsById.get(id);
    if (!lesson) return;
    this.teardown();
    this.runner = new LessonRunner(this.root, {
      lesson,
      index: this.curriculum.lessons.findIndex((l) => l.id === id) + 1,
      engine: this.engine,
      store: this.store,
      getA4: this.getA4,
      onExit: () => { this.renderList(); this.onProgress(); },
      onComplete: () => {
        this.store.completeLesson(id);
        this.onProgress();
      },
    });
  }

  teardown() {
    if (this.runner) { this.runner.destroy(); this.runner = null; }
  }
}

class LessonRunner {
  constructor(root, opts) {
    this.root = root;
    this.lesson = opts.lesson;
    this.index = opts.index;
    this.engine = opts.engine;
    this.store = opts.store;
    this.getA4 = opts.getA4;
    this.onExit = opts.onExit;
    this.onComplete = opts.onComplete;
    this.stepIndex = 0;
    this.cleanup = [];
    this.startedAt = Date.now();
    this.render();
  }

  get step() { return this.lesson.steps[this.stepIndex]; }

  render() {
    this.stopListening();
    const total = this.lesson.steps.length;
    const pct = ((this.stepIndex / total) * 100).toFixed(0);
    this.root.innerHTML = `
      <div class="btn-row" style="margin-top:0">
        <button class="btn ghost" id="ls-back" style="flex:0 0 auto">&larr; All lessons</button>
      </div>
      <div class="step-head">
        <h2 style="margin:0">${esc(this.lesson.title)}</h2>
        <span class="step-count">Step ${this.stepIndex + 1} of ${total}</span>
      </div>
      <div class="progress-rail"><span style="width:${pct}%"></span></div>
      <div id="ls-step"></div>`;

    this.root.querySelector('#ls-back').addEventListener('click', () => { this.destroy(); this.onExit(); });
    const host = this.root.querySelector('#ls-step');
    const s = this.step;
    if (!s) return this.renderDone(host);

    switch (s.type) {
      case 'info': return this.renderInfo(host, s);
      case 'check': return this.renderCheck(host, s);
      case 'tune': return this.renderTune(host, s);
      case 'listen': return this.renderListen(host, s);
      case 'sequence': return this.renderSequence(host, s);
      case 'rhythm': return this.renderRhythm(host, s);
      case 'drone': return this.renderDrone(host, s);
      default: return this.renderInfo(host, { title: 'Step', body: ['This step type is not available.'] });
    }
  }

  next() {
    this.stopListening();
    if (this.stepIndex < this.lesson.steps.length - 1) {
      this.stepIndex++;
      this.render();
    } else {
      this.stepIndex = this.lesson.steps.length;
      this.render();
    }
  }

  renderDone(host) {
    const mins = Math.max(1, Math.round((Date.now() - this.startedAt) / 60000));
    this.store.addPracticeSeconds(Math.round((Date.now() - this.startedAt) / 1000));
    this.onComplete();
    host.innerHTML = `
      <div class="card">
        <h3 style="margin-top:0">Lesson complete</h3>
        <p>${esc(this.lesson.goal)}</p>
        <p style="color:var(--charcoal-soft);font-size:0.88rem">That took about ${mins} minute${mins === 1 ? '' : 's'}.</p>
        <div class="btn-row" style="margin-bottom:0">
          <button class="btn" id="ls-finish">Back to the course</button>
          <button class="btn ghost" id="ls-again">Repeat this lesson</button>
        </div>
      </div>`;
    host.querySelector('#ls-finish').addEventListener('click', () => { this.destroy(); this.onExit(); });
    host.querySelector('#ls-again').addEventListener('click', () => { this.stepIndex = 0; this.startedAt = Date.now(); this.render(); });
  }

  renderInfo(host, s) {
    host.innerHTML = `
      <div class="card">
        ${s.title ? `<h3 style="margin-top:0">${esc(s.title)}</h3>` : ''}
        ${(s.body || []).map((p) => `<p>${esc(p)}</p>`).join('')}
        ${s.tip ? `<div class="tip">${esc(s.tip)}</div>` : ''}
      </div>
      <div class="btn-row"><button class="btn wide" id="ls-next">Continue</button></div>`;
    host.querySelector('#ls-next').addEventListener('click', () => this.next());
  }

  renderCheck(host, s) {
    host.innerHTML = `
      <div class="card">
        <p>${esc(s.prompt || 'Check each of these.')}</p>
        <ul class="checklist">
          ${(s.items || []).map((it, i) => `<li><label><input type="checkbox" data-i="${i}"><span>${esc(it)}</span></label></li>`).join('')}
        </ul>
      </div>
      <div class="btn-row"><button class="btn wide" id="ls-next">Continue</button></div>`;
    host.querySelector('#ls-next').addEventListener('click', () => this.next());
  }

  renderTune(host, s) {
    host.innerHTML = `
      <div class="card">
        <p>${esc(s.prompt || 'Tune the cello.')}</p>
      </div>
      <div id="ls-tuner"></div>
      <div class="btn-row"><button class="btn wide" id="ls-next">Done tuning, continue</button></div>`;

    const tunerHost = host.querySelector('#ls-tuner');
    const tuner = new TunerView(tunerHost, {
      engine: this.engine,
      getA4: this.getA4,
      onTuned: () => { this.store.recordTuned(); announce('All four strings are in tune.'); },
      onStringDone: (id) => announce(`The ${id} string is in tune.`),
    });
    tuner.setGuided(s.strings || ['A', 'D', 'G', 'C']);
    tuner.attach();
    this.cleanup.push(() => tuner.detach());

    host.querySelector('#ls-next').addEventListener('click', () => this.next());
  }

  // ---- Listening steps -------------------------------------------------

  renderListen(host, s) {
    const a4 = this.getA4();
    const target = resolveTarget(s.target, a4);
    const reps = s.reps || 3;
    const passReps = Math.min(s.passReps || 2, reps);
    const attempts = [];

    host.innerHTML = `
      <div class="card">
        <p>${esc(s.prompt)}</p>
        <p class="caps" style="color:var(--gold-deep);margin-bottom:0">Target: ${esc(target ? target.label : 'a note')}${
          target && target.kind === 'note' ? ` (${target.hz.toFixed(1)} Hz)` : ''
        }</p>
      </div>
      <div class="stage">
        <div class="caps" id="li-state">Not listening</div>
        <div class="readout quiet"><span class="note" id="li-note">&ndash;</span><span class="oct" id="li-oct"></span></div>
        <div class="cents-line" id="li-cents"></div>
        <div class="hz-line" id="li-hint">Press start, then play</div>
        <div class="level"><span id="li-level"></span></div>
      </div>
      <div class="reps" id="li-reps"></div>
      <div id="li-feedback"></div>
      <div class="btn-row">
        <button class="btn" id="li-start">Start listening</button>
        <button class="btn ghost" id="li-ref">Hear it</button>
      </div>
      <div class="btn-row" style="margin-top:0">
        <button class="btn ghost" id="li-skip">Skip this step</button>
        <button class="btn gold" id="li-next" hidden>Continue</button>
      </div>`;

    const el = {
      state: host.querySelector('#li-state'),
      note: host.querySelector('#li-note'),
      oct: host.querySelector('#li-oct'),
      cents: host.querySelector('#li-cents'),
      hint: host.querySelector('#li-hint'),
      level: host.querySelector('#li-level'),
      reps: host.querySelector('#li-reps'),
      feedback: host.querySelector('#li-feedback'),
      start: host.querySelector('#li-start'),
      next: host.querySelector('#li-next'),
      readout: host.querySelector('.readout'),
    };

    const drawReps = () => {
      const pips = [];
      for (let i = 0; i < reps; i++) {
        const a = attempts[i];
        pips.push(`<span class="pip ${a ? (a.pass ? 'hit' : 'miss') : ''}"></span>`);
      }
      const hits = attempts.filter((a) => a.pass).length;
      el.reps.innerHTML = pips.join('') + `<span class="label">${hits} of ${passReps} good ${passReps === 1 ? 'try' : 'tries'} needed</span>`;
    };
    drawReps();

    host.querySelector('#li-ref').addEventListener('click', () => {
      if (this.engine.ctx && target) playReference(this.engine.ctx, target.hz, 2.0);
    });
    host.querySelector('#li-skip').addEventListener('click', () => this.next());
    el.next.addEventListener('click', () => this.next());

    const finish = (passed) => {
      this.stopListening();
      el.state.textContent = 'Finished';
      el.start.hidden = true;
      el.next.hidden = false;
      el.next.textContent = passed ? 'Well done, continue' : 'Continue anyway';
      if (passed) this.store.recordStepPass(this.lesson.id, this.stepIndex);
    };

    el.start.addEventListener('click', () => {
      if (this.listening) {
        this.stopListening();
        el.start.textContent = 'Start listening';
        el.state.textContent = 'Paused';
        return;
      }
      attempts.length = 0;
      drawReps();
      el.feedback.innerHTML = '';
      el.start.textContent = 'Stop';
      el.state.textContent = 'Listening';
      el.hint.textContent = 'Play the note and let it ring';

      // Judge a held note once it has comfortably met the asked for length,
      // rather than making the player stop bowing to find out how it went.
      const seg = new NoteSegmenter({ maxNoteSec: Math.max(2.5, (s.holdSec || 2) * 1.4) });
      this.startListening((f) => {
        el.level.style.width = `${Math.min(100, (f.rms / 0.08) * 100).toFixed(0)}%`;
        if (f.smoothHz && f.confidence >= 0.45) {
          el.readout.classList.remove('quiet');
          const n = nearestLabel(f.smoothHz, a4);
          el.note.textContent = n.name;
          el.oct.textContent = n.octave;
          if (target) {
            const off = cents(f.smoothHz, target.hz);
            el.cents.textContent = `${off > 0 ? '+' : '−'}${Math.round(Math.abs(off))} cents`;
          }
        } else {
          el.readout.classList.add('quiet');
        }

        const ev = seg.push(f);
        if (!ev || !target) return;

        const g = gradeNote(ev, target.hz, s);
        attempts.push(g);
        drawReps();
        el.feedback.innerHTML = feedbackCard(g, s);
        announce(g.pass ? 'Good.' : coachFor(s, g.issue, g.direction, g.measures.semitonesOff));

        const hits = attempts.filter((a) => a.pass).length;
        if (hits >= passReps) return finish(true);
        if (attempts.length >= reps) {
          el.feedback.innerHTML += `
            <div class="card flat">
              <p style="margin:0;font-size:0.92rem">That is the set finished with ${hits} good ${hits === 1 ? 'try' : 'tries'}.
              Have another go, or move on and come back to it.</p>
            </div>`;
          this.stopListening();
          el.start.textContent = 'Try the set again';
          el.state.textContent = 'Finished';
          el.next.hidden = false;
          el.next.textContent = 'Continue anyway';
        }
      });
    });
  }

  renderSequence(host, s) {
    const a4 = this.getA4();
    const expected = (s.notes || []).map((n) => noteToFreq(n, a4));
    const reps = s.reps || 3;
    const passReps = Math.min(s.passReps || 2, reps);
    let round = 0;
    let hits = 0;

    host.innerHTML = `
      <div class="card">
        <p>${esc(s.prompt)}</p>
        <div class="seq-notes" id="sq-notes">
          ${(s.notes || []).map((n, i) => `<span class="n ${i === 0 ? 'now' : ''}" data-i="${i}">${esc(spokenNote(n).replace(' sharp', '♯'))}</span>`).join('')}
        </div>
      </div>
      <div class="stage">
        <div class="caps" id="sq-state">Not listening</div>
        <div class="readout quiet"><span class="note" id="sq-note">&ndash;</span><span class="oct" id="sq-oct"></span></div>
        <div class="hz-line" id="sq-hint">Press start, then play the notes in order</div>
        <div class="level"><span id="sq-level"></span></div>
      </div>
      <div class="reps" id="sq-reps"></div>
      <div id="sq-feedback"></div>
      <div class="btn-row">
        <button class="btn" id="sq-start">Start listening</button>
        <button class="btn ghost" id="sq-ref">Hear the notes</button>
      </div>
      <div class="btn-row" style="margin-top:0">
        <button class="btn ghost" id="sq-skip">Skip this step</button>
        <button class="btn gold" id="sq-next" hidden>Continue</button>
      </div>`;

    const chips = [...host.querySelectorAll('#sq-notes .n')];
    const el = {
      state: host.querySelector('#sq-state'),
      note: host.querySelector('#sq-note'),
      oct: host.querySelector('#sq-oct'),
      hint: host.querySelector('#sq-hint'),
      level: host.querySelector('#sq-level'),
      reps: host.querySelector('#sq-reps'),
      feedback: host.querySelector('#sq-feedback'),
      start: host.querySelector('#sq-start'),
      next: host.querySelector('#sq-next'),
      readout: host.querySelector('.readout'),
    };

    const drawReps = () => {
      const pips = [];
      for (let i = 0; i < reps; i++) pips.push(`<span class="pip ${i < round ? (i < hits ? 'hit' : 'miss') : ''}"></span>`);
      el.reps.innerHTML = pips.join('') + `<span class="label">${hits} of ${passReps} clean run${passReps === 1 ? '' : 's'} needed</span>`;
    };
    drawReps();

    host.querySelector('#sq-ref').addEventListener('click', async () => {
      const ctx = this.engine.ctx;
      if (!ctx) return;
      for (let i = 0; i < expected.length; i++) {
        playReference(ctx, expected[i], 0.55, 0.14);
        await sleep(620);
      }
    });
    host.querySelector('#sq-skip').addEventListener('click', () => this.next());
    el.next.addEventListener('click', () => this.next());

    el.start.addEventListener('click', () => {
      if (this.listening) {
        this.stopListening();
        el.start.textContent = 'Start listening';
        el.state.textContent = 'Paused';
        return;
      }
      el.feedback.innerHTML = '';
      el.start.textContent = 'Stop';
      el.state.textContent = 'Listening';
      el.hint.textContent = 'Play the notes in order, with a small gap between each';
      chips.forEach((c, i) => { c.className = `n ${i === 0 ? 'now' : ''}`; });

      // A generous cap, so a note held indefinitely cannot stall a whole run.
      const seg = new NoteSegmenter({ maxNoteSec: 8 });
      const got = [];

      const judgeRun = () => {
        const r = gradeSequence(got, expected, s);
        round++;
        if (r.pass) hits++;
        drawReps();
        el.feedback.innerHTML = sequenceFeedback(r, s, s.notes || []);
        this.stopListening();
        if (hits >= passReps) {
          this.store.recordStepPass(this.lesson.id, this.stepIndex);
          el.state.textContent = 'Finished';
          el.start.hidden = true;
          el.next.hidden = false;
          el.next.textContent = 'Well done, continue';
        } else {
          el.state.textContent = 'Run finished';
          el.start.textContent = round >= reps ? 'Try again' : 'Play it again';
          el.next.hidden = false;
          el.next.textContent = 'Continue anyway';
        }
      };

      this.startListening((f) => {
        el.level.style.width = `${Math.min(100, (f.rms / 0.08) * 100).toFixed(0)}%`;
        if (f.smoothHz && f.confidence >= 0.45) {
          el.readout.classList.remove('quiet');
          const n = nearestLabel(f.smoothHz, a4);
          el.note.textContent = n.name;
          el.oct.textContent = n.octave;
        } else {
          el.readout.classList.add('quiet');
        }

        const ev = seg.push(f);
        if (!ev) return;
        const i = got.length;
        got.push(ev);
        if (i < expected.length) {
          const off = cents(ev.hz, expected[i]);
          const tol = s.toleranceCents != null ? s.toleranceCents : 45;
          const chip = chips[i];
          if (chip) {
            chip.className = 'n ' + (Math.abs(off) <= tol ? 'hit' : Math.abs(off) < 70 ? 'near' : 'bad');
          }
          if (chips[i + 1]) chips[i + 1].classList.add('now');
        }
        if (got.length >= expected.length) judgeRun();
      });
    });
  }

  renderRhythm(host, s) {
    const a4 = this.getA4();
    const target = resolveTarget(s.target, a4);
    const bpm = s.bpm || 60;
    const beats = s.beats || 8;
    const beatsPerNote = s.beatsPerNote || 1;
    const expectedNotes = Math.max(1, Math.round(beats / beatsPerNote));

    host.innerHTML = `
      <div class="card">
        <p>${esc(s.prompt)}</p>
        <p class="caps" style="color:var(--gold-deep);margin-bottom:0">${bpm} beats per minute${
          target ? ` &middot; on ${esc(target.label)}` : ''
        }</p>
      </div>
      <div class="stage">
        <div class="caps" id="rh-state">Not running</div>
        <div class="beat-dots" id="rh-dots" style="justify-content:center"></div>
        <div class="hz-line" id="rh-hint">Four clicks to count you in, then play</div>
        <div class="level"><span id="rh-level"></span></div>
      </div>
      <div id="rh-feedback"></div>
      <div class="btn-row">
        <button class="btn" id="rh-start">Start the metronome</button>
      </div>
      <div class="btn-row" style="margin-top:0">
        <button class="btn ghost" id="rh-skip">Skip this step</button>
        <button class="btn gold" id="rh-next" hidden>Continue</button>
      </div>
      <div class="tip">If your device is playing the clicks out loud, the microphone will hear them too.
      The click is pitched high on purpose so it is ignored, but headphones make this more reliable.</div>`;

    const el = {
      state: host.querySelector('#rh-state'),
      dots: host.querySelector('#rh-dots'),
      hint: host.querySelector('#rh-hint'),
      level: host.querySelector('#rh-level'),
      feedback: host.querySelector('#rh-feedback'),
      start: host.querySelector('#rh-start'),
      next: host.querySelector('#rh-next'),
    };

    const drawDots = (onCount, playedCount) => {
      const out = [];
      for (let i = 0; i < expectedNotes; i++) {
        const cls = i < playedCount ? 'played' : i === onCount ? 'on' : '';
        out.push(`<span class="d ${cls}"></span>`);
      }
      el.dots.innerHTML = out.join('');
    };
    drawDots(-1, 0);

    host.querySelector('#rh-skip').addEventListener('click', () => this.next());
    el.next.addEventListener('click', () => this.next());

    el.start.addEventListener('click', () => {
      const ctx = this.engine.ctx;
      if (!ctx) return;
      if (this.metronome) { this.stopListening(); el.start.textContent = 'Start the metronome'; el.state.textContent = 'Stopped'; return; }

      el.feedback.innerHTML = '';
      el.start.textContent = 'Stop';
      el.state.textContent = 'Counting you in';
      const countIn = 4;

      const metro = new Metronome(ctx);
      this.metronome = metro;
      const seg = new NoteSegmenter();
      const onsets = [];
      let gridStartPerf = null;
      let playedBeats = 0;

      metro.onBeat = ({ beat, countIn: isCountIn, ctxTime }) => {
        if (isCountIn) {
          el.hint.textContent = `Counting in: ${countIn - beat}`;
          return;
        }
        if (gridStartPerf == null) {
          gridStartPerf = metro.toPerformanceTime(ctxTime);
          el.state.textContent = 'Listening';
          el.hint.textContent = 'Play now, one note per click';
        }
        const noteIndex = Math.floor((beat - countIn) / beatsPerNote);
        drawDots(noteIndex, onsets.length);
        if (beat - countIn >= beats + beatsPerNote) {
          // One extra beat of grace so a final note still gets captured.
          finishRun();
        }
      };

      const finishRun = () => {
        const tail = seg.flush(performance.now());
        if (tail && onsets.length < expectedNotes) onsets.push(tail.startAt - ONSET_LATENCY_MS);
        metro.stop();
        this.metronome = null;
        this.stopListening();
        const r = gradeRhythm(onsets, gridStartPerf != null ? gridStartPerf : performance.now(), bpm, beats, {
          beatsPerNote,
          toleranceMs: s.toleranceMs || 180,
        });
        el.state.textContent = 'Finished';
        el.start.textContent = 'Try again';
        el.next.hidden = false;
        el.next.textContent = r.pass ? 'Well done, continue' : 'Continue anyway';
        if (r.pass) this.store.recordStepPass(this.lesson.id, this.stepIndex);
        const coach = (s.coach && s.coach[r.issue]) || RHYTHM_COACH[r.issue] || RHYTHM_COACH.good;
        el.feedback.innerHTML = `
          <div class="feedback ${r.pass ? 'good' : 'bad'}">
            <p>${esc(coach)}</p>
            <span class="measure">${esc(r.detail)}</span>
          </div>`;
        announce(coach);
      };

      metro.start(bpm, { beatsPerBar: 4, countIn });

      this.startListening((f) => {
        el.level.style.width = `${Math.min(100, (f.rms / 0.08) * 100).toFixed(0)}%`;
        if (gridStartPerf == null) return;
        // Discard frames contaminated by our own click.
        if (metro.nearClick(f.at, 60)) return;
        const ev = seg.push(f);
        if (!ev) return;
        onsets.push(ev.startAt - ONSET_LATENCY_MS);
        drawDots(-1, onsets.length);
        if (onsets.length >= expectedNotes) finishRun();
      });
    });
  }

  renderDrone(host, s) {
    const a4 = this.getA4();
    const hz = noteToFreq(s.note || 'D3', a4);
    host.innerHTML = `
      <div class="card">
        <p>${esc(s.prompt)}</p>
        <p class="caps" style="color:var(--gold-deep);margin-bottom:0">Drone on ${esc(spokenNote(s.note || 'D3'))}</p>
      </div>
      <div class="btn-row">
        <button class="btn" id="dr-toggle">Start the drone</button>
      </div>
      <div class="btn-row" style="margin-top:0"><button class="btn gold wide" id="ls-next">Continue</button></div>`;

    const btn = host.querySelector('#dr-toggle');
    btn.addEventListener('click', () => {
      const ctx = this.engine.ctx;
      if (!ctx) return;
      if (!this.drone) this.drone = new Drone(ctx);
      if (this.drone.playing) { this.drone.stop(); btn.textContent = 'Start the drone'; }
      else { this.drone.start(hz); btn.textContent = 'Stop the drone'; }
    });
    this.cleanup.push(() => { if (this.drone) { this.drone.stop(); this.drone = null; } });
    host.querySelector('#ls-next').addEventListener('click', () => this.next());
  }

  // ---- Frame subscription ---------------------------------------------

  startListening(fn) {
    this.stopListening();
    this.listening = this.engine.onFrame(fn);
  }

  stopListening() {
    if (this.listening) { this.listening(); this.listening = null; }
    if (this.metronome) { this.metronome.stop(); this.metronome = null; }
    while (this.cleanup.length) {
      const fn = this.cleanup.pop();
      try { fn(); } catch { /* best effort */ }
    }
  }

  destroy() { this.stopListening(); }
}

// ---- Presentation helpers ---------------------------------------------

function feedbackCard(g, step) {
  const coach = coachFor(step, g.issue, g.direction, g.measures ? g.measures.semitonesOff : null);
  return `
    <div class="feedback ${g.pass ? 'good' : 'bad'}">
      <p>${esc(coach)}</p>
      <span class="measure">${esc(g.detail)}</span>
    </div>`;
}

function sequenceFeedback(r, step, names) {
  if (r.pass) {
    return `<div class="feedback good"><p>${esc(coachFor(step, 'good'))}</p>
      <span class="measure">All ${r.total} notes inside the tolerance.</span></div>`;
  }
  const lines = [];
  if (r.missing) lines.push(`${r.missing} note${r.missing === 1 ? '' : 's'} did not come through.`);
  const wrong = r.results.filter((x) => x.wrongNote);
  const outOfTune = r.results.filter((x) => !x.pass && !x.wrongNote);
  if (wrong.length) {
    lines.push(
      `Wrong note on ${wrong.map((w) => `number ${w.index + 1} (${spokenNote(names[w.index] || '')})`).join(', ')}. Check the finger and the string.`
    );
  }
  if (outOfTune.length) {
    lines.push(
      `Out of tune on ${outOfTune
        .map((w) => `number ${w.index + 1}, ${Math.abs(Math.round(w.centsOff))} cents ${w.centsOff < 0 ? 'flat' : 'sharp'}`)
        .join('; ')}.`
    );
  }
  return `<div class="feedback bad">
      <p>${esc(lines.join(' '))}</p>
      <span class="measure">${r.correct} of ${r.total} notes correct.</span>
    </div>`;
}

function nearestLabel(hz, a4) {
  const n = nearestNoteName(hz, a4);
  const m = /^([A-G]#?)(-?\d+)$/.exec(n);
  return m ? { name: m[1], octave: m[2] } : { name: n, octave: '' };
}

function nearestNoteName(hz, a4) {
  const NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  const midi = Math.round(69 + 12 * Math.log2(hz / a4));
  return NAMES[((midi % 12) + 12) % 12] + (Math.floor(midi / 12) - 1);
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function announce(text) {
  const live = document.getElementById('live');
  if (live) live.textContent = text;
}

export { stringById };
