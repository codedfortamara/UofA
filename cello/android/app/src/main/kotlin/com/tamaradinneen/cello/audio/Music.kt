package com.tamaradinneen.cello.audio

import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.roundToInt

/** Note and pitch mathematics, and the cello string table. */
object Music {
    const val A4_DEFAULT = 440.0

    private val SEMITONES = mapOf('C' to 0, 'D' to 2, 'E' to 4, 'F' to 5, 'G' to 7, 'A' to 9, 'B' to 11)
    private val NAMES = arrayOf("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    private val SPOKEN = mapOf("C#" to "C sharp", "D#" to "D sharp", "F#" to "F sharp", "G#" to "G sharp", "A#" to "A sharp")

    private val NOTE_RE = Regex("^([A-Ga-g])([#b]?)(-?\\d+)$")

    fun noteToMidi(name: String): Int {
        val m = NOTE_RE.find(name.trim()) ?: throw IllegalArgumentException("not a note name: $name")
        val letter = m.groupValues[1].uppercase()[0]
        val acc = when (m.groupValues[2]) { "#" -> 1; "b" -> -1; else -> 0 }
        val octave = m.groupValues[3].toInt()
        return (octave + 1) * 12 + SEMITONES.getValue(letter) + acc
    }

    fun midiToFreq(midi: Double, a4: Double = A4_DEFAULT): Double = a4 * 2.0.pow((midi - 69.0) / 12.0)

    fun noteToFreq(name: String, a4: Double = A4_DEFAULT): Double = midiToFreq(noteToMidi(name).toDouble(), a4)

    fun midiToName(midi: Int): String = NAMES[((midi % 12) + 12) % 12] + (Math.floorDiv(midi, 12) - 1)

    fun cents(f: Double, ref: Double): Double = 1200.0 * (ln(f / ref) / ln(2.0))

    data class Nearest(val midi: Int, val name: String, val cents: Double)

    fun nearestNote(freq: Double, a4: Double = A4_DEFAULT): Nearest? {
        if (freq <= 0) return null
        val exact = 69.0 + 12.0 * (ln(freq / a4) / ln(2.0))
        val midi = exact.roundToInt()
        return Nearest(midi, midiToName(midi), (exact - midi) * 100.0)
    }

    /** Strip the octave and expand an accidental, so "F#3" reads as "F sharp". */
    fun spokenNote(name: String): String {
        val m = Regex("^([A-Ga-g][#b]?)(-?\\d+)?$").find(name.trim()) ?: return name
        val head = m.groupValues[1].replaceFirstChar { it.uppercase() }
        return SPOKEN[head] ?: head
    }

    data class CelloString(val id: String, val note: String, val label: String, val hint: String)

    /** Identical on a 1/8 size cello: fractional instruments tune to standard pitch. */
    val STRINGS = listOf(
        CelloString("C", "C2", "C string", "Thickest, nearest your left knee."),
        CelloString("G", "G2", "G string", "Second from the left."),
        CelloString("D", "D3", "D string", "Third from the left."),
        CelloString("A", "A3", "A string", "Thinnest, nearest your right knee."),
    )

    fun stringById(id: String): CelloString? = STRINGS.firstOrNull { it.id == id }

    fun stringFreq(id: String, a4: Double = A4_DEFAULT): Double =
        stringById(id)?.let { noteToFreq(it.note, a4) } ?: Double.NaN

    data class NearestString(val string: CelloString, val cents: Double, val target: Double)

    fun nearestString(freq: Double, a4: Double = A4_DEFAULT): NearestString? {
        if (freq <= 0) return null
        var best: NearestString? = null
        for (s in STRINGS) {
            val target = noteToFreq(s.note, a4)
            val dev = cents(freq, target)
            if (best == null || abs(dev) < abs(best.cents)) best = NearestString(s, dev, target)
        }
        return best
    }

    enum class Device { NONE, FINE_TUNER, PEG }

    data class Advice(val state: String, val device: Device, val headline: String, val detail: String)

    /**
     * Turn a cents deviation into something a beginner can act on. The split
     * matters: fine tuners are safe and have limited travel, pegs move a long
     * way for very little turn and are where strings get broken.
     */
    fun tuningAdvice(centsOff: Double): Advice {
        val a = abs(centsOff)
        val sharp = centsOff > 0
        if (a <= 5) return Advice("in-tune", Device.NONE, "In tune", "Leave this string alone and move to the next one.")
        val direction = if (sharp) "lower" else "raise"
        val fineTurn = if (sharp) "anticlockwise" else "clockwise"
        return when {
            a <= 35 -> Advice(
                if (sharp) "sharp" else "flat", Device.FINE_TUNER,
                if (sharp) "Slightly sharp" else "Slightly flat",
                "Use the fine tuner at the tailpiece. Turn it $fineTurn by about a quarter turn to $direction the pitch, then check again."
            )
            a <= 120 -> Advice(
                if (sharp) "sharp" else "flat", Device.FINE_TUNER,
                if (sharp) "Sharp" else "Flat",
                "Use the fine tuner, turning $fineTurn to $direction the pitch. If it runs out of travel before you reach the note, move to the peg."
            )
            else -> Advice(
                if (sharp) "very-sharp" else "very-flat", Device.PEG,
                if (sharp) "Far too sharp" else "Far too flat",
                if (sharp) "This needs the peg. Turn it very slightly to let the string down, then bring it back up onto the note from below."
                else "This needs the peg. Push the peg gently into its hole as you turn, and go in tiny amounts while watching the number."
            )
        }
    }
}
