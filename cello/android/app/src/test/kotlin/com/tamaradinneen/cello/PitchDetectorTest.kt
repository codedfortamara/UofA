package com.tamaradinneen.cello

import com.tamaradinneen.cello.audio.Music
import com.tamaradinneen.cello.audio.PitchDetector
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.sin

/**
 * The same validation the web app gets, run against the Kotlin port, so the
 * two implementations are held to one standard. A tuner that is confidently
 * wrong is worse than no tuner, so every case here has a known true frequency
 * and the error is measured rather than eyeballed.
 */
class PitchDetectorTest {

    private val sr = 48000
    private val w = 2048

    // A realistic bowed spectrum, and the weak fundamental case that makes
    // naive autocorrelation report an octave too high.
    private val cello = doubleArrayOf(1.0, 0.70, 0.50, 0.35, 0.22, 0.15, 0.10)
    private val weakFundamental = doubleArrayOf(0.18, 1.0, 0.8, 0.5, 0.3, 0.2, 0.12)

    private fun synth(hz: Double, harmonics: DoubleArray, seconds: Double = 0.5,
                      noise: Double = 0.0, amp: Double = 0.25, seed: Long = 7): FloatArray {
        val n = (sr * seconds).toInt()
        val out = FloatArray(n)
        val rnd = java.util.Random(seed)
        var phase = 0.0
        val step = 2 * PI * hz / sr
        for (i in 0 until n) {
            phase += step
            var v = 0.0
            for ((k, a) in harmonics.withIndex()) v += a * sin(phase * (k + 1))
            if (noise > 0) v += noise * (rnd.nextDouble() * 2 - 1)
            out[i] = (v * amp).toFloat()
        }
        return out
    }

    private data class Measured(val detectRate: Double, val medianCents: Double, val worstCents: Double)

    private fun measure(signal: FloatArray, trueHz: Double): Measured {
        val det = PitchDetector(sr, w)
        val frame = FloatArray(w * 2)
        val errs = mutableListOf<Double>()
        var frames = 0
        var off = 1024
        while (off + w * 2 <= signal.size) {
            System.arraycopy(signal, off, frame, 0, w * 2)
            val r = det.detect(frame)
            frames++
            r.hz?.let { errs.add(Music.cents(it, trueHz)) }
            off += 1024
        }
        if (errs.isEmpty()) return Measured(0.0, Double.NaN, Double.NaN)
        val sorted = errs.sorted()
        return Measured(errs.size.toDouble() / frames, sorted[sorted.size / 2], errs.maxOf { abs(it) })
    }

    private fun check(label: String, m: Measured, maxMedian: Double, maxWorst: Double) {
        assertTrue("$label: detect rate ${m.detectRate}", m.detectRate >= 0.9)
        assertTrue("$label: median ${"%.3f".format(m.medianCents)}c", abs(m.medianCents) <= maxMedian)
        assertTrue("$label: worst ${"%.3f".format(m.worstCents)}c", m.worstCents <= maxWorst)
    }

    @Test
    fun `open strings are detected accurately`() {
        for (s in Music.STRINGS) {
            val hz = Music.noteToFreq(s.note)
            check("${s.note} cello spectrum", measure(synth(hz, cello), hz), 0.5, 2.5)
        }
    }

    @Test
    fun `a weak fundamental does not cause an octave error`() {
        for (s in Music.STRINGS) {
            val hz = Music.noteToFreq(s.note)
            check("${s.note} weak fundamental", measure(synth(hz, weakFundamental), hz), 0.5, 2.5)
        }
    }

    @Test
    fun `stopped notes used in the lessons are detected`() {
        for (n in listOf("E3", "F#3", "G3", "A3", "B3", "C#4", "D4", "A2", "D2")) {
            val hz = Music.noteToFreq(n)
            check(n, measure(synth(hz, cello), hz), 0.5, 2.5)
        }
    }

    @Test
    fun `detuned strings read the right number of cents`() {
        for (off in listOf(-250, -100, -50, -20, -5, 5, 20, 50, 100, 250)) {
            val hz = Music.noteToFreq("D3") * Math.pow(2.0, off / 1200.0)
            check("D3 offset $off", measure(synth(hz, cello), hz), 0.5, 2.5)
        }
    }

    @Test
    fun `noise and quiet playing are tolerated`() {
        val d3 = Music.noteToFreq("D3")
        check("10% noise", measure(synth(d3, cello, noise = 0.10), d3), 2.0, 10.0)
        check("30% noise", measure(synth(d3, cello, noise = 0.30), d3), 3.0, 20.0)
        check("quiet", measure(synth(d3, cello, amp = 0.02), d3), 2.0, 6.0)
        val c2 = Music.noteToFreq("C2")
        check("C2 noisy, worst case string", measure(synth(c2, weakFundamental, noise = 0.15), c2), 3.0, 15.0)
    }

    @Test
    fun `silence returns no pitch`() {
        val det = PitchDetector(sr, w)
        assertNull(det.detect(FloatArray(w * 2)).hz)
    }

    @Test
    fun `white noise rarely looks confident`() {
        val det = PitchDetector(sr, w)
        val buf = FloatArray(w * 2)
        val rnd = java.util.Random(11)
        var confident = 0
        repeat(20) {
            for (i in buf.indices) buf[i] = ((rnd.nextDouble() * 2 - 1) * 0.2).toFloat()
            val r = det.detect(buf)
            if (r.hz != null && r.confidence > 0.6) confident++
        }
        assertTrue("$confident of 20 noise frames looked confident", confident <= 2)
    }

    @Test
    fun `a frame costs far less than one hop`() {
        val det = PitchDetector(sr, w)
        val sig = synth(Music.noteToFreq("D3"), cello, seconds = 1.0)
        val frame = FloatArray(w * 2)
        System.arraycopy(sig, 0, frame, 0, w * 2)
        repeat(50) { det.detect(frame) }   // warm up the JIT
        val t0 = System.nanoTime()
        val iterations = 200
        repeat(iterations) { det.detect(frame) }
        val ms = (System.nanoTime() - t0) / 1e6 / iterations
        // The hop is 21.3 ms. Anything near that would drop frames on a phone.
        assertTrue("took %.2f ms per frame".format(ms), ms < 10.0)
        println("cost per frame: %.2f ms (hop is 21.3 ms)".format(ms))
    }

    @Test
    fun `string frequencies match standard pitch`() {
        assertEquals(65.406, Music.noteToFreq("C2"), 0.01)
        assertEquals(97.999, Music.noteToFreq("G2"), 0.01)
        assertEquals(146.832, Music.noteToFreq("D3"), 0.01)
        assertEquals(220.000, Music.noteToFreq("A3"), 0.01)
    }

    @Test
    fun `tuning advice picks the right device`() {
        assertEquals(Music.Device.NONE, Music.tuningAdvice(2.0).device)
        assertEquals(Music.Device.FINE_TUNER, Music.tuningAdvice(-12.0).device)
        assertEquals(Music.Device.FINE_TUNER, Music.tuningAdvice(90.0).device)
        assertEquals(Music.Device.PEG, Music.tuningAdvice(-200.0).device)
        assertTrue(Music.tuningAdvice(-12.0).detail.contains("clockwise"))
        assertTrue(Music.tuningAdvice(12.0).detail.contains("anticlockwise"))
    }
}
