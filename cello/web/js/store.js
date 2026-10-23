// Progress and settings, kept in localStorage. Everything here is per device
// and private: the app has no account, no server and sends nothing anywhere.

const KEY = 'claudecello.v1';

const DEFAULTS = {
  a4: 440,
  completed: {},        // lessonId -> ISO timestamp
  stepPasses: {},       // "lessonId:index" -> count of successful attempts
  lastLesson: null,
  practiceSeconds: 0,
  tunedCount: 0,
  seenIntro: false,
};

function read() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw);
    return { ...DEFAULTS, ...parsed };
  } catch {
    // Private browsing, cleared storage or a corrupt value. The app must work
    // either way, so fall back to defaults rather than failing to start.
    return { ...DEFAULTS };
  }
}

function write(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch { /* storage unavailable; the session still works, it just forgets */ }
}

export const store = {
  get() { return read(); },

  update(patch) {
    const next = { ...read(), ...patch };
    write(next);
    return next;
  },

  completeLesson(id) {
    const s = read();
    s.completed[id] = new Date().toISOString();
    s.lastLesson = id;
    write(s);
    return s;
  },

  recordStepPass(lessonId, index) {
    const s = read();
    const k = `${lessonId}:${index}`;
    s.stepPasses[k] = (s.stepPasses[k] || 0) + 1;
    write(s);
    return s;
  },

  recordTuned() {
    const s = read();
    s.tunedCount = (s.tunedCount || 0) + 1;
    write(s);
    return s;
  },

  addPracticeSeconds(sec) {
    if (!(sec > 0)) return read();
    const s = read();
    s.practiceSeconds = Math.round((s.practiceSeconds || 0) + sec);
    write(s);
    return s;
  },

  setA4(hz) {
    const v = Math.max(415, Math.min(466, Number(hz) || 440));
    return this.update({ a4: v });
  },

  reset() {
    try { localStorage.removeItem(KEY); } catch { /* nothing to remove */ }
    return { ...DEFAULTS };
  },
};
