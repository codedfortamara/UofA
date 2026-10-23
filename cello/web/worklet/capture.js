// AudioWorklet capture stage.
//
// It does no analysis. It collects the 128 sample render quanta into a ring
// buffer and posts one overlapping analysis frame per hop, transferring the
// buffer so there is no copy. Detection itself runs on the main thread from
// js/pitch.js, which keeps a single implementation of the algorithm rather
// than one copy here and another for the tests.

class CaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const o = options.processorOptions || {};
    this.frameSize = o.frameSize || 4096;
    this.hopSize = o.hopSize || 1024;
    this.ring = new Float32Array(this.frameSize);
    this.written = 0;
    this.sinceHop = 0;
    this.running = true;
    this.port.onmessage = (e) => {
      if (e.data === 'stop') this.running = false;
    };
  }

  process(inputs) {
    if (!this.running) return false;
    const input = inputs[0];
    if (!input || !input.length) return true;
    const channel = input[0];
    if (!channel) return true;

    const n = channel.length;
    const size = this.frameSize;
    const ring = this.ring;

    // Shift left by n and append. At 128 samples against a 4096 buffer this
    // copy is cheap and keeps the frame contiguous, which matters because the
    // detector wants a plain ordered window.
    ring.copyWithin(0, n);
    ring.set(channel, size - n);

    this.written += n;
    this.sinceHop += n;

    if (this.written >= size && this.sinceHop >= this.hopSize) {
      this.sinceHop = 0;
      const out = new Float32Array(size);
      out.set(ring);
      this.port.postMessage({ frame: out }, [out.buffer]);
    }
    return true;
  }
}

registerProcessor('capture-processor', CaptureProcessor);
