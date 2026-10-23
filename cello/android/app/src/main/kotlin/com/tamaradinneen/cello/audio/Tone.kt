package com.tamaradinneen.cello.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.concurrent.thread
import kotlin.math.PI
import kotlin.math.sin

private const val SR = 44100

private fun newTrack(bufBytes: Int, mode: Int): AudioTrack =
    AudioTrack.Builder()
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build()
        )
        .setAudioFormat(
            AudioFormat.Builder()
                .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                .setSampleRate(SR)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .build()
        )
        .setBufferSizeInBytes(bufBytes)
        .setTransferMode(mode)
        .build()

/** A held reference note, for playing a scale against. */
class Drone {
    private var track: AudioTrack? = null
    @Volatile private var running = false
    var playing: Boolean = false
        private set

    // Additive, with the upper partials slightly detuned so it sounds closer
    // to a bowed string than to a synthesiser.
    private val partials = doubleArrayOf(1.0, 0.62, 0.45, 0.28, 0.18, 0.11, 0.07)

    fun start(hz: Double, gain: Float = 0.18f) {
        stop()
        val period = SR
        val buf = FloatArray(period)
        val norm = partials.sum()
        for (i in 0 until period) {
            var v = 0.0
            for ((k, amp) in partials.withIndex()) {
                val detune = if (k > 1) (if (k % 2 == 1) 1.0008 else 0.9992) else 1.0
                v += amp * sin(2.0 * PI * hz * detune * (k + 1) * i / SR)
            }
            buf[i] = (v / norm).toFloat() * gain
        }
        val t = newTrack(maxOf(AudioTrack.getMinBufferSize(SR, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_FLOAT), period * 4),
                         AudioTrack.MODE_STREAM)
        track = t
        running = true
        playing = true
        t.play()
        thread(name = "cello-drone") {
            // A short fade in, so starting the drone is not a click.
            val fade = FloatArray(buf.size)
            val fadeLen = SR / 6
            for (i in buf.indices) fade[i] = buf[i] * (if (i < fadeLen) i.toFloat() / fadeLen else 1f)
            var first = true
            while (running) {
                val b = if (first) fade else buf
                first = false
                var off = 0
                while (off < b.size && running) {
                    val n = t.write(b, off, b.size - off, AudioTrack.WRITE_BLOCKING)
                    if (n <= 0) break
                    off += n
                }
            }
        }
    }

    fun stop() {
        running = false
        playing = false
        try { track?.pause(); track?.flush(); track?.stop() } catch (e: Exception) { /* already stopped */ }
        track?.release()
        track = null
    }
}

/** A single short reference pitch: "this is the note you are aiming for". */
object Reference {
    fun play(hz: Double, seconds: Double = 2.0, gain: Float = 0.22f) {
        val n = (SR * seconds).toInt()
        val buf = FloatArray(n)
        val partials = doubleArrayOf(1.0, 0.6, 0.4, 0.25, 0.15)
        val norm = partials.sum()
        val fade = (SR * 0.04).toInt()
        for (i in 0 until n) {
            var v = 0.0
            for ((k, amp) in partials.withIndex()) v += amp * sin(2.0 * PI * hz * (k + 1) * i / SR)
            var a = (v / norm).toFloat() * gain
            if (i < fade) a *= i.toFloat() / fade
            if (i > n - fade) a *= (n - i).toFloat() / fade
            buf[i] = a
        }
        val t = newTrack(n * 4, AudioTrack.MODE_STATIC)
        t.write(buf, 0, n, AudioTrack.WRITE_BLOCKING)
        t.setNotificationMarkerPosition(n - 1)
        t.setPlaybackPositionUpdateListener(object : AudioTrack.OnPlaybackPositionUpdateListener {
            override fun onMarkerReached(track: AudioTrack?) { try { track?.release() } catch (e: Exception) { /* gone */ } }
            override fun onPeriodicNotification(track: AudioTrack?) {}
        })
        t.play()
    }
}

/**
 * A metronome whose click timing is known to the sample, because rhythm
 * grading compares note onsets against it.
 *
 * The whole exercise is rendered into one buffer up front, so the clicks are
 * exactly a period apart by construction rather than by timer accuracy. The
 * grid is then anchored to wall clock using the playback head position, which
 * accounts for output latency.
 *
 * The click sits at 2.6 kHz, above the detector's 1320 Hz ceiling and inside
 * the roll off of its 1200 Hz low pass, and lasts 12 ms, far shorter than the
 * four consecutive frames the segmenter needs before it calls something a
 * note. So the app hearing its own click cannot be mistaken for the cello.
 */
class Metronome {
    private var track: AudioTrack? = null
    @Volatile var running = false
        private set

    /** Wall clock time of the first beat after the count in, once known. */
    @Volatile var gridStartMs: Long = 0L
        private set

    private var periodSamples = 0
    private var countInBeats = 0

    fun start(bpm: Int, beats: Int, countIn: Int = 4, onBeat: ((Int, Boolean) -> Unit)? = null) {
        stop()
        periodSamples = (SR * 60.0 / bpm).toInt()
        countInBeats = countIn
        val total = countIn + beats + 1
        val n = periodSamples * total
        val buf = FloatArray(n)

        for (b in 0 until total) {
            val at = b * periodSamples
            val isCountIn = b < countIn
            val freq = if (isCountIn) 1800.0 else if ((b - countIn) % 4 == 0) 3000.0 else 2600.0
            val peak = if (isCountIn) 0.3f else if ((b - countIn) % 4 == 0) 0.38f else 0.26f
            val len = (SR * 0.012).toInt()
            for (i in 0 until len) {
                if (at + i >= n) break
                val env = (1.0 - i.toDouble() / len).let { it * it }
                buf[at + i] = (sin(2.0 * PI * freq * i / SR) * env).toFloat() * peak
            }
        }

        val t = newTrack(n * 4, AudioTrack.MODE_STATIC)
        t.write(buf, 0, n, AudioTrack.WRITE_BLOCKING)
        track = t
        running = true
        t.play()

        thread(name = "cello-metro") {
            var announced = -1
            while (running) {
                val head = try { t.playbackHeadPosition } catch (e: Exception) { break }
                if (head >= n - periodSamples / 2) break
                val beat = head / periodSamples
                if (beat == countIn && gridStartMs == 0L) {
                    // Anchor the grid: this many samples into the buffer, now.
                    gridStartMs = System.currentTimeMillis() - ((head - countIn * periodSamples) * 1000L / SR)
                }
                if (beat != announced) {
                    announced = beat
                    onBeat?.invoke(beat, beat < countIn)
                }
                Thread.sleep(8)
            }
            running = false
        }
    }

    fun stop() {
        running = false
        gridStartMs = 0L
        try { track?.pause(); track?.flush(); track?.stop() } catch (e: Exception) { /* already stopped */ }
        track?.release()
        track = null
    }
}
