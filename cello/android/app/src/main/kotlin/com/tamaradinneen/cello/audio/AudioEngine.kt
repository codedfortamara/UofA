package com.tamaradinneen.cello.audio

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.util.Log
import com.tamaradinneen.cello.lesson.Frame
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.concurrent.thread

/**
 * Microphone capture and the analysis loop.
 *
 * This is the main reason the native app reads more steadily than a browser.
 * Android's default capture path is tuned for speech, and all three of its
 * standard effects actively damage a sustained musical note: automatic gain
 * control pumps the level so a long bow appears to swell and fade, noise
 * suppression treats a steady tone as background and attenuates it, and the
 * echo canceller can comb filter the result.
 *
 * So we ask for UNPROCESSED, which is the source Android defines as having no
 * signal processing applied, and then explicitly release any effect that the
 * platform attached anyway. Not every device implements UNPROCESSED, so we
 * fall back deliberately and report which source we actually got, rather than
 * silently reading through a speech processor.
 */
class AudioEngine(
    private val requestedSampleRate: Int = 48000,
    private val frameSize: Int = 4096,
    private val hopSize: Int = 1024,
) {
    data class Status(
        val running: Boolean = false,
        val sampleRate: Int = 0,
        val source: String = "",
        val unprocessed: Boolean = false,
        val effectsDisabled: List<String> = emptyList(),
        val error: String? = null,
    )

    private val _status = MutableStateFlow(Status())
    val status: StateFlow<Status> = _status

    private val listeners = CopyOnWriteArrayList<(Frame) -> Unit>()
    private var record: AudioRecord? = null
    private var worker: Thread? = null
    @Volatile private var running = false

    private var agc: AutomaticGainControl? = null
    private var ns: NoiseSuppressor? = null
    private var aec: AcousticEchoCanceler? = null

    private val smoother = PitchSmoother()
    @Volatile var lastSmoothHz: Double? = null
        private set

    fun addListener(fn: (Frame) -> Unit): () -> Unit {
        listeners.add(fn)
        return { listeners.remove(fn) }
    }

    /** Sources in order of preference for pitch work. */
    private fun candidateSources(): List<Pair<Int, String>> {
        val out = mutableListOf<Pair<Int, String>>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            out.add(MediaRecorder.AudioSource.UNPROCESSED to "UNPROCESSED")
        }
        out.add(MediaRecorder.AudioSource.VOICE_RECOGNITION to "VOICE_RECOGNITION")
        out.add(MediaRecorder.AudioSource.MIC to "MIC")
        return out
    }

    @SuppressLint("MissingPermission")
    fun start(): Boolean {
        if (running) return true

        val rates = intArrayOf(requestedSampleRate, 44100, 48000, 22050)
        for ((source, label) in candidateSources()) {
            for (rate in rates.distinct()) {
                val minBuf = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_FLOAT)
                if (minBuf <= 0) continue
                // A generous buffer: a dropped read costs a visible stutter on
                // the needle, and the memory is trivial.
                val bufBytes = maxOf(minBuf, frameSize * 4 * 4)
                val rec = try {
                    AudioRecord(source, rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_FLOAT, bufBytes)
                } catch (e: Exception) {
                    Log.w(TAG, "AudioRecord($label, $rate) threw: ${e.message}")
                    null
                }
                if (rec == null) continue
                if (rec.state != AudioRecord.STATE_INITIALIZED) { rec.release(); continue }

                val disabled = disableEffects(rec.audioSessionId)
                record = rec
                return launch(rec, rate, label, source == MediaRecorder.AudioSource.UNPROCESSED, disabled)
            }
        }
        _status.value = Status(error = "No usable microphone was found on this device.")
        return false
    }

    /**
     * Release any speech processing the platform attached to our session.
     * Each of these is a no-op where the device does not implement it.
     */
    private fun disableEffects(sessionId: Int): List<String> {
        val off = mutableListOf<String>()
        try {
            if (AutomaticGainControl.isAvailable()) {
                agc = AutomaticGainControl.create(sessionId)?.also { if (it.enabled) it.enabled = false; off.add("automatic gain") }
            }
        } catch (e: Exception) { Log.w(TAG, "AGC: ${e.message}") }
        try {
            if (NoiseSuppressor.isAvailable()) {
                ns = NoiseSuppressor.create(sessionId)?.also { if (it.enabled) it.enabled = false; off.add("noise suppression") }
            }
        } catch (e: Exception) { Log.w(TAG, "NS: ${e.message}") }
        try {
            if (AcousticEchoCanceler.isAvailable()) {
                aec = AcousticEchoCanceler.create(sessionId)?.also { if (it.enabled) it.enabled = false; off.add("echo cancellation") }
            }
        } catch (e: Exception) { Log.w(TAG, "AEC: ${e.message}") }
        return off
    }

    private fun launch(rec: AudioRecord, rate: Int, label: String, unprocessed: Boolean, disabled: List<String>): Boolean {
        return try {
            rec.startRecording()
            if (rec.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
                rec.release(); record = null
                _status.value = Status(error = "The microphone is in use by another app. Close any call or recording app, then try again.")
                return false
            }
            running = true
            smoother.reset()
            _status.value = Status(true, rate, label, unprocessed, disabled, null)
            worker = thread(name = "cello-audio", priority = Thread.MAX_PRIORITY) { loop(rec, rate) }
            true
        } catch (e: Exception) {
            rec.release(); record = null
            _status.value = Status(error = "The microphone could not be started (${e.javaClass.simpleName}).")
            false
        }
    }

    private fun loop(rec: AudioRecord, rate: Int) {
        val detector = PitchDetector(rate, frameSize / 2)
        val ring = FloatArray(frameSize)
        val chunk = FloatArray(hopSize)
        var filled = 0

        while (running) {
            val read = try {
                rec.read(chunk, 0, hopSize, AudioRecord.READ_BLOCKING)
            } catch (e: Exception) {
                Log.w(TAG, "read failed: ${e.message}"); break
            }
            if (read <= 0) {
                if (read == AudioRecord.ERROR_INVALID_OPERATION || read == AudioRecord.ERROR_DEAD_OBJECT) break
                continue
            }

            System.arraycopy(ring, read, ring, 0, frameSize - read)
            System.arraycopy(chunk, 0, ring, frameSize - read, read)
            filled = minOf(frameSize, filled + read)
            if (filled < frameSize) continue

            val at = System.currentTimeMillis()
            val r = try { detector.detect(ring) } catch (e: Exception) { continue }
            val smooth = smoother.push(if (r.confidence >= 0.45) r.hz else null)
            lastSmoothHz = smooth
            val frame = Frame(r.hz, r.confidence, r.rms, at)
            for (fn in listeners) {
                try { fn(frame) } catch (e: Exception) { Log.w(TAG, "listener threw: ${e.message}") }
            }
        }
    }

    /** The smoothed value, for display. Raw frames go to the listeners. */
    fun smoothed(): Double? = lastSmoothHz

    fun stop() {
        running = false
        worker?.join(500)
        worker = null
        try { record?.stop() } catch (e: Exception) { /* already stopped */ }
        record?.release()
        record = null
        agc?.release(); ns?.release(); aec?.release()
        agc = null; ns = null; aec = null
        smoother.reset()
        lastSmoothHz = null
        _status.value = Status()
    }

    private companion object { const val TAG = "CelloAudio" }
}
