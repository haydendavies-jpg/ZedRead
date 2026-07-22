package com.zedread.pos.ui.screens.tables

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.api.PosDiningTableStatusDto
import com.zedread.pos.data.api.PosTableMapDetailDto
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.theme.parseHexColor
import com.zedread.pos.ui.theme.tableStatusStyle
import com.zedread.pos.ui.viewmodel.TablesViewModel
import kotlinx.coroutines.delay
import java.time.Duration
import java.time.Instant

/**
 * Tables / Floor Map screen (Android POS Phase 4) — exact-match layout to
 * `design_handoff_zedread/README-tables-floormap.md`'s "Tables / Floor Map"
 * section: a header with floor tabs + status legend, an absolutely
 * positioned map canvas of zone backdrops and table tiles, and a bottom
 * selection bar for the tapped table. State/behavior all live in
 * [TablesViewModel] (already built) — this file is presentation only.
 *
 * **"Seat table →" vs "Open order →" (this screen's own product judgement
 * call, not the design bundle's)**: the mockup's selection bar always shows
 * one "Open order →" action, but on the real backend an invoice can only
 * attach to a table via an existing [com.zedread.pos.data.api.TableSessionDto]
 * (`InvoiceCreateBody.tableSessionId`), and an *open* table has no session
 * yet. So the primary action here is context-sensitive: an open table (no
 * `sessionId`) shows "Seat table →", opening [SeatCoversDialog] and calling
 * [TablesViewModel.startSeating]/[TablesViewModel.confirmSeating] (already
 * built for exactly this); a seated/ordered/bill table shows "Open order →",
 * which navigates to the Register screen passing its `sessionId` as
 * `tableSessionId` (wired in `PosNavHost`).
 *
 * **Capacity gap**: [PosDiningTableStatusDto] carries `covers` (current
 * occupancy) but no seat-capacity field, so the mockup's "2/4" covers/seats
 * line and an open table's "Seats" chip can't be reproduced from real data.
 * Occupied tiles/chips show "<covers> guests" instead, and open tables just
 * omit that line — a real, flagged gap, not a fabricated number (mirrors
 * [TablesViewModel]'s own documented "Total" chip omission).
 *
 * **Poll interval**: 8 seconds. Frequent enough that another terminal
 * seating/clearing/merging a table shows up on this live floor view
 * promptly, without hammering `GET /pos/table-map`; [TablesViewModel.refresh]
 * is silent-on-failure after its first successful load, so a single missed
 * poll never blanks an already-rendered map.
 */
@Composable
fun TablesScreen(
    onOpenOrder: (tableSessionId: String) -> Unit,
    viewModel: TablesViewModel = hiltViewModel(),
) {
    val colors = LocalZedReadColors.current
    val floors by viewModel.floors.collectAsState()
    val activeFloorId by viewModel.activeFloorId.collectAsState()
    val selectedShapeId by viewModel.selectedShapeId.collectAsState()
    val mergeAnchorShapeId by viewModel.mergeAnchorShapeId.collectAsState()
    val toast by viewModel.toast.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()
    val error by viewModel.error.collectAsState()
    val seatDialogShapeId by viewModel.seatDialogShapeId.collectAsState()
    val isActionInFlight by viewModel.isActionInFlight.collectAsState()

    // Poll while this screen is on-screen; the loop (and its delay) is
    // cancelled automatically the moment TablesScreen leaves composition.
    LaunchedEffect(Unit) {
        while (true) {
            viewModel.refresh()
            delay(8_000)
        }
    }

    LaunchedEffect(toast) {
        if (toast != null) {
            delay(1600)
            viewModel.clearToast()
        }
    }

    val activeFloor = floors.firstOrNull { it.id == activeFloorId }
    val selectedShape = viewModel.findShape(selectedShapeId)

    Column(modifier = Modifier.fillMaxSize().background(colors.bg)) {
        TablesHeader(floors = floors, activeFloorId = activeFloorId, onSelectFloor = viewModel::selectFloor)

        Box(modifier = Modifier.fillMaxSize()) {
            when {
                isLoading && floors.isEmpty() ->
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                error != null && floors.isEmpty() ->
                    Text(
                        error ?: "Failed to load table map",
                        color = colors.accent,
                        modifier = Modifier.align(Alignment.Center).padding(24.dp),
                    )
                else ->
                    FloorMapCanvas(
                        floor = activeFloor,
                        mergeAnchorShapeId = mergeAnchorShapeId,
                        onTapTile = viewModel::tapTile,
                        modifier = Modifier
                            .fillMaxSize()
                            .verticalScroll(rememberScrollState())
                            .padding(24.dp),
                    )
            }

            if (selectedShape != null) {
                SelectionBar(
                    shape = selectedShape,
                    label = viewModel.tableDisplayLabel(selectedShape),
                    isMergeArmed = mergeAnchorShapeId == selectedShape.id,
                    isActionInFlight = isActionInFlight,
                    onMergeToggle = viewModel::toggleMergeArm,
                    onSeatTable = { viewModel.startSeating(selectedShape.id) },
                    onOpenOrder = onOpenOrder,
                    onClose = viewModel::clearSelection,
                    modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 22.dp),
                )
            }

            if (toast != null) {
                ToastBubble(
                    text = toast ?: "",
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = if (selectedShape != null) 116.dp else 22.dp),
                )
            }
        }
    }

    if (seatDialogShapeId != null) {
        SeatCoversDialog(onDismiss = viewModel::cancelSeating, onConfirm = viewModel::confirmSeating)
    }
}

@Composable
private fun TablesHeader(
    floors: List<PosTableMapDetailDto>,
    activeFloorId: String?,
    onSelectFloor: (String) -> Unit,
) {
    val colors = LocalZedReadColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.surface)
            .border(width = 1.dp, color = colors.border)
            .padding(horizontal = 24.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Text("Table Map", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge, color = colors.text)
            Text("FRONT OF HOUSE · LIVE", style = MaterialTheme.typography.labelSmall, color = colors.faint)
        }

        Row(
            modifier = Modifier.padding(start = 22.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            floors.sortedBy { it.sortOrder }.forEach { floor ->
                val active = floor.id == activeFloorId
                Text(
                    floor.name,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 12.5.sp,
                    color = if (active) colors.surface else colors.muted,
                    modifier = Modifier
                        .clip(RoundedCornerShape(9.dp))
                        .background(if (active) colors.text else Color.Transparent)
                        .border(
                            width = 1.5.dp,
                            color = if (active) colors.text else colors.inputBorder,
                            shape = RoundedCornerShape(9.dp),
                        )
                        .clickable { onSelectFloor(floor.id) }
                        .padding(horizontal = 15.dp, vertical = 7.dp),
                )
            }
        }

        Spacer(Modifier.weight(1f))
        TablesLegend()
    }
}

@Composable
private fun TablesLegend() {
    val seated = tableStatusStyle("seated")
    val ordered = tableStatusStyle("ordered")
    val bill = tableStatusStyle("bill")
    val open = tableStatusStyle(null)
    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        LegendItem("Open", open.fill, open.accent)
        LegendItem("Seated", seated.accent, seated.accent)
        LegendItem("Ordered", ordered.accent, ordered.accent)
        LegendItem("Needs bill", bill.accent, bill.accent)
    }
}

@Composable
private fun LegendItem(label: String, swatch: Color, border: Color) {
    val colors = LocalZedReadColors.current
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(
            modifier = Modifier
                .size(12.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(swatch)
                .border(width = 1.dp, color = border, shape = RoundedCornerShape(4.dp)),
        )
        Text(label, style = MaterialTheme.typography.labelMedium, color = colors.muted)
    }
}

/** Decorative (non-table) shape kinds — rendered as zone backdrops, never tappable. */
private val DECORATIVE_KINDS = setOf("zone", "bar_counter", "entrance", "wall")

@Composable
private fun FloorMapCanvas(
    floor: PosTableMapDetailDto?,
    mergeAnchorShapeId: String?,
    onTapTile: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalZedReadColors.current
    Box(modifier = modifier, contentAlignment = Alignment.TopCenter) {
        BoxWithConstraints(
            modifier = Modifier
                .widthIn(max = 1220.dp)
                .fillMaxWidth()
                .aspectRatio(16f / 10f)
                .clip(RoundedCornerShape(22.dp))
                .background(colors.surface)
                .border(width = 2.dp, color = colors.border, shape = RoundedCornerShape(22.dp)),
        ) {
            val stageWidth = maxWidth
            val stageHeight = maxHeight
            // Reference stage width the design's fixed pixel tile sizes assume
            // (README's "max-width:1220px" stage) — table tiles below scale off
            // the ratio between the actually-measured stage and this reference.
            val scale = (stageWidth / 1220.dp).coerceIn(0.55f, 1.2f)

            val shapes = floor?.shapes.orEmpty()

            shapes.filter { it.kind in DECORATIVE_KINDS }.forEach { shape ->
                ZoneBackdrop(shape = shape, stageWidth = stageWidth, stageHeight = stageHeight)
            }

            shapes.filterNot { it.kind in DECORATIVE_KINDS }.forEach { shape ->
                TableTile(
                    shape = shape,
                    scale = scale,
                    isMergeAnchor = shape.id == mergeAnchorShapeId,
                    stageWidth = stageWidth,
                    stageHeight = stageHeight,
                    onTap = { onTapTile(shape.id) },
                )
            }
        }
    }
}

@Composable
private fun ZoneBackdrop(shape: PosDiningTableStatusDto, stageWidth: Dp, stageHeight: Dp) {
    val colors = LocalZedReadColors.current
    val left = stageWidth * (shape.x / 100f).toFloat()
    val top = stageHeight * (shape.y / 100f).toFloat()
    val width = stageWidth * (shape.w / 100f).toFloat()
    val height = stageHeight * (shape.h / 100f).toFloat()
    val tint = shape.color?.let { parseHexColor(it).copy(alpha = 0.10f) } ?: colors.surface2

    Box(
        modifier = Modifier
            .offset(x = left, y = top)
            .size(width = width, height = height)
            .clip(RoundedCornerShape(16.dp))
            .background(tint)
            .then(
                if (shape.dashed) {
                    Modifier.dashedBorder(color = colors.text.copy(alpha = 0.18f))
                } else {
                    Modifier.border(width = 1.5.dp, color = colors.border, shape = RoundedCornerShape(16.dp))
                },
            ),
    ) {
        Text(
            shape.label.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = colors.faint,
            modifier = Modifier.align(Alignment.TopStart).padding(10.dp),
        )
    }
}

/** Dashed rounded-rect border for outdoor zones (README: `2px dashed rgba(36,31,26,.18)`). */
private fun Modifier.dashedBorder(color: Color, strokeWidth: Dp = 2.dp, cornerRadius: Dp = 16.dp): Modifier =
    this.drawWithContent {
        drawContent()
        drawRoundRect(
            color = color,
            style = Stroke(width = strokeWidth.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 6f), 0f)),
            cornerRadius = CornerRadius(cornerRadius.toPx()),
        )
    }

@Composable
private fun TableTile(
    shape: PosDiningTableStatusDto,
    scale: Float,
    isMergeAnchor: Boolean,
    stageWidth: Dp,
    stageHeight: Dp,
    onTap: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    val style = tableStatusStyle(shape.status)
    val isOpen = shape.status == null

    val isCircle = shape.kind == "stool" || shape.kind == "round"
    val (baseW, baseH) = when (shape.kind) {
        "stool" -> 58.dp to 58.dp
        "round" -> 92.dp to 92.dp
        else -> 154.dp to 94.dp // "rect"
    }
    val w = baseW * scale
    val h = baseH * scale
    val cx = stageWidth * (shape.x / 100f).toFloat()
    val cy = stageHeight * (shape.y / 100f).toFloat()
    val tileShape = if (isCircle) CircleShape else RoundedCornerShape(18.dp)

    val fill = if (isOpen) colors.surface else style.fill
    val borderColor = when {
        isMergeAnchor -> Color(0xFFA82040)
        isOpen -> colors.inputBorder
        else -> style.border
    }

    Box(
        modifier = Modifier
            .offset(x = cx - w / 2, y = cy - h / 2)
            .size(width = w, height = h)
            .shadow(elevation = 3.dp, shape = tileShape)
            .clip(tileShape)
            .background(fill)
            .border(width = if (isMergeAnchor) 3.dp else 2.5.dp, color = borderColor, shape = tileShape)
            .clickable(onClick = onTap),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(shape.label, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold, fontSize = (15 * scale).sp, color = colors.text)
            Text(
                if (isOpen) "Open" else "${shape.covers ?: 0} guests",
                fontWeight = FontWeight.SemiBold,
                fontSize = 10.sp,
                color = colors.muted,
            )
            if (!isOpen) {
                shape.seatedAt?.let { seatedAt ->
                    Text(
                        elapsedLabel(seatedAt) ?: "",
                        fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 9.sp,
                        color = colors.muted.copy(alpha = 0.85f),
                    )
                }
            }
        }

        // Reservation badge (open tables with a booking) — top-left.
        if (isOpen && shape.reservationLabel != null) {
            Box(
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .offset(x = (-9).dp, y = (-9).dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(colors.surface2)
                    .border(width = 1.5.dp, color = colors.inputBorder, shape = RoundedCornerShape(8.dp))
                    .padding(horizontal = 5.dp, vertical = 2.dp),
            ) {
                Text("◷ ${shape.reservationLabel}", fontSize = 8.5.sp, fontWeight = FontWeight.Bold, color = colors.text)
            }
        }

        // Merge badge (bottom-center) — this table is merged with a partner session.
        if (shape.mergePartnerLabel != null) {
            Box(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .offset(y = 9.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(colors.text)
                    .padding(horizontal = 5.dp, vertical = 2.dp),
            ) {
                Text("⛓ ${shape.mergePartnerLabel}", fontSize = 8.5.sp, fontWeight = FontWeight.Bold, color = colors.surface)
            }
        }
    }
}

@Composable
private fun SelectionBar(
    shape: PosDiningTableStatusDto,
    label: String,
    isMergeArmed: Boolean,
    isActionInFlight: Boolean,
    onMergeToggle: () -> Unit,
    onSeatTable: () -> Unit,
    onOpenOrder: (String) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalZedReadColors.current
    val style = tableStatusStyle(shape.status)
    val isOpen = shape.status == null
    val statusLabel = when (shape.status) {
        "seated" -> "SEATED"
        "ordered" -> "ORDERED"
        "bill" -> "NEEDS BILL"
        else -> "OPEN"
    }

    Row(
        modifier = modifier
            .widthIn(max = 1000.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(colors.text)
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Column {
            Text(label, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = colors.surface)
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(6.dp))
                    .background(style.accent)
                    .padding(horizontal = 7.dp, vertical = 2.dp),
            ) {
                Text(statusLabel, fontSize = 8.5.sp, fontWeight = FontWeight.Bold, color = Color.White)
            }
        }

        Box(Modifier.width(1.dp).height(36.dp).background(Color.White.copy(alpha = 0.16f)))

        if (!isOpen) {
            DetailChip("GUESTS", "${shape.covers ?: 0}")
            shape.seatedAt?.let { DetailChip("SEATED", elapsedLabel(it) ?: "—") }
            shape.lastTouchAt?.let { lastTouchAt ->
                val minutes = elapsedMinutes(lastTouchAt)
                DetailChip(
                    "LAST TOUCH",
                    minutes?.let { "${it}m" } ?: "—",
                    valueColor = if ((minutes ?: 0) >= 15) Color(0xFFF4A98C) else Color.White,
                )
            }
            shape.serverName?.let { DetailChip("SERVER", it) }
        } else {
            DetailChip("SEATS", "Open")
            shape.reservationLabel?.let { DetailChip("RESERVED", it, valueColor = Color(0xFFE9C46A)) }
        }

        Spacer(Modifier.weight(1f))

        // Merge only makes sense for a table with an open session — an open
        // table has nothing to merge, so the button is hidden rather than
        // shown-and-failing (see TablesViewModel's own doc on this).
        if (!isOpen && shape.sessionId != null) {
            OutlinedButton(
                onClick = onMergeToggle,
                enabled = !isActionInFlight,
                border = BorderStroke(1.5.dp, Color.White.copy(alpha = 0.28f)),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White),
            ) {
                Text(if (isMergeArmed) "Cancel merge" else "⛓ Merge", fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold)
            }
        }

        if (isOpen) {
            Button(
                onClick = onSeatTable,
                enabled = !isActionInFlight,
                colors = ButtonDefaults.buttonColors(containerColor = colors.accent, contentColor = Color.White),
                shape = RoundedCornerShape(9.dp),
            ) {
                Text("Seat table →", fontWeight = FontWeight.SemiBold, fontSize = 12.5.sp)
            }
        } else {
            Button(
                onClick = { shape.sessionId?.let(onOpenOrder) },
                enabled = !isActionInFlight && shape.sessionId != null,
                colors = ButtonDefaults.buttonColors(containerColor = colors.accent, contentColor = Color.White),
                shape = RoundedCornerShape(9.dp),
            ) {
                Text("Open order →", fontWeight = FontWeight.SemiBold, fontSize = 12.5.sp)
            }
        }

        IconButton(onClick = onClose) {
            Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
        }
    }
}

@Composable
private fun DetailChip(key: String, value: String, valueColor: Color = Color.White) {
    Column {
        Text(key, fontSize = 8.sp, fontWeight = FontWeight.SemiBold, color = Color.White.copy(alpha = 0.5f), letterSpacing = 0.5.sp)
        Text(value, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = valueColor)
    }
}

@Composable
private fun ToastBubble(text: String, modifier: Modifier = Modifier) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(colors.text)
            .padding(horizontal = 16.dp, vertical = 10.dp),
    ) {
        Text(text, color = colors.surface, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold)
    }
}

/** Covers-entry dialog for seating an open table — see the file doc's "Seat table →" note. */
@Composable
private fun SeatCoversDialog(onDismiss: () -> Unit, onConfirm: (Int) -> Unit) {
    var covers by remember { mutableStateOf(2) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Seat table") },
        text = {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                IconButton(onClick = { covers = (covers - 1).coerceAtLeast(1) }) {
                    Text("−", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                }
                Text("$covers guests", fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                IconButton(onClick = { covers = (covers + 1).coerceAtMost(20) }) {
                    Text("+", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                }
            }
        },
        confirmButton = { TextButton(onClick = { onConfirm(covers) }) { Text("Seat") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/** Minutes elapsed since [isoTimestamp] (an ISO-8601 instant), or null if unparsable. */
private fun elapsedMinutes(isoTimestamp: String): Long? = runCatching {
    Duration.between(Instant.parse(isoTimestamp), Instant.now()).toMinutes().coerceAtLeast(0)
}.getOrNull()

/** "<n>m"-formatted elapsed time since [isoTimestamp], or null if unparsable. */
private fun elapsedLabel(isoTimestamp: String): String? = elapsedMinutes(isoTimestamp)?.let { "${it}m" }
