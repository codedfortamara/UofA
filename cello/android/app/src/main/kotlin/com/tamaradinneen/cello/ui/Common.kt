package com.tamaradinneen.cello.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun SectionCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(2.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        border = BorderStroke(1.dp, Brand.Rule),
    ) { Column(Modifier.padding(14.dp), content = content) }
}

/** The dark panel the tuner and the listening steps sit on. */
@Composable
fun Stage(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier
            .fillMaxWidth()
            .background(Brand.Prussian, RoundedCornerShape(3.dp))
            .padding(14.dp),
        content = content,
    )
}

@Composable
fun CapsLabel(text: String, color: Color = Brand.GoldDeep, modifier: Modifier = Modifier) {
    Text(text.uppercase(), style = Caps, color = color, modifier = modifier)
}

/**
 * A note with a coloured rule down its left edge, used for tips and feedback.
 * IntrinsicSize.Min lets the rule match the text height exactly.
 */
@Composable
fun RuledNote(text: String, accent: Color, measure: String? = null, background: Color = Color.White) {
    Row(
        Modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Min)
            .background(background)
    ) {
        Box(
            Modifier
                .width(3.dp)
                .fillMaxHeight()
                .background(accent)
        )
        Column(Modifier.padding(start = 10.dp, top = 9.dp, bottom = 9.dp, end = 10.dp)) {
            Text(text, fontSize = 15.sp, color = Brand.Charcoal, lineHeight = 21.sp)
            if (measure != null) {
                Text(
                    measure.uppercase(), style = Caps, color = Brand.CharcoalSoft,
                    modifier = Modifier.padding(top = 6.dp)
                )
            }
        }
    }
}

@Composable
fun ProgressRail(fraction: Float, modifier: Modifier = Modifier) {
    Box(
        modifier
            .fillMaxWidth()
            .height(3.dp)
            .background(Brand.Rule)
    ) {
        Box(
            Modifier
                .fillMaxWidth(fraction.coerceIn(0f, 1f))
                .height(3.dp)
                .background(Brand.GoldDeep)
        )
    }
}

@Composable
fun Pip(hit: Boolean, miss: Boolean) {
    Box(
        Modifier
            .size(11.dp)
            .background(
                when {
                    hit -> Brand.Good
                    miss -> Brand.Rule
                    else -> Color.White
                },
                CircleShape
            )
    )
}

@Composable
fun Heading(text: String, modifier: Modifier = Modifier) {
    Text(
        text, fontSize = 19.sp, fontWeight = FontWeight.SemiBold, color = Brand.Charcoal,
        lineHeight = 25.sp, modifier = modifier
    )
}

@Composable
fun Body(text: String, modifier: Modifier = Modifier, color: Color = Brand.Charcoal) {
    Text(text, fontSize = 15.sp, color = color, lineHeight = 22.sp, modifier = modifier)
}

@Composable
fun CentreRow(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { content() }
}
