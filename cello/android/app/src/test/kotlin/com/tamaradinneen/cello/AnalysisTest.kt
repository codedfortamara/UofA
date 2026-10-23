package com.tamaradinneen.cello

import com.tamaradinneen.cello.audio.Music
import com.tamaradinneen.cello.lesson.Frame
import com.tamaradinneen.cello.lesson.Grade
import com.tamaradinneen.cello.lesson.Grading
import com.tamaradinneen.cello.lesson.NoteEvent
import com.tamaradinneen.cello.lesson.NoteSegmenter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sin

/**
 * Segmentation and grading, fed synthetic frame streams that stand for
 * specific playing faults. The engine must reach the diagnosis a teacher
 * would, and must tell an intonation slip apart from the wrong finger.
 */
class AnalysisTest {

    private val hopMs = 1024.0 / 48000.0 * 1000.0   // 21.33 ms, as in the real pipeline
    private var clock = 0L

    private fun reset() { clock = 0L }

    private fun note(hz: Double, seconds: Double, rms: Double = 0.05,
                     wobbleCents: Double = 0.0, rmsCv: Double = 0.0): List<Frame> {
        val n = (seconds * 1000 / hopMs).toInt()
        return (0 until n).map { i ->
            val wob = if (wobbleCents != 0.0) wobbleCents * sin(i * 1.7) else 0.0
            val amp = rms * (1 + if (rmsCv != 0.0) rmsCv * sin(i * 0.9) else 0.0)
            Frame(hz * Math.pow(2.0, wob / 1200.0), 0.95, amp, clock).also { clock += hopMs.toLong() }
        }
    }

    private fun silence(seconds: Double): List<Frame> {
        val n = (seconds * 1000 / hopMs).toInt()
        return (0 until n).map { Frame(null, 0.0, 0.0005, clock).also { clock += hopMs.toLong() } }
    }

    private fun segment(frames: List<Frame>, maxNoteSec: Double = 0.0): List<NoteEvent> {
        val seg = NoteSegmenter(maxNoteSec = maxNoteSec)
        val out = mutableListOf<NoteEvent>()
        for (f in frames) seg.push(f)?.let { out.add(it) }
        seg.flush(clock)?.let { out.add(it) }
        return out
    }

    private val d3 = Music.noteToFreq("D3")

    @Test
    fun `one bowed note yields one event`() {
        reset()
        val events = segment(silence(0.3) + note(d3, 3.0) + silence(0.4))
        assertEquals(1, events.size)
        assertEquals(3.0, events[0].durationSec, 0.25)
        assertTrue(Math.abs(Music.cents(events[0].hz, d3)) < 1.0)
    }

    @Test
    fun `separated notes are counted separately`() {
        reset()
        val frames = silence(0.2) + note(d3, 1.5) + silence(0.3) +
            note(Music.noteToFreq("A3"), 1.5) + silence(0.3) + note(d3, 1.5) + silence(0.3)
        assertEquals(3, segment(frames).size)
    }

    @Test
    fun `slurred notes split on the pitch change`() {
        reset()
        val frames = silence(0.2) + note(d3, 1.2) + note(Music.noteToFreq("E3"), 1.2) +
            note(Music.noteToFreq("F#3"), 1.2) + silence(0.3)
        assertEquals(3, segment(frames).size)
    }

    @Test
    fun `a momentary scrape is not a note`() {
        reset()
        assertEquals(0, segment(silence(0.2) + note(d3, 0.05) + silence(0.3)).size)
    }

    @Test
    fun `a continuously held note is graded without having to stop`() {
        reset()
        val events = segment(silence(0.2) + note(d3, 12.0), maxNoteSec = 3.0)
        assertEquals(1, events.size)
        assertTrue("capped at ${events[0].durationSec}", events[0].durationSec in 2.8..3.3)
    }


    @Test
    fun `playing faults are diagnosed`() {
        val metrics = setOf("pitch", "duration", "stability", "tone")
        fun grade(hz: Double, seconds: Double, wobble: Double = 0.0, cv: Double = 0.0): Grade {
            reset()
            val ev = segment(silence(0.2) + note(hz, seconds, wobbleCents = wobble, rmsCv = cv) + silence(0.4))
            return Grading.gradeNote(ev.first(), d3, 35.0, 3.0, metrics)
        }

        assertTrue(grade(d3, 3.2).pass)
        assertEquals("flat", grade(d3 * Math.pow(2.0, -60 / 1200.0), 3.2).issue)
        assertEquals("sharp", grade(d3 * Math.pow(2.0, 55 / 1200.0), 3.2).issue)
        assertEquals("short", grade(d3, 1.0).issue)
        assertEquals("unstable", grade(d3, 3.2, wobble = 45.0).issue)
        assertEquals("uneven", grade(d3, 3.2, cv = 0.75).issue)
        assertTrue("20 cents inside a 35 cent tolerance should pass",
                   grade(d3 * Math.pow(2.0, 20 / 1200.0), 3.2).pass)
    }

    @Test
    fun `a wrong note is told apart from poor intonation`() {
        val metrics = setOf("pitch")
        fun grade(cents: Double): Grade {
            reset()
            val ev = segment(silence(0.2) + note(d3 * Math.pow(2.0, cents / 1200.0), 3.0) + silence(0.4))
            return Grading.gradeNote(ev.first(), d3, 35.0, 0.0, metrics)
        }
        assertEquals("flat", grade(-45.0).issue)
        assertEquals("wrongNote", grade(-100.0).issue)
        assertTrue(grade(-100.0).detail.contains("a semitone"))
        assertTrue(grade(200.0).detail.contains("2 semitones"))
        assertTrue(grade(470.0).detail.contains("about 5 semitones"))
    }

    @Test
    fun `coaching only borrows the lesson wording for a near miss`() {
        val coach = mapOf("sharp" to "Slide the finger very slightly back.")
        assertTrue(Grading.coachFor(coach, "wrongNote", "sharp", 0.9).contains("very slightly"))
        assertTrue(!Grading.coachFor(coach, "wrongNote", "sharp", 4.7).contains("very slightly"))
    }

    @Test
    fun `rhythm timing is diagnosed`() {
        val bpm = 60
        val beats = 8
        val period = 60000.0 / bpm
        val onTime = (0 until beats).map { (it * period).toLong() }

        assertTrue(Grading.gradeRhythm(onTime, 0L, bpm, beats).pass)
        assertEquals("early", Grading.gradeRhythm(onTime.map { it - 250 }, 0L, bpm, beats).issue)
        assertEquals("late", Grading.gradeRhythm(onTime.map { it + 300 }, 0L, bpm, beats).issue)
        assertEquals("scattered",
            Grading.gradeRhythm(onTime.mapIndexed { i, x -> x + if (i % 2 == 0) -380L else 420L }, 0L, bpm, beats).issue)
        assertEquals("missing", Grading.gradeRhythm(onTime.take(5), 0L, bpm, beats).issue)
        assertEquals("silence", Grading.gradeRhythm(emptyList(), 0L, bpm, beats).issue)

        // Ordinary human unevenness must still pass, or the app just nags.
        val human = listOf(20L, -35L, 60L, -20L, 45L, -50L, 15L, 30L)
        assertTrue(Grading.gradeRhythm(onTime.mapIndexed { i, x -> x + human[i] }, 0L, bpm, beats).pass)
    }

    @Test
    fun `a sequence is graded note by note`() {
        reset()
        val scale = listOf("D3", "E3", "F#3", "G3").map { Music.noteToFreq(it) }
        var frames = emptyList<Frame>()
        for (hz in scale) frames = frames + silence(0.25) + note(hz, 1.3)
        frames = frames + silence(0.3)
        val r = Grading.gradeSequence(segment(frames), scale, 40.0)
        assertTrue(r.pass)
        assertEquals(4, r.correct)
    }
}
