// Note and pitch mathematics, plus the cello specific string table.
// Pure functions only, so the same code can be unit tested off the browser.

export const A4_DEFAULT = 440.0;

const SEMITONES = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const NAMES_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

// Spoken forms, used in coaching text so we never print a bare "#" at the user.
const SPOKEN = { 'C#': 'C sharp', 'D#': 'D sharp', 'F#': 'F sharp', 'G#': 'G sharp', 'A#': 'A sharp' };

/** Parse scientific pitch notation ("C2", "F#3", "Bb3") into a MIDI number. */
export function noteToMidi(name) {
  const m = /^([A-Ga-g])([#b]?)(-?\d+)$/.exec(String(name).trim());
  if (!m) throw new Error(`not a note name: ${name}`);
  const letter = m[1].toUpperCase();
  const accidental = m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0;
  const octave = parseInt(m[3], 10);
  return (octave + 1) * 12 + SEMITONES[letter] + accidental;
}

export function midiToFreq(midi, a4 = A4_DEFAULT) {
  return a4 * Math.pow(2, (midi - 69) / 12);
}

export function noteToFreq(name, a4 = A4_DEFAULT) {
  return midiToFreq(noteToMidi(name), a4);
}

export function midiToName(midi) {
  const m = Math.round(midi);
  return NAMES_SHARP[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1);
}

/** Interval between two frequencies in cents. Positive means f is above ref. */
export function cents(f, ref) {
  return 1200 * Math.log2(f / ref);
}

/** Nearest equal tempered note to a frequency, with the deviation in cents. */
export function nearestNote(freq, a4 = A4_DEFAULT) {
  if (!(freq > 0)) return null;
  const exact = 69 + 12 * Math.log2(freq / a4);
  const midi = Math.round(exact);
  return { midi, name: midiToName(midi), cents: (exact - midi) * 100 };
}

/** Human readable note name, so "F#3" reads as "F sharp". */
export function spokenNote(name) {
  const m = /^([A-Ga-g][#b]?)(-?\d+)?$/.exec(String(name).trim());
  if (!m) return name;
  const head = m[1][0].toUpperCase() + m[1].slice(1);
  return SPOKEN[head] || head;
}

// The four cello strings. Identical on a 1/8 size instrument and a full size
// one: fractional cellos tune to standard pitch.
export const STRINGS = [
  { id: 'C', note: 'C2', index: 1, label: 'C string', hint: 'Thickest, nearest your left knee.' },
  { id: 'G', note: 'G2', index: 2, label: 'G string', hint: 'Second from the left.' },
  { id: 'D', note: 'D3', index: 3, label: 'D string', hint: 'Third from the left.' },
  { id: 'A', note: 'A3', index: 4, label: 'A string', hint: 'Thinnest, nearest your right knee.' },
];

export function stringById(id) {
  return STRINGS.find((s) => s.id === id) || null;
}

export function stringFreq(id, a4 = A4_DEFAULT) {
  const s = stringById(id);
  return s ? noteToFreq(s.note, a4) : NaN;
}

/**
 * Which string is this most likely to be? Returns the nearest string by
 * absolute cents distance along with that distance, so the caller can decide
 * whether the player is anywhere near a string at all.
 */
export function nearestString(freq, a4 = A4_DEFAULT) {
  if (!(freq > 0)) return null;
  let best = null;
  for (const s of STRINGS) {
    const target = noteToFreq(s.note, a4);
    const dev = cents(freq, target);
    if (!best || Math.abs(dev) < Math.abs(best.cents)) best = { string: s, cents: dev, target };
  }
  return best;
}

/**
 * Turn a cents deviation into instructions a complete beginner can act on.
 * The threshold matters: fine tuners have limited travel and are safe, pegs
 * move a lot for very little turn and are where strings get broken.
 */
export function tuningAdvice(centsOff) {
  const a = Math.abs(centsOff);
  const sharp = centsOff > 0;
  if (a <= 5) {
    return { state: 'in-tune', device: null, headline: 'In tune', detail: 'Leave this string alone and move to the next one.' };
  }
  const direction = sharp ? 'lower' : 'raise';
  const fineTurn = sharp ? 'anticlockwise' : 'clockwise';
  if (a <= 35) {
    return {
      state: sharp ? 'sharp' : 'flat',
      device: 'fine-tuner',
      headline: sharp ? 'Slightly sharp' : 'Slightly flat',
      detail: `Use the fine tuner at the tailpiece. Turn it ${fineTurn} by about a quarter turn to ${direction} the pitch, then check again.`,
    };
  }
  if (a <= 120) {
    return {
      state: sharp ? 'sharp' : 'flat',
      device: 'fine-tuner',
      headline: sharp ? 'Sharp' : 'Flat',
      detail: `Use the fine tuner, turning ${fineTurn} to ${direction} the pitch. If it runs out of travel before you reach the note, move to the peg.`,
    };
  }
  return {
    state: sharp ? 'very-sharp' : 'very-flat',
    device: 'peg',
    headline: sharp ? 'Far too sharp' : 'Far too flat',
    detail: sharp
      ? 'This needs the peg. Turn it very slightly to let the string down, then bring it back up onto the note from below.'
      : 'This needs the peg. Push the peg gently into its hole as you turn, and go in tiny amounts while watching the number.',
  };
}
