package com.tamaradinneen.cello.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.Canvas
import com.tamaradinneen.cello.audio.AudioEngine
import com.tamaradinneen.cello.audio.Music
import com.tamaradinneen.cello.audio.Reference
import com.tamaradinneen.cello.lesson.Frame
import kotlin.math.abs
import kotlin.math.roundToInt

private const val METER_RANGE = 50.0   // cents at the edge of the dial
private const val IN_TUNE = 5.0
private const val CLOSE = 15.0
private const val STRAY_CENTS = 250.0  // beyond this from any open string, it is not one
private const val HOLD_FRAMES = 12     // frames in tune before a string counts as done

data class TunerReading(
    val playedName: String = "",
    val playedOctave: String = "",
    val centsOff: Double = 0.0,
    val hz: Double = 0.0,
    val targetHz: Double = 0.0,
    val targetId: String = "",
    val strayed: Boolean = false,
    val live: Boolean = false,
    val level: Float = 0f,
)

/**
 * Shared tuner state. Held outside the composable so the guided flow inside a
 * lesson and the standalone tuner tab behave identically.
 */
class TunerState(
    private val engine: AudioEngine,
    private val a4: () -> Double,
    var order: List<String> = listOf("A", "D", "G", "C"),
    private val onStringDone: (String) -> kotlin.Unit = {},
    private val onAllDone: () -> kotlin.Unit = {},
) {
    var mode by mutableStateOf("auto")       // "auto" or a string id
    var reading by mutableStateOf(TunerReading())
    var done by mutableStateOf(setOf<String>())
    private var inTuneRun = 0
    private var lastLive = 0L

    fun selectNext() {
        order.firstOrNull { it !in done }?.let { mode = it }
    }

    fun restart() { done = emptySet(); mode = "auto"; inTuneRun = 0 }

    fun onFrame(f: Frame) {
        val level = (f.rms / 0.08).coerceIn(0.0, 1.0).toFloat()
        val hz = engine.smoothed()
        if (hz == null || f.confidence < 0.45) {
            if (System.currentTimeMillis() - lastLive > 450) {
                reading = reading.copy(live = false, level = level)
                inTuneRun = 0
            }
            return
        }
        lastLive = System.currentTimeMillis()
        val ref = a4()

        val targetId: String
        val targetHz: Double
        val off: Double
        var strayed = false
        if (mode == "auto") {
            val near = Music.nearestString(hz, ref) ?: return
            targetId = near.string.id
            targetHz = near.target
            off = near.cents
            strayed = abs(near.cents) > STRAY_CENTS
        } else {
            targetId = mode
            targetHz = Music.stringFreq(targetId, ref)
            off = Music.cents(hz, targetHz)
        }

        val played = Music.nearestNote(hz, ref)
        val m = Regex("^([A-G]#?)(-?\\d+)$").find(played?.name ?: "")
        reading = TunerReading(
            playedName = m?.groupValues?.get(1) ?: (played?.name ?: ""),
            playedOctave = m?.groupValues?.get(2) ?: "",
            centsOff = off,
            hz = hz,
            targetHz = targetHz,
            targetId = targetId,
            strayed = strayed,
            live = true,
            level = level,
        )

        if (!strayed && abs(off) <= IN_TUNE) {
            inTuneRun++
            if (inTuneRun == HOLD_FRAMES && targetId !in done) {
                done = done + targetId
                onStringDone(targetId)
                if (order.all { it in done }) onAllDone()
                if (mode != "auto") selectNext()
            }
        } else {
            inTuneRun = 0
        }
    }
}

@Composable
fun TunerPanel(state: TunerState, a4: Double, showHelp: Boolean = true) {
    val r = state.reading

    Stage {
        CapsLabel(
            when {
                !r.live -> "Listening"
                r.strayed -> "Not an open string"
                state.mode == "auto" -> "Nearest: ${r.targetId} string"
                else -> "Tuning the ${state.mode} string"
            },
            Brand.Gold,
        )
        Spacer(Modifier.height(4.dp))

        CentreRow {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(
                    if (r.live) r.playedName.ifEmpty { "–" } else "–",
                    fontSize = 58.sp, fontWeight = FontWeight.SemiBold,
                    color = if (r.live) Brand.Ivory else Brand.Ivory.copy(alpha = 0.32f),
                )
                if (r.live && r.playedOctave.isNotEmpty()) {
                    Text(
                        r.playedOctave, fontSize = 20.sp, color = Brand.Gold,
                        modifier = Modifier.padding(start = 4.dp, bottom = 10.dp),
                    )
                }
            }
        }

        CentreRow {
            Text(
                when {
                    !r.live || r.strayed -> ""
                    abs(r.centsOff) < 1 -> "spot on"
                    else -> "${if (r.centsOff > 0) "+" else "−"}${abs(r.centsOff).roundToInt()} cents"
                },
                fontSize = 17.sp, color = Brand.Gold,
            )
        }

        CentsDial(centsOff = if (r.live && !r.strayed) r.centsOff else 0.0, live = r.live && !r.strayed)

        CentreRow {
            val abs = abs(r.centsOff)
            val (label, colour) = when {
                !r.live -> "Play a string" to Brand.Ivory.copy(alpha = 0.6f)
                r.strayed -> "That is ${Music.spokenNote(r.playedName)}" to Brand.Ivory.copy(alpha = 0.85f)
                abs <= IN_TUNE -> "In tune" to Brand.GoodBright
                abs > METER_RANGE -> (if (r.centsOff < 0) "Far too flat" else "Far too sharp") to Brand.OffBright
                abs <= CLOSE -> (if (r.centsOff < 0) "Flat" else "Sharp") to Brand.WarnBright
                else -> (if (r.centsOff < 0) "Flat" else "Sharp") to Brand.OffBright
            }
            Text(label.uppercase(), style = Caps, color = colour, fontSize = 13.sp)
        }

        CentreRow(Modifier.padding(top = 3.dp)) {
            Text(
                if (!r.live) "" else if (r.strayed) "%.1f Hz".format(r.hz)
                else "%.1f Hz, target %.1f Hz".format(r.hz, r.targetHz),
                fontSize = 12.sp, color = Brand.Ivory.copy(alpha = 0.55f),
            )
        }

        // Signal level, so it is obvious whether the app can hear anything.
        Box(
            Modifier
                .padding(top = 10.dp)
                .fillMaxWidth()
                .height(3.dp)
                .background(Brand.Ivory.copy(alpha = 0.15f))
        ) {
            Box(
                Modifier
                    .fillMaxWidth(r.level)
                    .height(3.dp)
                    .background(Brand.Gold)
            )
        }
    }

    Spacer(Modifier.height(10.dp))
    StringPicker(state)
    Spacer(Modifier.height(10.dp))
    AdviceCard(state, r)

    Spacer(Modifier.height(10.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = {
                val id = if (state.mode == "auto") state.order.firstOrNull { it !in state.done } ?: "A" else state.mode
                Reference.play(Music.stringFreq(id, a4), 2.2)
            },
            modifier = Modifier.weight(1f),
            shape = RoundedCornerShape(2.dp),
        ) { Text("Hear the note", fontSize = 13.sp) }
        OutlinedButton(
            onClick = { state.restart() },
            modifier = Modifier.weight(1f),
            shape = RoundedCornerShape(2.dp),
        ) { Text("Start again", fontSize = 13.sp) }
    }

    if (showHelp) {
        Spacer(Modifier.height(12.dp))
        SectionCard {
            Text("If a string will not come up to pitch", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            Spacer(Modifier.height(6.dp))
            for (line in listOf(
                "Use the fine tuner at the tailpiece for anything small. Clockwise raises the pitch.",
                "Pegs move a long way for very little turn. Push the peg gently inward as you turn it, or it will slip straight back.",
                "Always finish by coming up onto the note from below. A string tuned downward onto the note will drift flat again.",
                "Tune round all four strings twice. Each string changes the tension on the others.",
            )) {
                Row(Modifier.padding(vertical = 3.dp)) {
                    Text("· ", color = Brand.GoldDeep)
                    Body(line)
                }
            }
        }
    }
}

@Composable
private fun CentsDial(centsOff: Double, live: Boolean) {
    val clamped = centsOff.coerceIn(-METER_RANGE, METER_RANGE)
    val target = (clamped / METER_RANGE * 70.0).toFloat()
    val angle by animateFloatAsState(targetValue = if (live) target else 0f, animationSpec = tween(90), label = "needle")

    val a = abs(centsOff)
    val needleColour = when {
        !live -> Brand.Ivory.copy(alpha = 0.4f)
        a <= IN_TUNE -> Brand.GoodBright
        a <= CLOSE -> Brand.WarnBright
        else -> Brand.OffBright
    }

    Canvas(
        Modifier
            .fillMaxWidth()
            .height(124.dp)
            .padding(top = 6.dp)
    ) {
        val cx = size.width / 2f
        val cy = size.height - 6f
        val radius = minOf(cx * 0.82f, size.height - 22f)
        val sweep = 140f          // plus and minus 70 degrees
        val startAngle = 180f + (180f - sweep) / 2f

        fun arc(colour: Color, fromCents: Double, toCents: Double, stroke: Float) {
            val from = (fromCents / METER_RANGE * 70.0).toFloat()
            val to = (toCents / METER_RANGE * 70.0).toFloat()
            drawArc(
                color = colour,
                startAngle = 270f + from,
                sweepAngle = to - from,
                useCenter = false,
                topLeft = Offset(cx - radius, cy - radius),
                size = Size(radius * 2, radius * 2),
                style = Stroke(width = stroke, cap = StrokeCap.Butt),
            )
        }

        // Track, then the close band, then the in tune cap on top.
        drawArc(
            color = Brand.Ivory.copy(alpha = 0.18f),
            startAngle = startAngle,
            sweepAngle = sweep,
            useCenter = false,
            topLeft = Offset(cx - radius, cy - radius),
            size = Size(radius * 2, radius * 2),
            style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round),
        )
        arc(Brand.WarnBright.copy(alpha = 0.55f), -CLOSE, CLOSE, 3.dp.toPx())
        arc(Brand.GoodBright, -IN_TUNE, IN_TUNE, 4.dp.toPx())

        // Tick marks.
        for (c in listOf(-50, -25, 0, 25, 50)) {
            val deg = (c / METER_RANGE * 70.0).toFloat()
            val rad = Math.toRadians((deg - 90).toDouble())
            val inner = if (c == 0) radius - 14.dp.toPx() else radius - 9.dp.toPx()
            drawLine(
                color = if (c == 0) Brand.GoodBright else Brand.Ivory.copy(alpha = 0.35f),
                start = Offset(cx + (radius * Math.cos(rad)).toFloat(), cy + (radius * Math.sin(rad)).toFloat()),
                end = Offset(cx + (inner * Math.cos(rad)).toFloat(), cy + (inner * Math.sin(rad)).toFloat()),
                strokeWidth = if (c == 0) 2.dp.toPx() else 1.dp.toPx(),
            )
        }

        rotate(degrees = angle, pivot = Offset(cx, cy)) {
            drawLine(
                color = needleColour,
                start = Offset(cx, cy),
                end = Offset(cx, cy - radius + 8.dp.toPx()),
                strokeWidth = 2.5.dp.toPx(),
                cap = StrokeCap.Round,
            )
        }
        drawCircle(color = Brand.Gold, radius = 4.dp.toPx(), center = Offset(cx, cy))
    }
}

@Composable
private fun StringPicker(state: TunerState) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        for (id in listOf("A", "D", "G", "C")) {
            val selected = state.mode == id
            val isDone = id in state.done
            Surface(
                modifier = Modifier
                    .weight(1f)
                    .height(54.dp),
                shape = RoundedCornerShape(2.dp),
                color = if (selected) Brand.Prussian else Color.White,
                border = BorderStroke(1.dp, if (isDone) Brand.Good else Brand.Rule),
                onClick = { state.mode = id },
            ) {
                Column(
                    Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(id, fontSize = 19.sp, fontWeight = FontWeight.SemiBold,
                         color = if (selected) Brand.Ivory else Brand.Charcoal)
                    if (isDone) {
                        Text("IN TUNE", style = Caps, fontSize = 8.sp,
                             color = if (selected) Brand.GoodBright else Brand.Good)
                    }
                }
            }
        }
        Surface(
            modifier = Modifier
                .weight(1f)
                .height(54.dp),
            shape = RoundedCornerShape(2.dp),
            color = if (state.mode == "auto") Brand.Prussian else Color.White,
            border = BorderStroke(1.dp, Brand.Rule),
            onClick = { state.mode = "auto" },
        ) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Auto", fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                     color = if (state.mode == "auto") Brand.Ivory else Brand.Charcoal)
            }
        }
    }
}

@Composable
private fun AdviceCard(state: TunerState, r: TunerReading) {
    val next = state.order.firstOrNull { it !in state.done }
    when {
        r.live && r.strayed -> RuledNote(
            accent = Brand.Gold,
            text = "That is ${Music.spokenNote(r.playedName)}, not an open string. The four open strings are C, G, D and A. " +
                "If you are tuning, take every finger off the string and bow it again.",
            measure = "Not a tuning reading",
        )
        r.live -> {
            val adv = Music.tuningAdvice(r.centsOff)
            val label = when (adv.device) {
                Music.Device.PEG -> "Use the peg"
                Music.Device.FINE_TUNER -> "Use the fine tuner"
                Music.Device.NONE -> "Done"
            }
            RuledNote(
                accent = if (adv.device == Music.Device.NONE) Brand.Good else Brand.Gold,
                text = "${adv.headline}: the ${r.targetId} string. ${adv.detail}",
                measure = label,
            )
        }
        next != null -> RuledNote(
            accent = Brand.Gold,
            text = "Next: the $next string. ${Music.stringById(next)?.hint ?: ""} " +
                "Bow it and let it ring while you read the meter.",
        )
        else -> RuledNote(
            accent = Brand.Good,
            text = "All four strings are in tune. Go round once more to be sure: tuning one string changes the tension on the others.",
        )
    }
}
