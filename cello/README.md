# Cello from scratch

A cello tuner and a fourteen lesson beginner course, for an adult learning on
a 1/8 size cello. Both apps listen through the microphone: the tuner reads the
pitch of each string, and the lessons grade your playing and tell you what to
change.

Two builds share one curriculum and one detection algorithm:

| | |
| --- | --- |
| **Web app** (`web/`) | Installable, works offline, served at `tamaradinneen.com/claudecello` |
| **Android app** (`android/`) | Kotlin and Compose, better audio path, no network permission at all |

## Honest notes about the instrument

A 1/8 cello is built for a child of roughly four to six. An adult will feel
folded around it, and the left hand spacing is about half of a full size
instrument. That is the instrument, not a fault in your technique. Everything
in this course transfers to a larger cello without relearning.

Fractional cellos tune to exactly the same pitches as a full size cello:
C2 (65.41 Hz), G2 (98.00), D3 (146.83), A3 (220.00). Small instruments drift
faster, so expect to tune every session.

## What makes the detection good

The heart of both apps is a YIN detector (de Cheveigné and Kawahara, 2002) with
two additions that matter for this instrument.

**The difference function is computed through an FFT.** A cello is extremely
rich in harmonics, and plain autocorrelation happily locks onto the second
harmonic and reports an octave too high. YIN's cumulative mean normalised
difference function, plus "take the first dip below threshold", picks the true
period instead. Doing it by FFT keeps a frame at 0.8 ms against a 21 ms hop.

**Multi-period refinement.** Parabolic interpolation on a single period leaves
a sub-sample residual, and the higher the note the more that residual is worth:
at 220 Hz one sample of lag is already 8 cents, so half a sample is audible on
a tuner. Once the period is known, the lag is measured across as many whole
periods as the analysis window holds, which divides that error by the number of
periods. On the validation set this cut the worst single frame error from
5.3 cents to 0.2.

Measured against synthesised bowed tones:

| Case | Median error | Worst frame |
| --- | --- | --- |
| Open strings, realistic spectrum | under 0.05 cents | 2.1 cents (C2) |
| Weak fundamental (the octave trap) | under 0.05 cents | 1.3 cents |
| Stopped notes used in the lessons | under 0.15 cents | 1.1 cents |
| Detuned by 5 to 250 cents | under 0.05 cents | 0.8 cents |
| With 30% broadband noise | 0.05 cents | 0.4 cents |

## What makes the feedback useful

Measuring the error is the easy half. The engine names a physical cause,
because on a cello nearly every audible fault has one:

- A wavering pitch on a **stopped** note is finger pressure easing, or the
  finger sliding.
- The same wavering on an **open** string is the bow drifting out of parallel
  with the bridge.
- Volume rising and falling across one note is the bow changing speed partway
  through the stroke.
- An error of about a semitone or more is reported as the **wrong note**, in
  semitones, not as poor intonation, because the fix is a different finger
  rather than a nudge. A lesson's own "slide the finger slightly" wording is
  only reused for a near miss, never when the player is four notes away.

The tuner applies the same principle: it always says which device to turn and
which way, fine tuner for small corrections and peg once that runs out of
travel, and a note far from every open string is named as a stopped note
instead of being reported as a catastrophically out of tune string.

## Why the Android app exists

Android's default capture path is tuned for speech, and all three standard
effects damage a sustained bowed note: automatic gain control pumps the level
so a long bow appears to swell and fade, noise suppression treats a steady tone
as background and attenuates it, and the echo canceller can comb filter the
result. The native app requests `MediaRecorder.AudioSource.UNPROCESSED`, then
explicitly releases any effect the platform attached anyway, and reports in the
Practise tab which source it actually got. A browser cannot do this; it can
only ask for `echoCancellation: false` and hope.

The app declares **no network permission at all**, so nothing can leave the
device even in principle.

## Layout

```
cello/
  shared/curriculum.json     the course, read by both apps
  web/                       the installable web app
    js/pitch.js              YIN detector
    js/analysis.js           note segmentation, grading, coaching
    js/tuner.js  js/lessons.js  js/tone.js  js/store.js
    worklet/capture.js       AudioWorklet capture stage
  android/                   Kotlin and Compose app
    app/src/main/kotlin/.../audio/      PitchDetector.kt, AudioEngine.kt, Tone.kt
    app/src/main/kotlin/.../lesson/     Analysis.kt, Curriculum.kt, Progress.kt
    app/src/test/kotlin/...             20 JVM unit tests
  tools/                     build and validation
```

## Build and verify

```bash
# Web: assemble the deployable site into cello/build/claudecello
tools/build_web.sh

# Detector, against synthesised bowed tones with known pitches
node tools/verify_detector.mjs

# Segmentation, grading and coaching, against simulated playing faults
node tools/verify_analysis.mjs

# The whole web app end to end, in Chromium, with a synthesised cello
# played through a fake microphone
python3 tools/make_test_tones.py /tmp/tones
node tools/verify_browser.mjs /tmp/tones

# Android
cd android && ANDROID_HOME=/opt/android-sdk gradle testDebugUnitTest assembleDebug
```

The browser harness is the one that matters most: the unit tests prove the
maths, but only that one proves `getUserMedia`, the AudioWorklet, the detector
and the interface are actually wired together and showing the right thing.

## Deployment

The web app is served by Caddy from `deploy/static/claudecello` in the
`tamaradinneen-site` repository. One detail is load bearing: that site sets
`Permissions-Policy: microphone=()` for everything, which blocks microphone
access outright, so the `/claudecello` route replaces it with
`microphone=(self)` for that path alone. Without that the tuner fails silently
with no obvious cause.
