package com.tamaradinneen.cello.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tamaradinneen.cello.audio.AudioEngine
import com.tamaradinneen.cello.audio.Drone
import com.tamaradinneen.cello.audio.Metronome
import com.tamaradinneen.cello.audio.Music
import com.tamaradinneen.cello.audio.Reference
import com.tamaradinneen.cello.lesson.*
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * A detected onset lags the real one: the window covers the previous 85 ms and
 * the segmenter waits for two confident frames before calling a note real.
 * Taking that out stops the app accusing a player of being late when it is the
 * detector that is behind. Interval spread is immune to this by construction.
 */
private const val ONSET_LATENCY_MS = 85L

@Composable
fun LessonsScreen(curriculum: Curriculum, engine: AudioEngine, progress: Progress, a4: Double) {
    var openId by remember { mutableStateOf<String?>(null) }
    var version by remember { mutableIntStateOf(0) }

    val open = openId?.let { curriculum.lesson(it) }
    if (open == null) {
        LessonList(curriculum, progress, version) { openId = it }
    } else {
        LessonRunner(
            lesson = open,
            curriculum = curriculum,
            engine = engine,
            progress = progress,
            a4 = a4,
            onExit = { openId = null; version++ },
        )
    }
}

@Composable
private fun LessonList(curriculum: Curriculum, progress: Progress, version: Int, onOpen: (String) -> Unit) {
    @Suppress("UNUSED_EXPRESSION") version
    val done = curriculum.lessons.count { progress.isComplete(it.id) }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(14.dp)) {
        Heading("The course")
        Spacer(Modifier.height(6.dp))
        Body("Fourteen lessons, five to ten minutes each, starting from never having held a cello. The app listens while you play and tells you what to change.")
        Spacer(Modifier.height(12.dp))
        ProgressRail(done.toFloat() / curriculum.lessons.size)
        Spacer(Modifier.height(6.dp))
        CapsLabel("$done of ${curriculum.lessons.size} lessons done")

        for (unit in curriculum.units) {
            Spacer(Modifier.height(18.dp))
            CapsLabel(unit.title)
            Spacer(Modifier.height(6.dp))
            for (id in unit.lessons) {
                val l = curriculum.lesson(id) ?: continue
                val n = curriculum.indexOf(id) + 1
                val complete = progress.isComplete(id)
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp),
                    shape = RoundedCornerShape(2.dp),
                    color = Color.White,
                    border = BorderStroke(1.dp, Brand.Rule),
                    onClick = { onOpen(id) },
                ) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            Modifier.size(30.dp).background(
                                if (complete) Brand.Good else Color.White, CircleShape
                            ).then(
                                if (complete) Modifier else Modifier
                            ),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                if (complete) "✓" else "$n",
                                fontSize = 13.sp,
                                color = if (complete) Color.White else Brand.CharcoalSoft,
                            )
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(l.title, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = Brand.Charcoal)
                            Text("${l.minutes} min · ${l.goal}", fontSize = 12.sp, color = Brand.CharcoalSoft, lineHeight = 17.sp)
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(18.dp))
        SectionCard {
            Text("About your instrument", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            Spacer(Modifier.height(6.dp))
            Body(curriculum.sizeNote)
            Spacer(Modifier.height(8.dp))
            Body(curriculum.tuningNote)
        }
        Spacer(Modifier.height(30.dp))
    }
}

@Composable
private fun LessonRunner(
    lesson: Lesson,
    curriculum: Curriculum,
    engine: AudioEngine,
    progress: Progress,
    a4: Double,
    onExit: () -> kotlin.Unit,
) {
    var stepIndex by remember(lesson.id) { mutableIntStateOf(0) }
    val startedAt = remember(lesson.id) { System.currentTimeMillis() }

    Column(Modifier.verticalScroll(rememberScrollState()).padding(14.dp)) {
        OutlinedButton(onClick = onExit, shape = RoundedCornerShape(2.dp)) {
            Text("←  All lessons", fontSize = 13.sp)
        }
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            Heading(lesson.title, Modifier.weight(1f))
            Text(
                if (stepIndex < lesson.steps.size) "Step ${stepIndex + 1} of ${lesson.steps.size}" else "Done",
                fontSize = 12.sp, color = Brand.CharcoalSoft,
            )
        }
        Spacer(Modifier.height(8.dp))
        ProgressRail(stepIndex.toFloat() / lesson.steps.size)
        Spacer(Modifier.height(12.dp))

        if (stepIndex >= lesson.steps.size) {
            LaunchedEffect(lesson.id) {
                progress.completeLesson(lesson.id)
                progress.addPractice(((System.currentTimeMillis() - startedAt) / 1000).toInt())
            }
            SectionCard {
                Text("Lesson complete", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                Spacer(Modifier.height(6.dp))
                Body(lesson.goal)
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = onExit, shape = RoundedCornerShape(2.dp)) { Text("Back to the course") }
                    OutlinedButton(onClick = { stepIndex = 0 }, shape = RoundedCornerShape(2.dp)) { Text("Repeat") }
                }
            }
        } else {
            val step = lesson.steps[stepIndex]
            key(lesson.id, stepIndex) {
                StepView(step, engine, progress, a4) { stepIndex++ }
            }
        }
        Spacer(Modifier.height(40.dp))
    }
}

@Composable
private fun StepView(step: Step, engine: AudioEngine, progress: Progress, a4: Double, onNext: () -> kotlin.Unit) {
    when (step.type) {
        "info" -> InfoStep(step, onNext)
        "check" -> CheckStep(step, onNext)
        "tune" -> TuneStep(step, engine, progress, a4, onNext)
        "listen" -> ListenStep(step, engine, a4, onNext)
        "sequence" -> SequenceStep(step, engine, a4, onNext)
        "rhythm" -> RhythmStep(step, engine, onNext)
        "drone" -> DroneStep(step, a4, onNext)
        else -> InfoStep(step, onNext)
    }
}

@Composable
private fun NextButton(label: String = "Continue", gold: Boolean = false, onClick: () -> kotlin.Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(2.dp),
        colors = if (gold) ButtonDefaults.buttonColors(containerColor = Brand.GoldDeep) else ButtonDefaults.buttonColors(),
    ) { Text(label) }
}

@Composable
private fun InfoStep(step: Step, onNext: () -> kotlin.Unit) {
    SectionCard {
        step.title?.let {
            Text(it, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Spacer(Modifier.height(8.dp))
        }
        for (p in step.body) {
            Body(p)
            Spacer(Modifier.height(8.dp))
        }
        step.tip?.let {
            Spacer(Modifier.height(2.dp))
            RuledNote(it, Brand.Gold, background = Brand.IvoryDim)
        }
    }
    Spacer(Modifier.height(10.dp))
    NextButton { onNext() }
}

@Composable
private fun CheckStep(step: Step, onNext: () -> kotlin.Unit) {
    val checked = remember { mutableStateListOf(*Array(step.items.size) { false }) }
    SectionCard {
        step.prompt?.let { Body(it); Spacer(Modifier.height(8.dp)) }
        step.items.forEachIndexed { i, item ->
            Row(
                Modifier.fillMaxWidth().padding(vertical = 2.dp),
                verticalAlignment = Alignment.Top,
            ) {
                Checkbox(
                    checked = checked[i],
                    onCheckedChange = { checked[i] = it },
                    colors = CheckboxDefaults.colors(checkedColor = Brand.Prussian),
                )
                Body(item, Modifier.padding(top = 13.dp))
            }
        }
    }
    Spacer(Modifier.height(10.dp))
    NextButton { onNext() }
}

@Composable
private fun TuneStep(step: Step, engine: AudioEngine, progress: Progress, a4: Double, onNext: () -> kotlin.Unit) {
    val state = remember {
        TunerState(engine, { a4 }, step.strings.ifEmpty { listOf("A", "D", "G", "C") },
            onAllDone = { progress.tunedCount += 1 })
    }
    LaunchedEffect(Unit) { state.selectNext() }
    DisposableEffect(Unit) {
        val off = engine.addListener { state.onFrame(it) }
        onDispose { off() }
    }
    step.prompt?.let {
        SectionCard { Body(it) }
        Spacer(Modifier.height(10.dp))
    }
    TunerPanel(state, a4, showHelp = false)
    Spacer(Modifier.height(12.dp))
    NextButton("Done tuning, continue") { onNext() }
}

/** Live readout shared by the listening steps. */
@Composable
private fun ListenStage(label: String, name: String, octave: String, sub: String, level: Float) {
    Stage {
        CapsLabel(label, Brand.Gold)
        Spacer(Modifier.height(4.dp))
        CentreRow {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(
                    name.ifEmpty { "–" }, fontSize = 50.sp, fontWeight = FontWeight.SemiBold,
                    color = if (name.isEmpty()) Brand.Ivory.copy(alpha = 0.32f) else Brand.Ivory,
                )
                if (octave.isNotEmpty()) {
                    Text(octave, fontSize = 18.sp, color = Brand.Gold, modifier = Modifier.padding(start = 3.dp, bottom = 8.dp))
                }
            }
        }
        CentreRow { Text(sub, fontSize = 13.sp, color = Brand.Ivory.copy(alpha = 0.6f)) }
        Box(
            Modifier.padding(top = 10.dp).fillMaxWidth().height(3.dp)
                .background(Brand.Ivory.copy(alpha = 0.15f))
        ) { Box(Modifier.fillMaxWidth(level).height(3.dp).background(Brand.Gold)) }
    }
}

private fun noteLabel(hz: Double, a4: Double): Pair<String, String> {
    val n = Music.nearestNote(hz, a4) ?: return "" to ""
    val m = Regex("^([A-G]#?)(-?\\d+)$").find(n.name) ?: return n.name to ""
    return m.groupValues[1] to m.groupValues[2]
}

@Composable
private fun ListenStep(step: Step, engine: AudioEngine, a4: Double, onNext: () -> kotlin.Unit) {
    val targetHz = remember(step) {
        when {
            step.targetNote != null -> Music.noteToFreq(step.targetNote, a4)
            step.targetString != null -> Music.stringFreq(step.targetString, a4)
            else -> 0.0
        }
    }
    val targetLabel = remember(step) {
        step.targetNote?.let { Music.spokenNote(it) } ?: step.targetString?.let { "the $it string" } ?: "a note"
    }
    val passReps = minOf(step.passReps, step.reps)

    var listening by remember { mutableStateOf(false) }
    var finished by remember { mutableStateOf(false) }
    val attempts = remember { mutableStateListOf<Grade>() }
    var liveName by remember { mutableStateOf("") }
    var liveOct by remember { mutableStateOf("") }
    var liveSub by remember { mutableStateOf("Press start, then play") }
    var level by remember { mutableFloatStateOf(0f) }

    val segmenter = remember(step) {
        NoteSegmenter(maxNoteSec = maxOf(2.5, step.holdSec * 1.4))
    }

    DisposableEffect(listening) {
        if (!listening) return@DisposableEffect onDispose { }
        val off = engine.addListener { f ->
            level = (f.rms / 0.08).coerceIn(0.0, 1.0).toFloat()
            val hz = engine.smoothed()
            if (hz != null && f.confidence >= 0.45) {
                val (n, o) = noteLabel(hz, a4)
                liveName = n; liveOct = o
                if (targetHz > 0) {
                    val off2 = Music.cents(hz, targetHz)
                    liveSub = "${if (off2 > 0) "+" else "−"}${abs(off2).roundToInt()} cents"
                }
            } else {
                liveName = ""; liveOct = ""
            }
            val ev = segmenter.push(f)
            if (ev != null && targetHz > 0) {
                val g = Grading.gradeNote(ev, targetHz, step.toleranceCents, step.holdSec, step.metrics)
                attempts.add(g)
                val hits = attempts.count { it.pass }
                if (hits >= passReps || attempts.size >= step.reps) {
                    listening = false
                    finished = true
                }
            }
        }
        onDispose { off() }
    }

    SectionCard {
        step.prompt?.let { Body(it); Spacer(Modifier.height(8.dp)) }
        CapsLabel("Target: $targetLabel" + if (step.targetNote != null) " (%.1f Hz)".format(targetHz) else "")
    }
    Spacer(Modifier.height(10.dp))
    ListenStage(if (listening) "Listening" else if (finished) "Finished" else "Not listening",
                liveName, liveOct, liveSub, level)

    Spacer(Modifier.height(10.dp))
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        for (i in 0 until step.reps) {
            val a = attempts.getOrNull(i)
            Pip(hit = a?.pass == true, miss = a != null && !a.pass)
        }
        val hits = attempts.count { it.pass }
        Text("  $hits of $passReps good ${if (passReps == 1) "try" else "tries"} needed",
             fontSize = 12.sp, color = Brand.CharcoalSoft)
    }

    attempts.lastOrNull()?.let { g ->
        Spacer(Modifier.height(8.dp))
        RuledNote(
            Grading.coachFor(step.coach, g.issue, g.direction, g.semitonesOff),
            if (g.pass) Brand.Good else Brand.Warn,
            g.detail,
        )
    }

    Spacer(Modifier.height(10.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(
            onClick = {
                if (listening) { listening = false } else {
                    attempts.clear(); segmenter.reset(); finished = false
                    liveSub = "Play the note and let it ring"
                    listening = true
                }
            },
            modifier = Modifier.weight(1f),
            shape = RoundedCornerShape(2.dp),
        ) { Text(if (listening) "Stop" else if (attempts.isEmpty()) "Start listening" else "Try again") }
        OutlinedButton(
            onClick = { if (targetHz > 0) Reference.play(targetHz, 2.0) },
            modifier = Modifier.weight(1f),
            shape = RoundedCornerShape(2.dp),
        ) { Text("Hear it") }
    }
    Spacer(Modifier.height(8.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = onNext, modifier = Modifier.weight(1f), shape = RoundedCornerShape(2.dp)) {
            Text("Skip this step", fontSize = 13.sp)
        }
        if (finished) {
            val passed = attempts.count { it.pass } >= passReps
            Button(
                onClick = onNext,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(2.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Brand.GoldDeep),
            ) { Text(if (passed) "Well done" else "Continue", fontSize = 13.sp) }
        }
    }
}

@Composable
private fun SequenceStep(step: Step, engine: AudioEngine, a4: Double, onNext: () -> kotlin.Unit) {
    val expected = remember(step) { step.notes.map { Music.noteToFreq(it, a4) } }
    var listening by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<Grading.SeqResult?>(null) }
    val got = remember { mutableStateListOf<NoteEvent>() }
    var liveName by remember { mutableStateOf("") }
    var liveOct by remember { mutableStateOf("") }
    var level by remember { mutableFloatStateOf(0f) }
    val segmenter = remember(step) { NoteSegmenter(maxNoteSec = 8.0) }

    DisposableEffect(listening) {
        if (!listening) return@DisposableEffect onDispose { }
        val off = engine.addListener { f ->
            level = (f.rms / 0.08).coerceIn(0.0, 1.0).toFloat()
            val hz = engine.smoothed()
            if (hz != null && f.confidence >= 0.45) {
                val (n, o) = noteLabel(hz, a4); liveName = n; liveOct = o
            } else { liveName = "" }
            val ev = segmenter.push(f)
            if (ev != null) {
                got.add(ev)
                if (got.size >= expected.size) {
                    result = Grading.gradeSequence(got.toList(), expected, step.toleranceCents)
                    listening = false
                }
            }
        }
        onDispose { off() }
    }

    SectionCard {
        step.prompt?.let { Body(it); Spacer(Modifier.height(10.dp)) }
        FlowRowNotes(step.notes, got.size, expected, step.toleranceCents, got)
    }
    Spacer(Modifier.height(10.dp))
    ListenStage(if (listening) "Listening" else "Not listening", liveName, liveOct,
                if (listening) "Play the notes in order, with a gap between each" else "Press start, then play", level)

    result?.let { r ->
        Spacer(Modifier.height(10.dp))
        RuledNote(sequenceMessage(r, step), if (r.pass) Brand.Good else Brand.Warn,
                  "${r.correct} of ${r.total} notes correct")
    }

    Spacer(Modifier.height(10.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(
            onClick = {
                if (listening) listening = false
                else { got.clear(); segmenter.reset(); result = null; listening = true }
            },
            modifier = Modifier.weight(1f), shape = RoundedCornerShape(2.dp),
        ) { Text(if (listening) "Stop" else if (result == null) "Start listening" else "Play it again") }
        OutlinedButton(
            onClick = { expected.firstOrNull()?.let { Reference.play(it, 0.6) } },
            modifier = Modifier.weight(1f), shape = RoundedCornerShape(2.dp),
        ) { Text("Hear first note", fontSize = 12.sp) }
    }
    Spacer(Modifier.height(8.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = onNext, modifier = Modifier.weight(1f), shape = RoundedCornerShape(2.dp)) {
            Text("Skip this step", fontSize = 13.sp)
        }
        if (result != null) {
            Button(onClick = onNext, modifier = Modifier.weight(1f), shape = RoundedCornerShape(2.dp),
                   colors = ButtonDefaults.buttonColors(containerColor = Brand.GoldDeep)) {
                Text(if (result!!.pass) "Well done" else "Continue", fontSize = 13.sp)
            }
        }
    }
}

@Composable
private fun FlowRowNotes(names: List<String>, playedCount: Int, expected: List<Double>,
                         tolerance: Double, got: List<NoteEvent>) {
    Column {
        var i = 0
        while (i < names.size) {
            Row(Modifier.fillMaxWidth().padding(bottom = 4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                var c = 0
                while (c < 5 && i < names.size) {
                    val idx = i
                    val ev = got.getOrNull(idx)
                    val colour = when {
                        ev == null -> Brand.Rule
                        abs(Music.cents(ev.hz, expected[idx])) <= tolerance -> Brand.Good
                        abs(Music.cents(ev.hz, expected[idx])) < 70 -> Brand.Warn
                        else -> Brand.Off
                    }
                    val filled = ev != null && abs(Music.cents(ev.hz, expected[idx])) <= tolerance
                    Surface(
                        shape = RoundedCornerShape(2.dp),
                        color = if (filled) Brand.Good else Color.White,
                        border = BorderStroke(if (idx == playedCount) 2.dp else 1.dp,
                                              if (idx == playedCount) Brand.Prussian else colour),
                    ) {
                        Text(
                            names[idx].replace("#", "♯"),
                            modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
                            fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                            color = if (filled) Color.White else Brand.Charcoal,
                        )
                    }
                    i++; c++
                }
            }
        }
    }
}

private fun sequenceMessage(r: Grading.SeqResult, step: Step): String {
    if (r.pass) return Grading.coachFor(step.coach, "good")
    val parts = mutableListOf<String>()
    if (r.missing > 0) parts.add("${r.missing} note${if (r.missing == 1) "" else "s"} did not come through.")
    val wrong = r.results.filter { it.wrongNote }
    val outOfTune = r.results.filter { !it.pass && !it.wrongNote }
    if (wrong.isNotEmpty()) {
        parts.add("Wrong note on " + wrong.joinToString(", ") { "number ${it.index + 1}" } +
            ". Check the finger and the string.")
    }
    if (outOfTune.isNotEmpty()) {
        parts.add("Out of tune on " + outOfTune.joinToString("; ") {
            "number ${it.index + 1}, ${abs(it.centsOff).roundToInt()} cents ${if (it.centsOff < 0) "flat" else "sharp"}"
        } + ".")
    }
    return parts.joinToString(" ")
}

@Composable
private fun RhythmStep(step: Step, engine: AudioEngine, onNext: () -> kotlin.Unit) {
    val metro = remember { Metronome() }
    var running by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<Grading.RhythmResult?>(null) }
    var beatLabel by remember { mutableStateOf("Four clicks to count you in, then play") }
    var level by remember { mutableFloatStateOf(0f) }
    val onsets = remember { mutableStateListOf<Long>() }
    val expectedNotes = remember(step) { maxOf(1, Math.round(step.beats.toDouble() / step.beatsPerNote).toInt()) }
    val segmenter = remember(step) { NoteSegmenter() }

    DisposableEffect(Unit) { onDispose { metro.stop() } }

    DisposableEffect(running) {
        if (!running) return@DisposableEffect onDispose { }
        val off = engine.addListener { f ->
            level = (f.rms / 0.08).coerceIn(0.0, 1.0).toFloat()
            val grid = metro.gridStartMs
            if (grid == 0L) return@addListener
            val ev = segmenter.push(f)
            if (ev != null) {
                onsets.add(ev.startAt - ONSET_LATENCY_MS)
                if (onsets.size >= expectedNotes) {
                    result = Grading.gradeRhythm(onsets.toList(), grid, step.bpm, step.beats,
                                                 step.beatsPerNote, step.toleranceMs)
                    metro.stop(); running = false
                }
            }
        }
        onDispose { off() }
    }

    SectionCard {
        step.prompt?.let { Body(it); Spacer(Modifier.height(8.dp)) }
        CapsLabel("${step.bpm} beats per minute" + (step.targetString?.let { " · on the $it string" } ?: ""))
    }
    Spacer(Modifier.height(10.dp))
    Stage {
        CapsLabel(if (running) "Running" else "Not running", Brand.Gold)
        Spacer(Modifier.height(8.dp))
        CentreRow { Text(beatLabel, fontSize = 14.sp, color = Brand.Ivory.copy(alpha = 0.8f)) }
        Spacer(Modifier.height(8.dp))
        CentreRow {
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                for (i in 0 until expectedNotes) {
                    Box(
                        Modifier.size(10.dp).background(
                            if (i < onsets.size) Brand.GoodBright else Brand.Ivory.copy(alpha = 0.25f),
                            CircleShape
                        )
                    )
                }
            }
        }
        Box(Modifier.padding(top = 10.dp).fillMaxWidth().height(3.dp)
            .background(Brand.Ivory.copy(alpha = 0.15f))) {
            Box(Modifier.fillMaxWidth(level).height(3.dp).background(Brand.Gold))
        }
    }

    result?.let { r ->
        Spacer(Modifier.height(10.dp))
        RuledNote(
            step.coach[r.issue] ?: Grading.RHYTHM_COACH[r.issue] ?: "",
            if (r.pass) Brand.Good else Brand.Warn,
            r.detail,
        )
    }

    Spacer(Modifier.height(10.dp))
    Button(
        onClick = {
            if (running) { metro.stop(); running = false }
            else {
                onsets.clear(); segmenter.reset(); result = null; running = true
                metro.start(step.bpm, step.beats, countIn = 4) { beat, isCountIn ->
                    beatLabel = if (isCountIn) "Counting in: ${4 - beat}" else "Play now, one note per click"
                }
            }
        },
        modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(2.dp),
    ) { Text(if (running) "Stop" else if (result == null) "Start the metronome" else "Try again") }

    Spacer(Modifier.height(8.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = onNext, modifier = Modifier.weight(1f), shape = RoundedCornerShape(2.dp)) {
            Text("Skip this step", fontSize = 13.sp)
        }
        if (result != null) {
            Button(onClick = onNext, modifier = Modifier.weight(1f), shape = RoundedCornerShape(2.dp),
                   colors = ButtonDefaults.buttonColors(containerColor = Brand.GoldDeep)) {
                Text("Continue", fontSize = 13.sp)
            }
        }
    }
    Spacer(Modifier.height(10.dp))
    RuledNote(
        "The click is pitched high on purpose so the app ignores its own metronome. Headphones make this more reliable still.",
        Brand.Gold, background = Brand.IvoryDim,
    )
}

@Composable
private fun DroneStep(step: Step, a4: Double, onNext: () -> kotlin.Unit) {
    val drone = remember { Drone() }
    var playing by remember { mutableStateOf(false) }
    val hz = remember(step) { Music.noteToFreq(step.note ?: "D3", a4) }
    DisposableEffect(Unit) { onDispose { drone.stop() } }

    SectionCard {
        step.prompt?.let { Body(it); Spacer(Modifier.height(8.dp)) }
        CapsLabel("Drone on ${Music.spokenNote(step.note ?: "D3")}")
    }
    Spacer(Modifier.height(10.dp))
    Button(
        onClick = { if (playing) { drone.stop(); playing = false } else { drone.start(hz); playing = true } },
        modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(2.dp),
    ) { Text(if (playing) "Stop the drone" else "Start the drone") }
    Spacer(Modifier.height(8.dp))
    NextButton("Continue", gold = true) { drone.stop(); onNext() }
}
