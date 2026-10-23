package com.tamaradinneen.cello.lesson

import android.content.Context
import android.content.SharedPreferences

/**
 * Progress and settings. Kept on the device only: the app declares no network
 * permission at all, so none of this can go anywhere even in principle.
 */
class Progress(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("cello", Context.MODE_PRIVATE)

    var a4: Double
        get() = prefs.getFloat("a4", 440f).toDouble()
        set(v) { prefs.edit().putFloat("a4", v.coerceIn(415.0, 466.0).toFloat()).apply() }

    fun isComplete(lessonId: String): Boolean = prefs.getBoolean("done.$lessonId", false)

    fun completeLesson(lessonId: String) {
        prefs.edit().putBoolean("done.$lessonId", true).putString("last", lessonId).apply()
    }

    fun completedCount(all: List<Lesson>): Int = all.count { isComplete(it.id) }

    var tunedCount: Int
        get() = prefs.getInt("tuned", 0)
        set(v) { prefs.edit().putInt("tuned", v).apply() }

    var practiceSeconds: Int
        get() = prefs.getInt("practiceSeconds", 0)
        set(v) { prefs.edit().putInt("practiceSeconds", v).apply() }

    fun addPractice(seconds: Int) { if (seconds > 0) practiceSeconds += seconds }

    fun reset() = prefs.edit().clear().apply()
}
