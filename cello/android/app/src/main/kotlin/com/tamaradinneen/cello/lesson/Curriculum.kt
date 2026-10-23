package com.tamaradinneen.cello.lesson

import android.content.Context
import org.json.JSONObject

/**
 * The course content, parsed from assets/curriculum.json. That file is the
 * single source shared with the web app, so the two teach exactly the same
 * course and only one copy has to be edited.
 */
data class Step(
    val type: String,
    val title: String? = null,
    val body: List<String> = emptyList(),
    val tip: String? = null,
    val prompt: String? = null,
    val items: List<String> = emptyList(),
    val strings: List<String> = emptyList(),
    val targetNote: String? = null,
    val targetString: String? = null,
    val notes: List<String> = emptyList(),
    val holdSec: Double = 0.0,
    val toleranceCents: Double = 35.0,
    val reps: Int = 3,
    val passReps: Int = 2,
    val metrics: Set<String> = setOf("pitch", "duration"),
    val bpm: Int = 60,
    val beats: Int = 8,
    val beatsPerNote: Int = 1,
    val toleranceMs: Double = 180.0,
    val note: String? = null,
    val coach: Map<String, String> = emptyMap(),
)

data class Lesson(
    val id: String,
    val unit: String,
    val title: String,
    val minutes: Int,
    val goal: String,
    val steps: List<Step>,
)

data class Unit(val id: String, val title: String, val lessons: List<String>)

data class Curriculum(
    val title: String,
    val subtitle: String,
    val sizeNote: String,
    val tuningNote: String,
    val units: List<Unit>,
    val lessons: List<Lesson>,
) {
    fun lesson(id: String): Lesson? = lessons.firstOrNull { it.id == id }
    fun indexOf(id: String): Int = lessons.indexOfFirst { it.id == id }

    companion object {
        fun load(context: Context): Curriculum {
            val text = context.assets.open("curriculum.json").bufferedReader().use { it.readText() }
            return parse(JSONObject(text))
        }

        fun parse(root: JSONObject): Curriculum {
            val units = root.optJSONArray("units")?.let { arr ->
                (0 until arr.length()).map { i ->
                    val o = arr.getJSONObject(i)
                    Unit(o.getString("id"), o.getString("title"), o.strings("lessons"))
                }
            } ?: emptyList()

            val lessons = root.optJSONArray("lessons")?.let { arr ->
                (0 until arr.length()).map { i -> parseLesson(arr.getJSONObject(i)) }
            } ?: emptyList()

            return Curriculum(
                title = root.optString("title"),
                subtitle = root.optString("subtitle"),
                sizeNote = root.optString("sizeNote"),
                tuningNote = root.optString("tuningNote"),
                units = units,
                lessons = lessons,
            )
        }

        private fun parseLesson(o: JSONObject): Lesson {
            val steps = o.optJSONArray("steps")?.let { arr ->
                (0 until arr.length()).map { i -> parseStep(arr.getJSONObject(i)) }
            } ?: emptyList()
            return Lesson(
                id = o.getString("id"),
                unit = o.optString("unit"),
                title = o.optString("title"),
                minutes = o.optInt("minutes", 5),
                goal = o.optString("goal"),
                steps = steps,
            )
        }

        private fun parseStep(o: JSONObject): Step {
            val target = o.optJSONObject("target")
            val coach = o.optJSONObject("coach")?.let { c ->
                c.keys().asSequence().associateWith { k -> c.getString(k) }
            } ?: emptyMap()
            val metrics = o.optJSONArray("metrics")?.let { a ->
                (0 until a.length()).map { a.getString(it) }.toSet()
            } ?: setOf("pitch", "duration")

            return Step(
                type = o.optString("type"),
                title = o.optStringOrNull("title"),
                body = o.strings("body"),
                tip = o.optStringOrNull("tip"),
                prompt = o.optStringOrNull("prompt"),
                items = o.strings("items"),
                strings = o.strings("strings"),
                targetNote = target?.optStringOrNull("note"),
                targetString = target?.optStringOrNull("string"),
                notes = o.strings("notes"),
                holdSec = o.optDouble("holdSec", 0.0),
                toleranceCents = o.optDouble("toleranceCents", 35.0),
                reps = o.optInt("reps", 3),
                passReps = o.optInt("passReps", 2),
                metrics = metrics,
                bpm = o.optInt("bpm", 60),
                beats = o.optInt("beats", 8),
                beatsPerNote = o.optInt("beatsPerNote", 1),
                toleranceMs = o.optDouble("toleranceMs", 180.0),
                note = o.optStringOrNull("note"),
                coach = coach,
            )
        }

        private fun JSONObject.strings(key: String): List<String> =
            optJSONArray(key)?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: emptyList()

        private fun JSONObject.optStringOrNull(key: String): String? =
            if (has(key) && !isNull(key)) getString(key) else null
    }
}
