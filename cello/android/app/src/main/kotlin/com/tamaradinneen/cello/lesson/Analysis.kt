package com.tamaradinneen.cello.lesson

import com.tamaradinneen.cello.audio.Music
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * Note segmentation and grading. A port of cello/web/js/analysis.js, kept
 * behaviourally identical so both apps give the same advice.
 *
 * The principle: measure the symptom, then name the physical cause. On a cello
 * nearly every audible fault has one, and a beginner who is told which can fix
 * it, whereas one told only "out of tune" cannot.
 */

data class Frame(val hz: Double?, val confidence: Double, val rms: Double, val at: Long)

data class NoteEvent(
    val hz: Double,
    val frames: Int,
    val startAt: Long,
    val endAt: Long,
    val durationSec: Double,
    val wobbleCents: Double,
    val rmsMean: Double,
    val rmsCv: Double,
    val confidence: Double,
)

class NoteSegmenter(
    private val minConfidence: Double = 0.5,
    private val onsetFrames: Int = 2,
    private val offsetFrames: Int = 4,
    private val rmsFloor: Double = 0.006,
    private val jumpCents: Double = 150.0,
    private val minFrames: Int = 4,
    /**
     * Close a note that has run this long instead of waiting for it to stop.
     * Without it, a long steady bow produces no feedback at all, which is
     * backwards: a long steady bow is what the early lessons ask for.
     */
    private val maxNoteSec: Double = 0.0,
) {
    private var current: MutableList<Frame>? = null
    private var currentStart: Long = 0
    private var goodRun = 0
    private var badRun = 0
    private var awaitingGap = false

    fun reset() {
        current = null; goodRun = 0; badRun = 0; awaitingGap = false
    }

    fun push(f: Frame): NoteEvent? {
        val good = f.hz != null && f.confidence >= minConfidence && f.rms >= rmsFloor

        if (good) {
            badRun = 0
            goodRun++
            if (current == null && !awaitingGap && goodRun >= onsetFrames) {
                current = mutableListOf(); currentStart = f.at
            }
            val cur = current
            if (cur != null && maxNoteSec > 0) {
                val held = (f.at - currentStart) / 1000.0
                if (held >= maxNoteSec) {
                    cur.add(f)
                    val done = close(f.at)
                    awaitingGap = true
                    if (done != null) return done
                }
            }
            val cur2 = current
            if (cur2 != null) {
                val last = cur2.lastOrNull()
                if (last?.hz != null && f.hz != null && abs(Music.cents(f.hz, last.hz)) > jumpCents) {
                    val done = close(f.at)
                    current = mutableListOf(f); currentStart = f.at
                    if (done != null) return done
                } else {
                    cur2.add(f)
                }
            }
            return null
        }

        goodRun = 0
        badRun++
        if (badRun >= offsetFrames) awaitingGap = false
        if (current != null && badRun >= offsetFrames) return close(f.at)
        return null
    }

    fun flush(at: Long): NoteEvent? = if (current != null) close(at) else null

    private fun close(endAt: Long): NoteEvent? {
        val frames = current ?: return null
        current = null
        if (frames.size < minFrames) return null
        return summarise(frames, endAt)
    }
}

private fun median(xs: List<Double>): Double {
    if (xs.isEmpty()) return Double.NaN
    val s = xs.sorted()
    val m = s.size / 2
    return if (s.size % 2 == 1) s[m] else (s[m - 1] + s[m]) / 2
}

private fun stdev(xs: List<Double>): Double {
    if (xs.size < 2) return 0.0
    val mean = xs.average()
    return sqrt(xs.sumOf { (it - mean) * (it - mean) } / (xs.size - 1))
}

/**
 * Reduce a note to the numbers that matter, excluding the attack and release.
 * Every bowed note starts and ends unstable, and judging someone on the scrape
 * at the start of a stroke would be unfair and unhelpful.
 */
fun summarise(frames: List<Frame>, endAt: Long): NoteEvent {
    val n = frames.size
    val from = minOf((n * 0.25).toInt(), maxOf(0, n - 3))
    val to = maxOf(from + 1, Math.ceil(n * 0.9).toInt())
    val core = frames.subList(from, minOf(to, n))

    val hzs = core.mapNotNull { it.hz }
    val rmss = core.map { it.rms }
    val hzMedian = median(hzs)
    val centsFromOwn = hzs.map { Music.cents(it, hzMedian) }
    val rmsMean = rmss.average()
    val start = frames.first().at

    return NoteEvent(
        hz = hzMedian,
        frames = n,
        startAt = start,
        endAt = endAt,
        durationSec = maxOf(0.0, (endAt - start) / 1000.0),
        wobbleCents = stdev(centsFromOwn),
        rmsMean = rmsMean,
        rmsCv = if (rmsMean > 0) stdev(rmss) / rmsMean else 0.0,
        confidence = median(core.map { it.confidence }),
    )
}

data class Grade(
    val pass: Boolean,
    val issue: String,
    val detail: String,
    val centsOff: Double,
    val semitonesOff: Double,
    val direction: String,
)

object Grading {
    const val WOBBLE_CENTS = 22.0
    const val RMS_CV = 0.38
    const val DURATION_FRACTION = 0.7

    /**
     * Past this, it is a different note rather than an intonation slip. The two
     * need opposite advice: 25 cents flat means nudge the finger, 100 cents
     * flat means the wrong finger is down, or none at all.
     */
    const val WRONG_NOTE_CENTS = 70.0

    fun gradeNote(
        ev: NoteEvent,
        targetHz: Double,
        toleranceCents: Double = 35.0,
        holdSec: Double = 0.0,
        metrics: Set<String> = setOf("pitch", "duration"),
    ): Grade {
        val off = Music.cents(ev.hz, targetHz)
        val wrongNoteAt = maxOf(WRONG_NOTE_CENTS, toleranceCents * 1.6)
        val isWrongNote = metrics.contains("pitch") && abs(off) >= wrongNoteAt

        val failed = mutableSetOf<String>()
        if (metrics.contains("pitch") && abs(off) > toleranceCents) failed.add("pitch")
        if (metrics.contains("duration") && holdSec > 0 && ev.durationSec < holdSec * DURATION_FRACTION) failed.add("duration")
        if (metrics.contains("stability") && ev.wobbleCents > WOBBLE_CENTS) failed.add("stability")
        if (metrics.contains("tone") && ev.rmsCv > RMS_CV) failed.add("tone")

        val pass = failed.isEmpty()
        val issue = when {
            pass -> "good"
            failed.contains("pitch") -> if (isWrongNote) "wrongNote" else if (off < 0) "flat" else "sharp"
            failed.contains("duration") -> "short"
            failed.contains("stability") -> "unstable"
            failed.contains("tone") -> "uneven"
            else -> "good"
        }
        return Grade(
            pass = pass,
            issue = issue,
            detail = describe(off, ev, issue, isWrongNote),
            centsOff = off,
            semitonesOff = off / 100.0,
            direction = if (off < 0) "flat" else "sharp",
        )
    }

    /**
     * Say how far out in whatever unit is most informative: cents under a
     * semitone, semitones beyond, because semitones map onto fingers.
     */
    fun describeGap(absCents: Double): String {
        val semis = absCents / 100.0
        if (semis < 0.8) return "${absCents.roundToInt()} cents"
        val rounded = semis.roundToInt()
        val name = if (rounded == 1) "a semitone" else "$rounded semitones"
        if (abs(semis - rounded) <= 0.2) return name
        return "${absCents.roundToInt()} cents, about $name"
    }

    private fun describe(off: Double, ev: NoteEvent, issue: String, wrongNote: Boolean): String {
        val parts = mutableListOf<String>()
        val a = abs(off)
        val dir = if (off < 0) "flat" else "sharp"
        when {
            a < 4 -> parts.add("bang on the note")
            wrongNote -> parts.add("${describeGap(a)} $dir")
            else -> parts.add("${a.roundToInt()} cents $dir")
        }
        if (ev.durationSec > 0) parts.add("held %.1f s".format(ev.durationSec))
        if (issue == "unstable" || ev.wobbleCents > 15) parts.add("pitch moved by about ${ev.wobbleCents.roundToInt()} cents")
        if (issue == "uneven" || ev.rmsCv > 0.3) parts.add("volume varied by ${(ev.rmsCv * 100).roundToInt()}%")
        return parts.joinToString(", ") + "."
    }

    val GENERIC = mapOf(
        "silence" to "I did not hear a clear note. Check the bow has rosin, is tightened, and is touching the string between the fingerboard and the bridge.",
        "flat" to "That was below the note. For a stopped note, slide the finger very slightly towards the bridge. For an open string, check the tuning.",
        "sharp" to "That was above the note. For a stopped note, slide the finger very slightly back towards the scroll. For an open string, check the tuning.",
        "short" to "The note was too short to judge properly. Slow the bow down and use more of its length so the sound lasts.",
        "unstable" to "The pitch moved while the note was sounding. On a stopped note that is usually finger pressure easing off or the finger sliding. On an open string it is usually the bow drifting out of parallel with the bridge.",
        "uneven" to "The volume rose and fell during the note. That is the bow changing speed or pressure partway through. Aim for one single speed from one end of the stroke to the other.",
        "good" to "That one was good.",
        "wrongNote" to "That is a different note, not just a slightly out of tune one. Check you are on the right string, and that the right finger is down in the right place.",
    )

    /**
     * Prefer the lesson's own wording. For a wrong note we also try its flat or
     * sharp line, but only for a near miss: "nudge the finger" is the wrong
     * advice when the player is four notes away.
     */
    fun coachFor(coach: Map<String, String>?, issue: String, direction: String? = null, semitonesOff: Double? = null): String {
        if (coach != null) {
            coach[issue]?.let { return it }
            val near = semitonesOff == null || abs(semitonesOff) <= 1.6
            if (issue == "wrongNote" && near && direction != null) coach[direction]?.let { return it }
        }
        return GENERIC[issue] ?: GENERIC.getValue("good")
    }

    data class SeqItem(val index: Int, val centsOff: Double, val pass: Boolean, val wrongNote: Boolean)
    data class SeqResult(val results: List<SeqItem>, val missing: Int, val extra: Int, val correct: Int, val total: Int, val pass: Boolean)

    fun gradeSequence(events: List<NoteEvent>, expectedHz: List<Double>, toleranceCents: Double = 45.0): SeqResult {
        val results = mutableListOf<SeqItem>()
        val n = minOf(events.size, expectedHz.size)
        val wrongAt = maxOf(WRONG_NOTE_CENTS, toleranceCents * 1.6)
        for (i in 0 until n) {
            val off = Music.cents(events[i].hz, expectedHz[i])
            val wrong = abs(off) >= wrongAt
            results.add(SeqItem(i, off, !wrong && abs(off) <= toleranceCents, wrong))
        }
        val missing = maxOf(0, expectedHz.size - events.size)
        val correct = results.count { it.pass }
        return SeqResult(results, missing, maxOf(0, events.size - expectedHz.size), correct, expectedHz.size,
            missing == 0 && correct == expectedHz.size)
    }

    data class RhythmResult(val pass: Boolean, val issue: String, val meanMs: Double, val spreadMs: Double,
                            val played: Int, val expected: Int, val detail: String)

    fun gradeRhythm(onsets: List<Long>, startAt: Long, bpm: Int, beats: Int,
                    beatsPerNote: Int = 1, toleranceMs: Double = 180.0): RhythmResult {
        val period = (60000.0 / bpm) * beatsPerNote
        val expectedCount = maxOf(1, Math.round(beats.toDouble() / beatsPerNote).toInt())
        val errors = mutableListOf<Double>()
        for (i in 0 until minOf(onsets.size, expectedCount)) {
            errors.add(onsets[i] - (startAt + i * period))
        }
        if (errors.isEmpty()) {
            return RhythmResult(false, "silence", Double.NaN, Double.NaN, 0, expectedCount, "I did not hear any notes.")
        }
        val mean = errors.average()
        val spread = stdev(errors)
        val countOk = onsets.size >= expectedCount
        val pass = countOk && abs(mean) <= toleranceMs && spread <= toleranceMs
        val issue = when {
            pass -> "good"
            !countOk -> if (onsets.isEmpty()) "silence" else "missing"
            spread > toleranceMs -> "scattered"
            mean < 0 -> "early"
            else -> "late"
        }
        val detail = if (countOk)
            "${onsets.size} notes, on average ${abs(mean).roundToInt()} ms ${if (mean < 0) "ahead of" else "behind"} the click, spread ${spread.roundToInt()} ms."
        else "I heard ${onsets.size} of $expectedCount notes."
        return RhythmResult(pass, issue, mean, spread, onsets.size, expectedCount, detail)
    }

    val RHYTHM_COACH = mapOf(
        "silence" to "I did not hear any notes. Check the bow is making a sound, and that your device can hear the cello.",
        "missing" to "Some notes did not come through. Make sure every stroke actually sounds, and keep going for the full count.",
        "early" to "You are arriving ahead of the click. Let the click lead you rather than chasing it.",
        "late" to "You are landing behind the click. Start the bow moving a fraction earlier, so the sound arrives on the beat.",
        "scattered" to "The timing was uneven rather than consistently early or late. Count out loud, one, two, three, four, while you play.",
        "good" to "Steady and in time.",
    )
}
