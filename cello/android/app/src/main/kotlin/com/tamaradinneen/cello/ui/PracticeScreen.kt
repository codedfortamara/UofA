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
import com.tamaradinneen.cello.lesson.Curriculum
import com.tamaradinneen.cello.lesson.Progress

@Composable
fun PracticeScreen(
    curriculum: Curriculum,
    progress: Progress,
    engine: AudioEngine,
    a4: Double,
    onA4Change: (Double) -> kotlin.Unit,
) {
    val drone = remember { Drone() }
    val metro = remember { Metronome() }
    var dronePlaying by remember { mutableStateOf(false) }
    var droneString by remember { mutableStateOf("D") }
    var metroRunning by remember { mutableStateOf(false) }
    var bpm by remember { mutableFloatStateOf(60f) }
    var confirmReset by remember { mutableStateOf(false) }
    var version by remember { mutableIntStateOf(0) }
    val status by engine.status.collectAsState()

    DisposableEffect(Unit) { onDispose { drone.stop(); metro.stop() } }

    Column(Modifier.verticalScroll(rememberScrollState()).padding(14.dp)) {
        @Suppress("UNUSED_EXPRESSION") version
        Heading("Practice tools")
        Spacer(Modifier.height(12.dp))

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Stat(progress.completedCount(curriculum.lessons).toString(), "lessons done", Modifier.weight(1f))
            Stat((progress.practiceSeconds / 60).toString(), "minutes practised", Modifier.weight(1f))
            Stat(progress.tunedCount.toString(), "times tuned", Modifier.weight(1f))
        }

        Spacer(Modifier.height(14.dp))
        SectionCard {
            Text("Drone", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Spacer(Modifier.height(6.dp))
            Body("Play a scale against a held note. Notes that are in tune lock in and sound still; notes that are out produce a rough beating. This teaches your ear faster than any meter.")
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                for (id in listOf("A", "D", "G", "C")) {
                    val sel = droneString == id
                    Surface(
                        modifier = Modifier.weight(1f).height(44.dp),
                        shape = RoundedCornerShape(2.dp),
                        color = if (sel) Brand.Prussian else Color.White,
                        border = BorderStroke(1.dp, Brand.Rule),
                        onClick = {
                            droneString = id
                            if (dronePlaying) drone.start(Music.stringFreq(id, a4))
                        },
                    ) {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Text(id, fontSize = 17.sp, fontWeight = FontWeight.SemiBold,
                                 color = if (sel) Brand.Ivory else Brand.Charcoal)
                        }
                    }
                }
            }
            Spacer(Modifier.height(10.dp))
            Button(
                onClick = {
                    if (dronePlaying) { drone.stop(); dronePlaying = false }
                    else { drone.start(Music.stringFreq(droneString, a4)); dronePlaying = true }
                },
                modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(2.dp),
            ) { Text(if (dronePlaying) "Stop the drone" else "Start the drone") }
        }

        Spacer(Modifier.height(12.dp))
        SectionCard {
            Text("Metronome", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Tempo", fontSize = 15.sp, modifier = Modifier.width(62.dp))
                Slider(
                    value = bpm,
                    onValueChange = { bpm = it },
                    valueRange = 40f..140f,
                    steps = 99,
                    modifier = Modifier.weight(1f),
                    colors = SliderDefaults.colors(thumbColor = Brand.Prussian, activeTrackColor = Brand.Prussian),
                )
                Text("${bpm.toInt()} bpm", fontSize = 14.sp, modifier = Modifier.width(66.dp),
                     color = Brand.CharcoalSoft)
            }
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = {
                    if (metroRunning) { metro.stop(); metroRunning = false }
                    else { metro.start(bpm.toInt(), 64, countIn = 0); metroRunning = true }
                },
                modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(2.dp),
            ) { Text(if (metroRunning) "Stop the metronome" else "Start the metronome") }
        }

        Spacer(Modifier.height(12.dp))
        SectionCard {
            Text("Reference pitch", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Concert A", fontSize = 15.sp, modifier = Modifier.weight(1f))
                IconTextButton("−") { onA4Change((a4 - 0.5).coerceAtLeast(415.0)) }
                Text("%.1f Hz".format(a4), fontSize = 15.sp,
                     modifier = Modifier.padding(horizontal = 10.dp).width(74.dp))
                IconTextButton("+") { onA4Change((a4 + 0.5).coerceAtMost(466.0)) }
            }
            Spacer(Modifier.height(6.dp))
            Body("Leave this at 440 unless you are playing with someone who tunes differently.",
                 color = Brand.CharcoalSoft)
        }

        Spacer(Modifier.height(12.dp))
        SectionCard {
            Text("Microphone", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Spacer(Modifier.height(6.dp))
            Body(
                if (!status.running) "Not running."
                else buildString {
                    append("Listening at ${"%.1f".format(status.sampleRate / 1000.0)} kHz from the ${status.source} source. ")
                    append(
                        if (status.unprocessed)
                            "That is the raw, unprocessed input, which is what a tuner wants."
                        else
                            "This device does not offer an unprocessed input, so readings may be slightly less steady."
                    )
                    if (status.effectsDisabled.isNotEmpty()) {
                        append(" Switched off: ${status.effectsDisabled.joinToString(", ")}.")
                    }
                },
                color = Brand.CharcoalSoft,
            )
        }

        Spacer(Modifier.height(12.dp))
        SectionCard {
            Text("Progress", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Spacer(Modifier.height(6.dp))
            Body("Progress is kept on this device only. The app has no network permission at all, so nothing can leave it.")
            Spacer(Modifier.height(10.dp))
            OutlinedButton(
                onClick = {
                    if (confirmReset) { progress.reset(); confirmReset = false; version++ }
                    else confirmReset = true
                },
                shape = RoundedCornerShape(2.dp),
            ) { Text(if (confirmReset) "Tap again to confirm" else "Clear my progress", fontSize = 13.sp) }
        }
        Spacer(Modifier.height(40.dp))
    }
}

@Composable
private fun IconTextButton(label: String, onClick: () -> kotlin.Unit) {
    Surface(
        shape = CircleShape,
        color = Color.White,
        border = BorderStroke(1.dp, Brand.Rule),
        onClick = onClick,
        modifier = Modifier.size(42.dp),
    ) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(label, fontSize = 19.sp, color = Brand.Prussian)
        }
    }
}

@Composable
private fun Stat(value: String, label: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(2.dp),
        color = Color.White,
        border = BorderStroke(1.dp, Brand.Rule),
    ) {
        Column(Modifier.padding(vertical = 10.dp).fillMaxWidth(),
               horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontSize = 22.sp, fontWeight = FontWeight.SemiBold, color = Brand.Charcoal)
            Text(label.uppercase(), style = Caps, fontSize = 9.sp, color = Brand.CharcoalSoft)
        }
    }
}
