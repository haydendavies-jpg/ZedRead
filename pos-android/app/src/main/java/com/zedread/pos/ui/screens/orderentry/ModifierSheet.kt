package com.zedread.pos.ui.screens.orderentry

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.zedread.pos.data.local.entity.ProductEntity
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.theme.ZedReadColors
import com.zedread.pos.ui.theme.parseHexColor
import com.zedread.pos.ui.viewmodel.LinkedGroupSelection
import com.zedread.pos.ui.viewmodel.ModifierGroupSelection
import com.zedread.pos.ui.viewmodel.ModifierPathStep
import com.zedread.pos.ui.viewmodel.ModifierSheetState

/**
 * Modifier customise sheet — a centered floating box over a dimming overlay
 * (matching PaymentModal's own layout, per user-testing feedback that a
 * right-hand slide-over read as visually inconsistent with the payment
 * modal it sits alongside — the design_handoff_zedread README's original
 * right-hand-slide-over spec is superseded by this on that one point).
 * Header with the product's category colour/name/base price, one block per
 * modifier group (uppercase name + a "Choose 1"/"Optional" rule chip,
 * radio-style single-select vs checkbox-style multi-select rows, a
 * `+$X.XX` price when an option costs extra), each selected option's
 * "comboed" linked groups nested inline directly beneath it (one level
 * deep — see ModifierGroupSelection's doc), a qty stepper, and a
 * live-updating "Add to order $total" footer button.
 *
 * Rendered as an overlay on the Register screen itself (not a nav
 * destination) — see SellViewModel's class doc for why.
 */
@Composable
fun ModifierSheetOverlay(
    state: ModifierSheetState,
    onDismiss: () -> Unit,
    onToggleChoice: (groupIndex: Int, optionIndex: Int) -> Unit,
    onToggleNested: (groupIndex: Int, path: List<ModifierPathStep>, optionIndex: Int) -> Unit,
    onQtyDec: () -> Unit,
    onQtyInc: () -> Unit,
    onConfirm: () -> Unit,
    totalPriceCents: (ModifierSheetState.Ready) -> Long,
) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.5f))
            .imePadding()
            .clickable(onClick = onDismiss),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = 480.dp)
                .fillMaxWidth(0.9f)
                .fillMaxHeight(0.85f)
                .clip(RoundedCornerShape(18.dp))
                // Swallow taps inside the panel so they don't fall through to the
                // scrim's dismiss-on-click behind it.
                .clickable(enabled = false) {}
                .background(colors.surface),
        ) {
            when (state) {
                is ModifierSheetState.Loading -> {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
                is ModifierSheetState.Error -> {
                    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
                        Text(state.message, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center)
                    }
                }
                is ModifierSheetState.Ready -> {
                    Column(modifier = Modifier.fillMaxSize()) {
                        ModifierSheetHeader(product = state.product, onClose = onDismiss)
                        LazyColumn(
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                            contentPadding = PaddingValues(horizontal = 22.dp, vertical = 18.dp),
                            verticalArrangement = Arrangement.spacedBy(22.dp),
                        ) {
                            itemsIndexed(state.groups) { groupIndex, gs: ModifierGroupSelection ->
                                ModifierGroupBlock(
                                    groupIndex = groupIndex,
                                    gs = gs,
                                    onToggleChoice = onToggleChoice,
                                    onToggleNested = onToggleNested,
                                )
                            }
                        }
                        ModifierSheetFooter(
                            quantity = state.quantity,
                            totalCents = totalPriceCents(state),
                            onQtyDec = onQtyDec,
                            onQtyInc = onQtyInc,
                            onConfirm = onConfirm,
                        )
                    }
                }
                ModifierSheetState.Closed -> Unit
            }
        }
    }
}

@Composable
private fun ModifierSheetHeader(product: ProductEntity, onClose: () -> Unit) {
    val colors = LocalZedReadColors.current
    Column {
        Row(
            modifier = Modifier.fillMaxWidth().padding(20.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(44.dp)
                    .clip(RoundedCornerShape(11.dp))
                    .background(parseHexColor(product.categoryColor)),
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    product.name,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleLarge,
                    color = colors.text,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    "${formatCents(product.basePriceCents)} · Customise",
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.faint,
                )
            }
            Box(
                modifier = Modifier
                    .size(34.dp)
                    .clip(RoundedCornerShape(9.dp))
                    .clickable(onClick = onClose),
                contentAlignment = Alignment.Center,
            ) {
                Text("✕", color = colors.muted, style = MaterialTheme.typography.titleMedium)
            }
        }
        HorizontalDivider(color = colors.border)
    }
}

@Composable
private fun ModifierGroupBlock(
    groupIndex: Int,
    gs: ModifierGroupSelection,
    onToggleChoice: (Int, Int) -> Unit,
    onToggleNested: (groupIndex: Int, path: List<ModifierPathStep>, optionIndex: Int) -> Unit,
) {
    val colors = LocalZedReadColors.current
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                gs.group.name.uppercase(),
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = colors.text,
            )
            RuleChip(gs.isSingleSelect, gs.isRequired, gs.group.minSelections, gs.group.maxSelections, colors)
        }
        Spacer(Modifier.height(11.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            gs.group.options.forEachIndexed { optionIndex, option ->
                val selected = gs.selected.contains(optionIndex)
                ModifierChoiceRow(
                    label = option.name,
                    priceDeltaCents = option.priceDeltaCents,
                    selected = selected,
                    isSingleSelect = gs.isSingleSelect,
                    onClick = { onToggleChoice(groupIndex, optionIndex) },
                )
                // Comboed groups nest directly beneath their owning option, only
                // while it's selected — the inline-nested-cascade pattern the
                // portal's own Modifiers page uses for the same "option 1" design.
                // LinkedGroupBlock itself recurses further for a linked group
                // whose own selected option carries yet another link — no fixed
                // chain-depth limit, unlike the version this replaces.
                if (selected) {
                    gs.linkedSelections[optionIndex]?.forEachIndexed { linkedGroupIndex, linked ->
                        LinkedGroupBlock(
                            linked = linked,
                            path = listOf(ModifierPathStep(optionIndex, linkedGroupIndex)),
                            onToggle = { path, targetOptionIndex -> onToggleNested(groupIndex, path, targetOptionIndex) },
                            modifier = Modifier.padding(start = 18.dp, top = 2.dp),
                        )
                    }
                }
            }
        }
    }
}

/**
 * One linked ("combo") group's card, recursing into a further nested
 * [LinkedGroupBlock] for any of its own options that are selected AND
 * themselves carry further linked groups. [path] is this block's own
 * address from the top-level group (see [ModifierPathStep]'s doc) — passed
 * to [onToggle] verbatim when toggling one of THIS group's own options, and
 * extended by one more step when recursing into a child.
 */
@Composable
private fun LinkedGroupBlock(
    linked: LinkedGroupSelection,
    path: List<ModifierPathStep>,
    onToggle: (path: List<ModifierPathStep>, optionIndex: Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalZedReadColors.current
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.surface2)
            .padding(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                linked.group.name.uppercase(),
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = colors.text,
            )
            RuleChip(linked.isSingleSelect, linked.isRequired, linked.group.minSelections, linked.group.maxSelections, colors)
        }
        Spacer(Modifier.height(8.dp))
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            linked.group.options.forEachIndexed { optionIndex, option ->
                val optionSelected = linked.selected.contains(optionIndex)
                ModifierChoiceRow(
                    label = option.name,
                    priceDeltaCents = option.priceDeltaCents,
                    selected = optionSelected,
                    isSingleSelect = linked.isSingleSelect,
                    onClick = { onToggle(path, optionIndex) },
                )
                if (optionSelected) {
                    linked.linkedSelections[optionIndex]?.forEachIndexed { nestedGroupIndex, nested ->
                        LinkedGroupBlock(
                            linked = nested,
                            path = path + ModifierPathStep(optionIndex, nestedGroupIndex),
                            onToggle = onToggle,
                            modifier = Modifier.padding(start = 14.dp, top = 2.dp),
                        )
                    }
                }
            }
        }
    }
}

/** Shared by both top-level ModifierGroupBlock and nested LinkedGroupBlock — takes primitives, not one shared type. */
@Composable
private fun RuleChip(isSingleSelect: Boolean, isRequired: Boolean, minSelections: Int, maxSelections: Int, colors: ZedReadColors) {
    val label = if (isSingleSelect) {
        if (isRequired) "Choose 1" else "Optional"
    } else {
        if (isRequired) "Choose $minSelections-$maxSelections" else "Optional"
    }
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(if (isRequired) colors.accentSoft else colors.surface2)
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Text(
            label.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = if (isRequired) colors.accent else colors.faint,
        )
    }
}

@Composable
private fun ModifierChoiceRow(
    label: String,
    priceDeltaCents: Long,
    selected: Boolean,
    isSingleSelect: Boolean,
    onClick: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    val markShape = if (isSingleSelect) CircleShape else RoundedCornerShape(6.dp)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(if (selected) colors.accentSoft else colors.surface)
            .border(
                width = 1.5.dp,
                color = if (selected) colors.accent else colors.inputBorder,
                shape = RoundedCornerShape(10.dp),
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 13.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(20.dp)
                .clip(markShape)
                .background(if (selected) colors.accent else Color.Transparent)
                .border(
                    width = 1.5.dp,
                    color = if (selected) colors.accent else colors.inputBorder,
                    shape = markShape,
                ),
            contentAlignment = Alignment.Center,
        ) {
            if (selected) {
                Text(
                    if (isSingleSelect) "●" else "✓",
                    color = Color.White,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
        Text(
            label,
            color = colors.text,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
        if (priceDeltaCents > 0) {
            Text(
                "+${formatCents(priceDeltaCents)}",
                color = colors.muted,
                style = MaterialTheme.typography.labelMedium,
            )
        }
    }
}

@Composable
private fun ModifierSheetFooter(
    quantity: Int,
    totalCents: Long,
    onQtyDec: () -> Unit,
    onQtyInc: () -> Unit,
    onConfirm: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    Column {
        HorizontalDivider(color = colors.border)
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                modifier = Modifier
                    .clip(RoundedCornerShape(10.dp))
                    .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(10.dp))
                    .background(colors.bg),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                QtyStepperButton("−", onQtyDec, colors)
                Text(
                    "$quantity",
                    modifier = Modifier.width(34.dp),
                    textAlign = TextAlign.Center,
                    color = colors.text,
                    fontWeight = FontWeight.SemiBold,
                )
                QtyStepperButton("+", onQtyInc, colors)
            }
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(52.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(colors.accent)
                    .clickable(onClick = onConfirm),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    "Add to order  ${formatCents(totalCents)}",
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun QtyStepperButton(symbol: String, onClick: () -> Unit, colors: ZedReadColors) {
    Box(
        modifier = Modifier
            .width(40.dp)
            .height(44.dp)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(symbol, color = colors.muted, style = MaterialTheme.typography.titleMedium)
    }
}

private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
