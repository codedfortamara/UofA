// The tuner view.
//
// Design notes, because tuner interfaces are easy to get wrong for a beginner:
//
// 1. Auto string detection is the default, because someone new to the
//    instrument does not reliably know which string they just bowed. But in
//    the guided flow we lock to the requested string, otherwise a string that
//    is a long way out gets claimed by its neighbour and the user chases the
//    wrong target.
// 2. The meter is clamped to plus or minus 50 cents, and anything beyond that
//    pins at the edge. Showing 400 cents on a needle tells a beginner nothing;
//    "far too flat, use the peg" tells them what to do.
// 3. We always say which device to turn and which way. That single sentence is
//    the difference between a usable tuner and a frustrating one.

import { STRINGS, stringById, noteToFreq, cents, nearestNote, nearestString, tuningAdvice, spokenNote } from './music.js';
import { playReference } from './tone.js';

const METER_RANGE = 50;     // cents at the edge of the dial
const STRAY_CENTS = 250;    // beyond this from any open string, it is not one
const IN_TUNE = 5;          // cents, counts as done
const CLOSE = 15;           // cents, amber rather than red
const HOLD_FRAMES = 12;     // frames in tune before a string is marked done

export class TunerView {
  constructor(root, { engine, getA4, onTuned, onStringDone }) {
    this.root = root;
    this.engine = engine;
    this.getA4 = getA4;
    this.onTuned = onTuned || (() => {});
    this.onStringDone = onStringDone || (() => {});

    this.mode = 'auto';         // 'auto' or a string id
    this.done = new Set();
    this.inTuneRun = 0;
    this.lastDisplay = 0;
    this.targetOrder = ['A', 'D', 'G', 'C'];
    this.unsubscribe = null;
    this.active = false;
    this._render();
  }

  /** Restrict the tuner to one string, for a lesson's tuning step. */
  setGuided(order) {
    this.targetOrder = order && order.length ? order : ['A', 'D', 'G', 'C'];
    this.done.clear();
    this.mode = this.targetOrder[0];
    this._renderStrings();
    this._renderAdvice(null);
  }

  attach() {
    if (this.active) return;
    this.active = true;
    this.unsubscribe = this.engine.onFrame((f) => this._onFrame(f));
  }

  detach() {
    this.active = false;
    if (this.unsubscribe) { this.unsubscribe(); this.unsubscribe = null; }
  }

  _render() {
    this.root.innerHTML = `
      <div class="stage">
        <div class="caps" id="tn-mode">Listening</div>
        <div class="readout quiet" id="tn-readout">
          <span class="note" id="tn-note">&ndash;</span><span class="oct" id="tn-oct"></span>
        </div>
        <div class="cents-line" id="tn-cents"></div>
        <svg class="meter" id="tn-meter" viewBox="0 0 300 120" aria-hidden="true">
          <path class="track" d="M 56.03 83.80 A 100 100 0 0 1 243.97 83.80"
                fill="none" stroke-width="2"/>
          <path class="zone-close" d="M 114.16 24.64 A 100 100 0 0 1 185.84 24.64"
                fill="none" stroke-width="3"/>
          <path class="zone-good" d="M 137.81 18.75 A 100 100 0 0 1 162.19 18.75"
                fill="none" stroke-width="4"/>
          <g id="tn-ticks"></g>
          <line class="needle" id="tn-needle" x1="150" y1="118" x2="150" y2="26"
                stroke-width="2.5" style="transform-origin:150px 118px"/>
          <circle class="hub" cx="150" cy="118" r="4"/>
        </svg>
        <div class="verdict" id="tn-verdict">Play a string</div>
        <div class="hz-line" id="tn-hz"></div>
        <div class="level"><span id="tn-level"></span></div>
      </div>

      <div class="strings" id="tn-strings"></div>

      <div class="advice" id="tn-advice">
        <h4>Bow one string and hold it</h4>
        <p>Let the note ring while you read the meter. Work through A, then D, then G, then C.</p>
      </div>

      <div class="btn-row">
        <button class="btn ghost" id="tn-ref">Hear the target note</button>
        <button class="btn ghost" id="tn-reset">Start again</button>
      </div>

      <div class="card flat">
        <h3 style="margin-top:0">If a string will not come up to pitch</h3>
        <ul class="plain">
          <li>Use the fine tuner at the tailpiece for anything small. Clockwise raises the pitch.</li>
          <li>Pegs move a long way for very little turn. Push the peg gently inward as you turn it, or it will slip straight back.</li>
          <li>Always finish by coming up onto the note from below. A string tuned downward onto the note will drift flat again.</li>
          <li>Tune round all four strings twice. Each string changes the tension on the others.</li>
        </ul>
      </div>
    `;

    this._renderTicks();
    this._renderStrings();

    this.el = {
      mode: this.root.querySelector('#tn-mode'),
      readout: this.root.querySelector('#tn-readout'),
      note: this.root.querySelector('#tn-note'),
      oct: this.root.querySelector('#tn-oct'),
      centsLine: this.root.querySelector('#tn-cents'),
      needle: this.root.querySelector('#tn-needle'),
      verdict: this.root.querySelector('#tn-verdict'),
      hz: this.root.querySelector('#tn-hz'),
      level: this.root.querySelector('#tn-level'),
      advice: this.root.querySelector('#tn-advice'),
    };

    this.root.querySelector('#tn-ref').addEventListener('click', () => this._playReference());
    this.root.querySelector('#tn-reset').addEventListener('click', () => {
      this.done.clear();
      this.mode = 'auto';
      this.inTuneRun = 0;
      this._renderStrings();
      this._renderAdvice(null);
    });
  }

  _renderTicks() {
    const g = this.root.querySelector('#tn-ticks');
    const marks = [-50, -25, 0, 25, 50];
    const CX = 150, CY = 118, R = 100;
    g.innerHTML = marks
      .map((c) => {
        const rad = (((c / METER_RANGE) * 70 - 90) * Math.PI) / 180;
        const outer = R;
        const inner = c === 0 ? R - 14 : R - 9;
        const x1 = CX + outer * Math.cos(rad), y1 = CY + outer * Math.sin(rad);
        const x2 = CX + inner * Math.cos(rad), y2 = CY + inner * Math.sin(rad);
        const lx = CX + (R - 24) * Math.cos(rad), ly = CY + (R - 24) * Math.sin(rad);
        const stroke = c === 0 ? 'var(--good-bright)' : 'rgba(250,247,240,0.35)';
        return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"
                stroke="${stroke}" stroke-width="${c === 0 ? 2 : 1}"/>
                <text class="ticklabel" x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" text-anchor="middle">${c === 0 ? '0' : (c > 0 ? '+' : '\u2212') + Math.abs(c)}</text>`;
      })
      .join('');
  }

  _renderStrings() {
    const host = this.root.querySelector('#tn-strings');
    const order = ['A', 'D', 'G', 'C'];
    host.innerHTML =
      order
        .map((id) => {
          const s = stringById(id);
          const pressed = this.mode === id;
          const done = this.done.has(id);
          return `<button type="button" data-string="${id}" aria-pressed="${pressed}"
                   class="${done ? 'done' : ''}" aria-label="${s.label}">
                   ${id}<span class="tick">${done ? 'in tune' : ''}</span></button>`;
        })
        .join('') +
      `<button type="button" data-string="auto" aria-pressed="${this.mode === 'auto'}"
        aria-label="Detect the string automatically" style="font-size:0.78rem">Auto<span class="tick"></span></button>`;

    for (const b of host.querySelectorAll('button')) {
      b.addEventListener('click', () => {
        this.mode = b.dataset.string;
        this.inTuneRun = 0;
        this._renderStrings();
        this._renderAdvice(null);
      });
    }
  }

  _playReference() {
    const ctx = this.engine.ctx;
    if (!ctx) return;
    const id = this.mode === 'auto' ? this.targetOrder.find((s) => !this.done.has(s)) || 'A' : this.mode;
    const s = stringById(id);
    if (s) playReference(ctx, noteToFreq(s.note, this.getA4()), 2.2);
  }

  _onFrame(f) {
    if (!this.active) return;
    const a4 = this.getA4();
    const level = Math.min(1, f.rms / 0.08);
    if (this.el.level) this.el.level.style.width = `${(level * 100).toFixed(0)}%`;

    const hz = f.smoothHz;
    if (!hz || f.confidence < 0.45) {
      // Decay to the resting state rather than flickering off instantly.
      if (performance.now() - this.lastDisplay > 450) {
        this.el.readout.classList.add('quiet');
        this.el.verdict.textContent = 'Play a string';
        this.el.verdict.className = 'verdict';
        this.el.centsLine.textContent = '';
        this.el.hz.textContent = '';
        this.inTuneRun = 0;
      }
      return;
    }
    this.lastDisplay = performance.now();
    this.el.readout.classList.remove('quiet');

    let targetId, targetHz, off, strayed = false;
    if (this.mode === 'auto') {
      const near = nearestString(hz, a4);
      targetId = near.string.id;
      targetHz = near.target;
      off = near.cents;
      // Further than this from every open string and it is a stopped note, or
      // another instrument, rather than a string that needs tuning.
      strayed = Math.abs(near.cents) > STRAY_CENTS;
    } else {
      targetId = this.mode;
      targetHz = noteToFreq(stringById(targetId).note, a4);
      off = cents(hz, targetHz);
    }

    // What note did they actually play? Shown rather than the target, so an
    // accidental wrong string is obvious instead of confusing.
    const played = nearestNote(hz, a4);
    const nm = /^([A-G]#?)(-?\d+)$/.exec(played.name);
    this.el.note.textContent = nm ? nm[1] : played.name;
    this.el.oct.textContent = nm ? nm[2] : '';

    const abs = Math.abs(off);

    // A note nowhere near an open string is a stopped note. Reporting it as a
    // wildly out of tune string would send a beginner to the pegs for no
    // reason, so say what the note actually is and give no tuning advice.
    if (strayed) {
      const bare = played.name.replace(/-?\d+$/, '');
      this.el.centsLine.textContent = '';
      this.el.hz.textContent = `${hz.toFixed(1)} Hz`;
      this.el.mode.textContent = 'Not an open string';
      this.el.needle.style.transform = 'rotate(0deg)';
      this.el.needle.setAttribute('class', 'needle');
      this.el.verdict.className = 'verdict';
      this.el.verdict.textContent = `That is ${spokenNote(bare)}`;
      this._renderStray(bare);
      this.inTuneRun = 0;
      return;
    }

    this.el.centsLine.textContent = abs < 1 ? 'spot on' : `${off > 0 ? '+' : '−'}${Math.round(abs)} cents`;
    this.el.hz.textContent = `${hz.toFixed(1)} Hz, target ${targetHz.toFixed(1)} Hz`;
    this.el.mode.textContent = this.mode === 'auto' ? `Nearest: ${targetId} string` : `Tuning the ${targetId} string`;

    const clamped = Math.max(-METER_RANGE, Math.min(METER_RANGE, off));
    const angle = (clamped / METER_RANGE) * 70;
    this.el.needle.style.transform = `rotate(${angle.toFixed(2)}deg)`;

    const cls = abs <= IN_TUNE ? 'is-good' : abs <= CLOSE ? 'is-warn' : 'is-off';
    this.el.needle.setAttribute('class', `needle ${cls}`);
    this.el.verdict.className = `verdict ${cls}`;
    this.el.verdict.textContent =
      abs <= IN_TUNE ? 'In tune' : abs > METER_RANGE ? (off < 0 ? 'Far too flat' : 'Far too sharp') : off < 0 ? 'Flat' : 'Sharp';

    this._renderAdvice({ off, targetId });

    // Mark a string done only after it holds steady, so a needle swinging
    // through zero does not count as success.
    if (abs <= IN_TUNE) {
      this.inTuneRun++;
      if (this.inTuneRun === HOLD_FRAMES && !this.done.has(targetId)) {
        this.done.add(targetId);
        this._renderStrings();
        this.onStringDone(targetId, [...this.done]);
        if (this.targetOrder.every((s) => this.done.has(s))) this.onTuned([...this.done]);
        // Move the guided flow on to the next string that still needs work.
        if (this.mode !== 'auto') {
          const next = this.targetOrder.find((s) => !this.done.has(s));
          if (next) { this.mode = next; this._renderStrings(); }
        }
      }
    } else {
      this.inTuneRun = 0;
    }
  }

  _renderStray(bare) {
    const host = this.el.advice;
    if (!host) return;
    host.className = 'advice';
    host.innerHTML = `
      <span class="device">Not a tuning reading</span>
      <h4>That is ${spokenNote(bare)}, not an open string</h4>
      <p>The four open strings are C, G, D and A. If you are tuning, take every finger off the
      string and bow it again. If you meant to play that note, the tuner has nothing to add here.</p>`;
  }

  _renderAdvice(state) {
    const host = this.el ? this.el.advice : this.root.querySelector('#tn-advice');
    if (!host) return;
    if (!state) {
      const next = this.targetOrder.find((s) => !this.done.has(s));
      host.className = 'advice';
      host.innerHTML = next
        ? `<h4>Next: the ${next} string</h4><p>${stringById(next).hint} Bow it and let it ring while you read the meter.</p>`
        : `<h4>All four strings are in tune</h4><p>Go round once more to be sure. Tuning one string changes the tension on the others.</p>`;
      return;
    }
    const adv = tuningAdvice(state.off);
    const s = stringById(state.targetId);
    host.className = `advice${adv.state === 'in-tune' ? ' in-tune' : ''}`;
    const deviceLabel = adv.device === 'peg' ? 'Use the peg' : adv.device === 'fine-tuner' ? 'Use the fine tuner' : 'Done';
    host.innerHTML = `
      <span class="device">${deviceLabel}</span>
      <h4>${adv.headline}: ${s ? s.label : state.targetId}</h4>
      <p>${adv.detail}</p>`;
  }
}

export { STRINGS, spokenNote };
