// Application shell: tabs, the microphone gate, and the practice tools.

import { AudioEngine } from './audio.js';
import { TunerView } from './tuner.js';
import { LessonsView } from './lessons.js';
import { Drone, Metronome } from './tone.js';
import { store } from './store.js';
import { noteToFreq, STRINGS, spokenNote } from './music.js';

const engine = new AudioEngine();
let curriculum = null;
let tuner = null;
let lessons = null;
let practice = null;
let currentTab = 'tune';

const el = {
  gate: document.getElementById('mic-gate'),
  gateError: document.getElementById('mic-error'),
  allow: document.getElementById('mic-allow'),
  views: {
    tune: document.getElementById('view-tune'),
    learn: document.getElementById('view-learn'),
    practise: document.getElementById('view-practise'),
  },
  tabs: {
    tune: document.getElementById('tab-tune'),
    learn: document.getElementById('tab-learn'),
    practise: document.getElementById('tab-practise'),
  },
  footRate: document.getElementById('foot-rate'),
};

function getA4() { return store.get().a4 || 440; }

function showTab(name) {
  currentTab = name;
  for (const k of Object.keys(el.views)) {
    const on = k === name;
    el.views[k].hidden = !on || engine.state !== 'running';
    el.tabs[k].setAttribute('aria-selected', String(on));
  }
  // Only the visible view should be consuming frames.
  if (tuner) { if (name === 'tune') tuner.attach(); else tuner.detach(); }
  if (practice) { if (name === 'practise') practice.attach(); else practice.detach(); }
  if (name === 'learn' && lessons) lessons.renderList();
}

for (const [name, btn] of Object.entries(el.tabs)) {
  btn.addEventListener('click', () => showTab(name));
}

// ---- Microphone gate ---------------------------------------------------

function showGate(message) {
  el.gate.hidden = false;
  for (const v of Object.values(el.views)) v.hidden = true;
  if (message) {
    el.gateError.hidden = false;
    el.gateError.textContent = message;
  } else {
    el.gateError.hidden = true;
  }
}

el.allow.addEventListener('click', async () => {
  el.allow.disabled = true;
  el.allow.textContent = 'Starting...';
  try {
    await engine.start();
    el.gate.hidden = true;
    el.gateError.hidden = true;
    buildViews();
    showTab(currentTab);
    describeRate();
  } catch (err) {
    el.allow.disabled = false;
    el.allow.textContent = 'Try again';
    showGate(err && err.message ? err.message : 'The microphone could not be started.');
  }
});

function describeRate() {
  if (!el.footRate) return;
  const sr = engine.sampleRate;
  if (!sr) return;
  const applied = engine.appliedConstraints || {};
  const processing = [
    applied.echoCancellation ? 'echo cancellation on' : null,
    applied.noiseSuppression ? 'noise suppression on' : null,
    applied.autoGainControl ? 'automatic gain on' : null,
  ].filter(Boolean);
  el.footRate.textContent =
    `Listening at ${(sr / 1000).toFixed(1)} kHz` +
    (processing.length
      ? `. Note: this device has ${processing.join(' and ')}, which can blur the reading.`
      : '. Signal processing is off, which is what a tuner wants.');
}

// ---- Practice tools ----------------------------------------------------

class PracticeView {
  constructor(root) {
    this.root = root;
    this.drone = null;
    this.metro = null;
    this.tuner = null;
    this.render();
  }

  render() {
    const s = store.get();
    const mins = Math.round((s.practiceSeconds || 0) / 60);
    const doneCount = Object.keys(s.completed || {}).length;

    this.root.innerHTML = `
      <h2>Practice tools</h2>
      <div class="stat-row">
        <div class="stat"><b>${doneCount}</b><span>lessons done</span></div>
        <div class="stat"><b>${mins}</b><span>minutes practised</span></div>
        <div class="stat"><b>${s.tunedCount || 0}</b><span>times tuned</span></div>
      </div>

      <div class="card">
        <h3 style="margin-top:0">Drone</h3>
        <p style="font-size:0.93rem">Play a scale against a held note. Notes that are in tune lock in and sound
        still; notes that are out produce a rough beating. This teaches your ear faster than any meter.</p>
        <div class="strings" id="pr-drone-strings"></div>
        <div class="btn-row" style="margin-bottom:0">
          <button class="btn" id="pr-drone">Start the drone</button>
        </div>
      </div>

      <div class="card">
        <h3 style="margin-top:0">Metronome</h3>
        <div class="field">
          <label for="pr-bpm">Tempo</label>
          <input type="range" id="pr-bpm" min="40" max="140" step="1" value="60">
          <output id="pr-bpm-out">60 bpm</output>
        </div>
        <div class="beat-dots" id="pr-beats"></div>
        <div class="btn-row" style="margin-bottom:0">
          <button class="btn" id="pr-metro">Start the metronome</button>
        </div>
      </div>

      <div class="card">
        <h3 style="margin-top:0">Reference pitch</h3>
        <div class="field">
          <label for="pr-a4">Concert A</label>
          <input type="number" id="pr-a4" min="415" max="466" step="0.5" value="${s.a4 || 440}">
          <span style="font-size:0.85rem;color:var(--charcoal-soft)">Hz</span>
        </div>
        <p style="font-size:0.88rem;color:var(--charcoal-soft);margin-bottom:0">Leave this at 440 unless you are
        playing with someone who tunes differently.</p>
      </div>

      <div class="card flat">
        <h3 style="margin-top:0">Progress</h3>
        <p style="font-size:0.9rem">Progress is kept on this device only. Nothing is uploaded anywhere.</p>
        <div class="btn-row" style="margin-bottom:0">
          <button class="btn ghost" id="pr-reset">Clear my progress</button>
        </div>
      </div>`;

    this.droneId = 'D';
    const droneHost = this.root.querySelector('#pr-drone-strings');
    droneHost.innerHTML = ['A', 'D', 'G', 'C']
      .map((id) => `<button type="button" data-d="${id}" aria-pressed="${id === this.droneId}">${id}<span class="tick"></span></button>`)
      .join('');
    for (const b of droneHost.querySelectorAll('button')) {
      b.addEventListener('click', () => {
        this.droneId = b.dataset.d;
        for (const x of droneHost.querySelectorAll('button')) x.setAttribute('aria-pressed', String(x.dataset.d === this.droneId));
        if (this.drone && this.drone.playing) this.drone.start(noteToFreq(stringNote(this.droneId), getA4()));
      });
    }

    const droneBtn = this.root.querySelector('#pr-drone');
    droneBtn.addEventListener('click', () => {
      const ctx = engine.ctx;
      if (!ctx) return;
      if (!this.drone) this.drone = new Drone(ctx);
      if (this.drone.playing) { this.drone.stop(); droneBtn.textContent = 'Start the drone'; }
      else { this.drone.start(noteToFreq(stringNote(this.droneId), getA4())); droneBtn.textContent = 'Stop the drone'; }
    });

    const bpm = this.root.querySelector('#pr-bpm');
    const bpmOut = this.root.querySelector('#pr-bpm-out');
    bpm.addEventListener('input', () => {
      bpmOut.textContent = `${bpm.value} bpm`;
      if (this.metro && this.metro.running) this.metro.bpm = Number(bpm.value);
    });

    const beats = this.root.querySelector('#pr-beats');
    beats.innerHTML = Array.from({ length: 4 }, () => '<span class="d"></span>').join('');
    const metroBtn = this.root.querySelector('#pr-metro');
    metroBtn.addEventListener('click', () => {
      const ctx = engine.ctx;
      if (!ctx) return;
      if (this.metro && this.metro.running) {
        this.metro.stop();
        metroBtn.textContent = 'Start the metronome';
        for (const d of beats.querySelectorAll('.d')) d.className = 'd';
        return;
      }
      this.metro = new Metronome(ctx);
      this.metro.onBeat = ({ beat }) => {
        const dots = [...beats.querySelectorAll('.d')];
        dots.forEach((d, i) => { d.className = 'd' + (i === beat % 4 ? ' on' : ''); });
      };
      this.metro.start(Number(bpm.value), { beatsPerBar: 4 });
      metroBtn.textContent = 'Stop the metronome';
    });

    const a4 = this.root.querySelector('#pr-a4');
    a4.addEventListener('change', () => {
      store.setA4(a4.value);
      a4.value = getA4();
    });

    this.root.querySelector('#pr-reset').addEventListener('click', () => {
      // A destructive action, so make it a deliberate two step choice.
      const btn = this.root.querySelector('#pr-reset');
      if (btn.dataset.confirm === '1') {
        store.reset();
        this.render();
        if (lessons) lessons.renderList();
        return;
      }
      btn.dataset.confirm = '1';
      btn.textContent = 'Tap again to confirm';
    });
  }

  attach() { this.render(); }

  detach() {
    if (this.drone) { this.drone.stop(); this.drone = null; }
    if (this.metro) { this.metro.stop(); this.metro = null; }
  }
}

function stringNote(id) {
  const s = STRINGS.find((x) => x.id === id);
  return s ? s.note : 'D3';
}

// ---- Boot --------------------------------------------------------------

function buildViews() {
  if (!tuner) {
    tuner = new TunerView(el.views.tune, {
      engine,
      getA4,
      onTuned: () => { store.recordTuned(); },
      onStringDone: () => {},
    });
  }
  if (!lessons && curriculum) {
    lessons = new LessonsView(el.views.learn, {
      curriculum,
      engine,
      store,
      getA4,
      onProgress: () => { if (practice) practice.render(); },
    });
  }
  if (!practice) practice = new PracticeView(el.views.practise);
}

async function boot() {
  try {
    const res = await fetch('curriculum.json', { cache: 'no-cache' });
    curriculum = await res.json();
  } catch {
    curriculum = null;
  }

  if (!AudioEngine.isSupported()) {
    showGate('This browser cannot capture audio. On Android use Chrome; on iPhone use Safari.');
    el.allow.disabled = true;
    return;
  }
  showGate(null);

  // Keep the tab bar usable before permission is granted, so the course text
  // can be read without the microphone.
  if (curriculum) {
    lessons = new LessonsView(el.views.learn, {
      curriculum, engine, store, getA4,
      onProgress: () => { if (practice) practice.render(); },
    });
  }
}

// A page reload while a lesson is running should not leave the stream open.
window.addEventListener('pagehide', () => { engine.stop(); });

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch(() => { /* offline support is a bonus, not a requirement */ });
  });
}

void spokenNote;
boot();
