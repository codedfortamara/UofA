// Microphone capture and the analysis loop.
//
// The important part for a tuner is what we ask the browser NOT to do.
// Echo cancellation, noise suppression and automatic gain control are all
// designed for speech, and all three actively damage a sustained musical
// tone: the gain control pumps the level, the noise suppressor treats a
// steady note as background and attenuates it, and the echo canceller can
// introduce comb filtering. We switch all of them off.

import { PitchDetector, PitchSmoother } from './pitch.js';

export const MIC_CONSTRAINTS = {
  audio: {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
    channelCount: 1,
  },
  video: false,
};

export class AudioEngine {
  constructor({ frameSize = 4096, hopSize = 1024 } = {}) {
    this.frameSize = frameSize;
    this.hopSize = hopSize;
    this.ctx = null;
    this.stream = null;
    this.node = null;
    this.source = null;
    this.detector = null;
    this.smoother = new PitchSmoother();
    this.listeners = new Set();
    this.state = 'idle';
    this.lastError = null;
    this.appliedConstraints = null;
  }

  get sampleRate() {
    return this.ctx ? this.ctx.sampleRate : null;
  }

  onFrame(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** True when the page is in a context that is allowed to use a microphone. */
  static isSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.AudioWorkletNode);
  }

  async start() {
    if (this.state === 'running') return;
    this.state = 'starting';
    this.lastError = null;

    if (!AudioEngine.isSupported()) {
      this.state = 'error';
      this.lastError = { code: 'unsupported', message: 'This browser cannot capture audio. Try Chrome on Android, or Safari on iOS.' };
      throw this.lastError;
    }
    if (!window.isSecureContext) {
      this.state = 'error';
      this.lastError = { code: 'insecure', message: 'A microphone needs a secure connection. Open this page over https.' };
      throw this.lastError;
    }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
    } catch (err) {
      this.state = 'error';
      this.lastError = describeMicError(err);
      throw this.lastError;
    }

    const track = this.stream.getAudioTracks()[0];
    if (track && track.getSettings) this.appliedConstraints = track.getSettings();

    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === 'suspended') await this.ctx.resume();

    try {
      await this.ctx.audioWorklet.addModule(new URL('../worklet/capture.js', import.meta.url));
    } catch (err) {
      this.state = 'error';
      this.lastError = { code: 'worklet', message: 'The audio analyser failed to load. A reload usually fixes this.', cause: String(err) };
      throw this.lastError;
    }

    // The detector window is half the frame, because YIN needs 2*W samples to
    // compare a W sample window against itself at every lag up to W.
    this.detector = new PitchDetector(this.ctx.sampleRate, this.frameSize / 2);
    this.smoother.reset();

    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, 'capture-processor', {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      processorOptions: { frameSize: this.frameSize, hopSize: this.hopSize },
    });
    this.node.port.onmessage = (e) => this._handleFrame(e.data.frame);
    this.source.connect(this.node);

    this.state = 'running';
  }

  _handleFrame(frame) {
    if (!this.detector) return;
    let result;
    try {
      result = this.detector.detect(frame);
    } catch {
      return;
    }
    const smoothed = this.smoother.push(result.confidence >= 0.45 ? result.hz : null);
    const payload = {
      hz: result.hz,
      smoothHz: smoothed,
      confidence: result.confidence,
      rms: result.rms,
      reason: result.reason,
      at: performance.now(),
      frame,
    };
    for (const fn of this.listeners) {
      try { fn(payload); } catch { /* a bad listener must not stop the loop */ }
    }
  }

  async stop() {
    if (this.node) {
      try { this.node.port.postMessage('stop'); } catch { /* already gone */ }
      try { this.node.disconnect(); } catch { /* already gone */ }
    }
    if (this.source) { try { this.source.disconnect(); } catch { /* already gone */ } }
    if (this.stream) for (const t of this.stream.getTracks()) t.stop();
    if (this.ctx) { try { await this.ctx.close(); } catch { /* already gone */ } }
    this.node = null; this.source = null; this.stream = null; this.ctx = null;
    this.detector = null;
    this.smoother.reset();
    this.state = 'idle';
  }
}

export function describeMicError(err) {
  const name = err && err.name ? err.name : 'Error';
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return {
        code: 'denied',
        message: 'Microphone access was refused. Tap the padlock in the address bar, allow the microphone for this site, then reload.',
        cause: name,
      };
    case 'NotFoundError':
    case 'OverconstrainedError':
      return { code: 'no-device', message: 'No microphone was found on this device.', cause: name };
    case 'NotReadableError':
      return {
        code: 'busy',
        message: 'The microphone is in use by another app. Close any call or recording app, then try again.',
        cause: name,
      };
    default:
      return { code: 'unknown', message: `The microphone could not be started (${name}).`, cause: name };
  }
}
