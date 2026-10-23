package com.tamaradinneen.cello.audio

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Monophonic pitch detection for cello, using YIN with the difference function
 * computed through an FFT.
 *
 * This is a direct port of the JavaScript implementation in cello/web/js/pitch.js
 * and is kept behaviourally identical, so the two apps agree on what they hear
 * and one set of validation data covers both.
 *
 * Range is set for a cello: 55 Hz sits below a badly flat C string (65.4 Hz),
 * and 1320 Hz is well above anything reachable in first position.
 */
class PitchDetector(
    private val sampleRate: Int,
    private val windowSize: Int = 2048,
    private val config: Config = Config(),
) {
    data class Config(
        val minHz: Double = 55.0,
        val maxHz: Double = 1320.0,
        val threshold: Double = 0.12,
        val rmsGate: Double = 0.0035,
        val octaveGuard: Double = 0.80,
        val maxPeriods: Int = 16,
        val lowpassHz: Double = 1200.0,
        val highpassHz: Double = 35.0,
    )

    data class Result(val hz: Double?, val confidence: Double, val rms: Double, val reason: String)

    private val bufLen = windowSize * 2
    private val tauMax = windowSize
    private val fftSize = nextPow2(bufLen * 2)
    private val fft = Fft(fftSize)

    private val re1 = DoubleArray(fftSize)
    private val im1 = DoubleArray(fftSize)
    private val re2 = DoubleArray(fftSize)
    private val im2 = DoubleArray(fftSize)
    private val filtered = DoubleArray(bufLen)
    private val cumSq = DoubleArray(bufLen + 1)
    private val diff = DoubleArray(tauMax + 2)
    private val cmnd = DoubleArray(tauMax + 2)

    private val tauFloor = maxOf(2, floor(sampleRate / config.maxHz).toInt())
    private val tauCeil = minOf(tauMax - 2, ceil(sampleRate / config.minHz).toInt())

    // One pole high pass for DC and rumble, two pole Butterworth low pass to
    // take the edge off the upper harmonics before detection.
    private val hpA = Math.exp(-2.0 * PI * config.highpassHz / sampleRate)
    private var hpZ = 0.0
    private var hpPrev = 0.0

    private val lpB0: Double
    private val lpB1: Double
    private val lpB2: Double
    private val lpA1: Double
    private val lpA2: Double
    private var x1 = 0.0
    private var x2 = 0.0
    private var y1 = 0.0
    private var y2 = 0.0

    init {
        val w0 = 2.0 * PI * config.lowpassHz / sampleRate
        val cosw = cos(w0)
        val alpha = sin(w0) / (2.0 * (1.0 / sqrt(2.0)))
        val b0 = (1 - cosw) / 2; val b1 = 1 - cosw; val b2 = (1 - cosw) / 2
        val a0 = 1 + alpha; val a1 = -2 * cosw; val a2 = 1 - alpha
        lpB0 = b0 / a0; lpB1 = b1 / a0; lpB2 = b2 / a0; lpA1 = a1 / a0; lpA2 = a2 / a0
    }

    fun reset() {
        hpZ = 0.0; hpPrev = 0.0
        x1 = 0.0; x2 = 0.0; y1 = 0.0; y2 = 0.0
    }

    /** @param samples exactly 2*windowSize samples, normalised to roughly -1..1. */
    fun detect(samples: FloatArray): Result {
        require(samples.size >= bufLen) { "need $bufLen samples, got ${samples.size}" }

        var sumSq = 0.0
        for (i in 0 until bufLen) { val v = samples[i].toDouble(); sumSq += v * v }
        val rms = sqrt(sumSq / bufLen)
        if (rms < config.rmsGate) return Result(null, 0.0, rms, "quiet")

        for (i in 0 until bufLen) {
            val raw = samples[i].toDouble()
            hpZ = raw - hpPrev + hpA * hpZ
            hpPrev = raw
            val x0 = hpZ
            val y0 = lpB0 * x0 + lpB1 * x1 + lpB2 * x2 - lpA1 * y1 - lpA2 * y2
            x2 = x1; x1 = x0; y2 = y1; y1 = y0
            filtered[i] = y0
        }

        cumSq[0] = 0.0
        for (i in 0 until bufLen) cumSq[i + 1] = cumSq[i] + filtered[i] * filtered[i]

        java.util.Arrays.fill(re1, 0.0); java.util.Arrays.fill(im1, 0.0)
        java.util.Arrays.fill(re2, 0.0); java.util.Arrays.fill(im2, 0.0)
        for (i in 0 until windowSize) re1[i] = filtered[i]
        for (i in 0 until bufLen) re2[i] = filtered[i]
        fft.transform(re1, im1, false)
        fft.transform(re2, im2, false)
        for (i in 0 until fftSize) {
            val ar = re1[i]; val ai = -im1[i]
            val br = re2[i]; val bi = im2[i]
            re1[i] = ar * br - ai * bi
            im1[i] = ar * bi + ai * br
        }
        fft.transform(re1, im1, true)

        val p1 = cumSq[windowSize]
        for (tau in 0..tauMax) {
            val p2 = cumSq[tau + windowSize] - cumSq[tau]
            val v = p1 + p2 - 2 * re1[tau]
            diff[tau] = if (v > 0) v else 0.0
        }

        cmnd[0] = 1.0
        var running = 0.0
        for (tau in 1..tauMax) {
            running += diff[tau]
            cmnd[tau] = if (running > 0) diff[tau] * tau / running else 1.0
        }

        var tau = -1
        var t = tauFloor
        while (t <= tauCeil) {
            if (cmnd[t] < config.threshold) {
                while (t + 1 <= tauCeil && cmnd[t + 1] < cmnd[t]) t++
                tau = t
                break
            }
            t++
        }
        var periodic = true
        if (tau < 0) {
            periodic = false
            var bestT = tauFloor
            var bestV = Double.MAX_VALUE
            for (k in tauFloor..tauCeil) if (cmnd[k] < bestV) { bestV = cmnd[k]; bestT = k }
            tau = bestT
        }

        // Octave guard: a dip noticeably deeper at twice the lag means we locked
        // onto a harmonic and the real fundamental is an octave down.
        val twice = tau * 2
        if (twice <= tauCeil && cmnd[twice] < cmnd[tau] * config.octaveGuard) {
            var k = twice
            while (k + 1 <= tauCeil && cmnd[k + 1] < cmnd[k]) k++
            tau = k
        }

        // Multi-period refinement. Interpolating one period leaves a sub-sample
        // residual worth 8 cents at 220 Hz; measuring across k periods divides
        // that by k.
        val refineMax = tauMax - 2
        var k = refineMax / tau
        if (k > config.maxPeriods) k = config.maxPeriods
        if (k < 1) k = 1

        var refined = interpolate(diff, tau, tauMax)
        if (k > 1) {
            val centre = tau * k
            val span = maxOf(2, (tau * 0.25).toInt())
            val lo = maxOf(1, centre - span)
            val hi = minOf(refineMax, centre + span)
            var bestT = centre
            var bestV = Double.MAX_VALUE
            for (i in lo..hi) if (diff[i] < bestV) { bestV = diff[i]; bestT = i }
            val refinedK = interpolate(diff, bestT, tauMax)
            if (abs(refinedK / k - tau) <= tau * 0.1) refined = refinedK / k
        }

        val hz = sampleRate / refined
        if (hz < config.minHz || hz > config.maxHz) return Result(null, 0.0, rms, "out-of-range")
        val confidence = (1.0 - cmnd[tau]).coerceIn(0.0, 1.0)
        return Result(hz, if (periodic) confidence else confidence * 0.5, rms, if (periodic) "ok" else "weak")
    }

    private fun interpolate(d: DoubleArray, t: Int, limit: Int): Double {
        if (t <= 0 || t >= limit) return t.toDouble()
        val s0 = d[t - 1]; val s1 = d[t]; val s2 = d[t + 1]
        val denom = s0 - 2 * s1 + s2
        if (denom == 0.0) return t.toDouble()
        val shift = (s0 - s2) / (2 * denom)
        return if (shift > -1 && shift < 1) t + shift else t.toDouble()
    }

    private fun nextPow2(x: Int): Int { var n = 1; while (n < x) n = n shl 1; return n }

    /** In place iterative radix-2 complex FFT with precomputed twiddles. */
    private class Fft(val n: Int) {
        private val cosT = DoubleArray(n / 2)
        private val sinT = DoubleArray(n / 2)
        private val rev = IntArray(n)

        init {
            for (i in 0 until n / 2) {
                cosT[i] = cos(-2.0 * PI * i / n)
                sinT[i] = sin(-2.0 * PI * i / n)
            }
            var j = 0
            for (i in 1 until n) {
                var bit = n shr 1
                while (j and bit != 0) { j = j xor bit; bit = bit shr 1 }
                j = j or bit
                rev[i] = j
            }
        }

        fun transform(re: DoubleArray, im: DoubleArray, inverse: Boolean) {
            for (i in 1 until n) {
                val j = rev[i]
                if (i < j) {
                    var t = re[i]; re[i] = re[j]; re[j] = t
                    t = im[i]; im[i] = im[j]; im[j] = t
                }
            }
            var len = 2
            while (len <= n) {
                val half = len shr 1
                val stride = n / len
                var i = 0
                while (i < n) {
                    for (q in 0 until half) {
                        val tw = q * stride
                        val wr = cosT[tw]
                        val wi = if (inverse) -sinT[tw] else sinT[tw]
                        val a = i + q
                        val b = a + half
                        val vr = re[b] * wr - im[b] * wi
                        val vi = re[b] * wi + im[b] * wr
                        re[b] = re[a] - vr
                        im[b] = im[a] - vi
                        re[a] += vr
                        im[a] += vi
                    }
                    i += len
                }
                len = len shl 1
            }
            if (inverse) for (i in 0 until n) { re[i] /= n; im[i] /= n }
        }
    }
}

/**
 * Display smoothing: a median rejects single frame glitches outright, and a
 * jump has to persist before it is believed, so the needle neither twitches
 * nor lags.
 */
class PitchSmoother(
    private val size: Int = 5,
    private val jumpCents: Double = 120.0,
    private val jumpFrames: Int = 3,
) {
    private val history = ArrayDeque<Double>()
    private val pending = mutableListOf<Double>()

    fun reset() { history.clear(); pending.clear() }

    fun push(hz: Double?): Double? {
        if (hz == null) { history.clear(); pending.clear(); return null }
        val current = value()
        if (current != null) {
            val jump = abs(Music.cents(hz, current))
            if (jump > jumpCents) {
                pending.add(hz)
                if (pending.size >= jumpFrames) {
                    history.clear()
                    pending.forEach { history.addLast(it) }
                    pending.clear()
                }
                return current
            }
        }
        pending.clear()
        history.addLast(hz)
        while (history.size > size) history.removeFirst()
        return value()
    }

    fun value(): Double? {
        if (history.isEmpty()) return null
        val s = history.sorted()
        return s[s.size / 2]
    }
}
