package com.tamaradinneen.cello

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.platform.LocalLifecycleOwner
import com.tamaradinneen.cello.audio.AudioEngine
import com.tamaradinneen.cello.lesson.Curriculum
import com.tamaradinneen.cello.lesson.Progress
import com.tamaradinneen.cello.ui.*

class MainActivity : ComponentActivity() {
    private val engine = AudioEngine()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val curriculum = try { Curriculum.load(this) } catch (e: Exception) { null }
        val progress = Progress(this)
        setContent { CelloTheme { App(engine, curriculum, progress) } }
    }

    override fun onStop() {
        super.onStop()
        // Release the microphone whenever the app is not in front. Holding it
        // in the background would block the phone's other audio apps.
        engine.stop()
    }
}

@Composable
private fun App(engine: AudioEngine, curriculum: Curriculum?, progress: Progress) {
    val context = LocalContext.current
    var granted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        )
    }
    var denied by remember { mutableStateOf(false) }
    var tab by remember { mutableIntStateOf(0) }
    var a4 by remember { mutableDoubleStateOf(progress.a4) }
    val status by engine.status.collectAsState()

    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        granted = ok
        denied = !ok
        if (ok) engine.start()
    }

    // Start on resume, stop on pause, so the microphone is only ever held
    // while the app is actually in front.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner, granted) {
        val obs = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> if (granted && !engine.status.value.running) engine.start()
                Lifecycle.Event.ON_STOP -> engine.stop()
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(obs)
        onDispose { lifecycleOwner.lifecycle.removeObserver(obs) }
    }

    Scaffold(
        containerColor = Brand.Ivory,
        topBar = {
            Column(Modifier.background(Brand.Prussian).statusBarsPadding()) {
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.Bottom,
                ) {
                    Text("Cello from scratch", color = Brand.Ivory, fontSize = 18.sp,
                         fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    Text("1/8 SIZE", style = Caps, color = Brand.Gold, fontSize = 10.sp)
                }
                TabRow(
                    selectedTabIndex = tab,
                    containerColor = Brand.Prussian,
                    contentColor = Brand.Ivory,
                    indicator = { positions ->
                        if (tab < positions.size) {
                            TabRowDefaults.SecondaryIndicator(
                                Modifier.tabIndicatorOffset(positions[tab]),
                                color = Brand.Gold,
                            )
                        }
                    },
                ) {
                    listOf("Tune", "Lessons", "Practise").forEachIndexed { i, label ->
                        Tab(
                            selected = tab == i,
                            onClick = { tab = i },
                            text = {
                                Text(label.uppercase(), style = Caps, fontSize = 11.sp,
                                     color = if (tab == i) Brand.Ivory else Brand.Ivory.copy(alpha = 0.65f))
                            },
                        )
                    }
                }
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding).navigationBarsPadding()) {
            when {
                !granted -> MicGate(denied) { launcher.launch(Manifest.permission.RECORD_AUDIO) }
                status.error != null -> ErrorPanel(status.error!!) { engine.start() }
                curriculum == null -> ErrorPanel("The course content could not be loaded.") { }
                else -> when (tab) {
                    0 -> TunerTab(engine, a4, progress)
                    1 -> LessonsScreen(curriculum, engine, progress, a4)
                    else -> PracticeScreen(curriculum, progress, engine, a4) {
                        a4 = it; progress.a4 = it
                    }
                }
            }
        }
    }
}

@Composable
private fun TunerTab(engine: AudioEngine, a4: Double, progress: Progress) {
    val state = remember { TunerState(engine, { a4 }, onAllDone = { progress.tunedCount += 1 }) }
    DisposableEffect(Unit) {
        val off = engine.addListener { state.onFrame(it) }
        onDispose { off() }
    }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(14.dp)) {
        TunerPanel(state, a4)
        Spacer(Modifier.height(40.dp))
    }
}

@Composable
private fun MicGate(denied: Boolean, onAsk: () -> kotlin.Unit) {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(14.dp)) {
        SectionCard {
            Text("Let the app hear your cello", fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
            Spacer(Modifier.height(8.dp))
            Body("Everything here works by listening: the tuner reads the pitch of each string, and the lessons listen to you play and tell you what to change.")
            Spacer(Modifier.height(8.dp))
            Body("Nothing is recorded and nothing leaves your device. The app has no network permission at all.")
            Spacer(Modifier.height(14.dp))
            Button(onClick = onAsk, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(2.dp)) {
                Text("Allow the microphone")
            }
        }
        if (denied) {
            Spacer(Modifier.height(10.dp))
            RuledNote(
                "Microphone access was refused. Open Settings, then Apps, then Cello, then Permissions, and allow the microphone.",
                Brand.Off,
            )
        }
    }
}

@Composable
private fun ErrorPanel(message: String, onRetry: () -> kotlin.Unit) {
    Column(Modifier.padding(14.dp)) {
        RuledNote(message, Brand.Off)
        Spacer(Modifier.height(10.dp))
        Button(onClick = onRetry, shape = RoundedCornerShape(2.dp)) { Text("Try again") }
    }
}
