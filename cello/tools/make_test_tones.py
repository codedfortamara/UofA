#!/usr/bin/env python3
"""Synthesise cello-like WAV files to drive Chromium's fake microphone.

These let the browser test exercise the real pipeline end to end: getUserMedia,
the AudioWorklet, the detector and the interface, rather than just the maths.
"""
import math
import struct
import wave
import os
import sys

SR = 48000
# A realistic bowed spectrum. The fundamental is present but the second and
# third harmonics carry real weight, which is what trips naive detectors.
HARMONICS = [1.0, 0.70, 0.50, 0.35, 0.22, 0.15, 0.10]

NOTE_SEMITONES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def note_hz(name, a4=440.0):
    letter = name[0].upper()
    rest = name[1:]
    acc = 0
    if rest and rest[0] in '#b':
        acc = 1 if rest[0] == '#' else -1
        rest = rest[1:]
    midi = (int(rest) + 1) * 12 + NOTE_SEMITONES[letter] + acc
    return a4 * (2 ** ((midi - 69) / 12))


def write_tone(path, hz, seconds=6.0, amp=0.28, fade=0.02):
    n = int(SR * seconds)
    frames = bytearray()
    phase = 0.0
    step = 2 * math.pi * hz / SR
    fade_n = int(SR * fade)
    for i in range(n):
        phase += step
        v = sum(a * math.sin(phase * (k + 1)) for k, a in enumerate(HARMONICS))
        v *= amp / sum(HARMONICS)
        # Fade the ends so the loop point does not click, which would otherwise
        # register as a spurious note onset every time the file repeats.
        if i < fade_n:
            v *= i / fade_n
        elif i > n - fade_n:
            v *= (n - i) / fade_n
        s = max(-32767, min(32767, int(v * 32767)))
        frames += struct.pack('<h', s)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    return hz


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    os.makedirs(out, exist_ok=True)
    cases = [
        ('d3_intune.wav', note_hz('D3'), 0),
        ('a3_flat30.wav', note_hz('A3') * 2 ** (-30 / 1200), -30),
        ('g2_sharp18.wav', note_hz('G2') * 2 ** (18 / 1200), 18),
        ('c2_flat200.wav', note_hz('C2') * 2 ** (-200 / 1200), -200),
        ('fsharp3_intune.wav', note_hz('F#3'), 0),
    ]
    for name, hz, off in cases:
        p = os.path.join(out, name)
        write_tone(p, hz)
        print(f'{name}: {hz:.3f} Hz ({off:+d} cents)')
