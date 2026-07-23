package com.zedread.pos.ui.screens.orderentry

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items as columnItems
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.zedread.pos.data.api.PosMenuButtonDto
import com.zedread.pos.data.api.PosMenuLayoutDto
import com.zedread.pos.data.api.PosMenuTabDto
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.theme.SoldOutTileColor
import com.zedread.pos.ui.theme.contrastTextColor
import com.zedread.pos.ui.theme.parseHexColor

/**
 * Rail of a menu layout's top-level tabs — the Menu Studio grid render's
 * equivalent of [CategoryRail] when a menu layout (not the category
 * fallback) is driving the grid. Solid tab.colour-filled blocks, flush
 * edge-to-edge, matching the portal's own "POS Layout tab rail style
 * redesign" (a colour dot on a neutral row read as under-designed; a solid
 * fill block reads as an actual POS button).
 */
@Composable
fun MenuTabRail(
    layout: PosMenuLayoutDto,
    effectiveTabId: String?,
    onSelectTab: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalZedReadColors.current
    LazyColumn(modifier = modifier.width(200.dp).background(colors.surface)) {
        columnItems(layout.topLevelTabs) { tab ->
            val isActive = tab.id == effectiveTabId
            val fill = tab.color?.let { parseHexColor(it) } ?: colors.accent
            val textColor = contrastTextColor(tab.color ?: "#554C44")
            val ringColor = if (isSystemInDarkTheme()) Color.White else Color.Black
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(fill)
                    .then(
                        if (isActive) Modifier.border(BorderStroke(2.dp, ringColor)) else Modifier,
                    )
                    .clickable { onSelectTab(tab.id) }
                    .padding(horizontal = 16.dp, vertical = 14.dp),
            ) {
                Column {
                    Text(tab.name, color = textColor, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium, maxLines = 1)
                    Text(
                        "${tab.buttons.size} item${if (tab.buttons.size == 1) "" else "s"}",
                        color = textColor.copy(alpha = 0.75f),
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        }
    }
}

/**
 * Breadcrumb shown above the tile grid when a folder tile has been drilled
 * into — walks [PosMenuTabDto.parentTabId] back to the rail's top-level tab
 * so staff can jump back up without repeatedly tapping the folder's own
 * implicit "back". Rendered only for a nested (non-top-level) tab; hidden
 * for a rail-level tab, where the rail selection itself is the navigation.
 */
@Composable
fun MenuBreadcrumb(layout: PosMenuLayoutDto, tabId: String?, onSelectTab: (String) -> Unit) {
    val colors = LocalZedReadColors.current
    val chain = remember(layout, tabId) { buildBreadcrumbChain(layout, tabId) }
    if (chain.size <= 1) return
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        chain.forEachIndexed { index, tab ->
            if (index > 0) Text(" / ", color = colors.faint, style = MaterialTheme.typography.labelMedium)
            val isLast = index == chain.lastIndex
            Text(
                tab.name,
                color = if (isLast) colors.text else colors.muted,
                fontWeight = if (isLast) FontWeight.Bold else FontWeight.Normal,
                style = MaterialTheme.typography.labelMedium,
                modifier = if (isLast) Modifier else Modifier.clickable { onSelectTab(tab.id) },
            )
        }
    }
}

private fun buildBreadcrumbChain(layout: PosMenuLayoutDto, tabId: String?): List<PosMenuTabDto> {
    val byId = layout.tabs.associateBy { it.id }
    val chain = mutableListOf<PosMenuTabDto>()
    var current = tabId?.let { byId[it] }
    while (current != null) {
        chain.add(0, current)
        current = current.parentTabId?.let { byId[it] }
    }
    return chain
}

/**
 * The dense 6-column tile grid for one tab — [packMenuButtons] resolves
 * every button to a concrete cell, then each is placed by absolute offset
 * inside a fixed-size canvas sized from the available width (so a 1x1 tile
 * is a perfect square regardless of screen size, per user-testing feedback
 * that tiles previously read as non-square).
 */
@Composable
fun MenuTileGrid(
    layout: PosMenuLayoutDto,
    tabId: String?,
    onProductTap: (productRef: String) -> Unit,
    onProductLongPress: (productRef: String) -> Unit,
    onFolderTap: (childTabId: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LocalZedReadColors.current
    val tab = layout.tabs.firstOrNull { it.id == tabId }
    if (tab == null || tab.buttons.isEmpty()) {
        Box(modifier.fillMaxSize().background(colors.bg), contentAlignment = Alignment.Center) {
            Text("No items in this menu.", color = colors.muted)
        }
        return
    }

    val placed = remember(tab.id, tab.buttons) { packMenuButtons(tab.buttons) }
    val rows = totalRows(placed)

    BoxWithConstraints(
        modifier = modifier
            .fillMaxSize()
            .background(colors.bg)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        val cellSize = maxWidth / MENU_GRID_COLUMNS
        Box(modifier = Modifier.fillMaxWidth().height(cellSize * rows)) {
            placed.forEach { p ->
                Box(
                    modifier = Modifier
                        .offset(x = cellSize * p.col, y = cellSize * p.row)
                        .size(width = cellSize * p.button.width, height = cellSize * p.button.height)
                        .padding(6.dp),
                ) {
                    MenuTile(
                        button = p.button,
                        onProductTap = onProductTap,
                        onProductLongPress = onProductLongPress,
                        onFolderTap = onFolderTap,
                    )
                }
            }
        }
    }
}

@Composable
private fun MenuTile(
    button: PosMenuButtonDto,
    onProductTap: (String) -> Unit,
    onProductLongPress: (String) -> Unit,
    onFolderTap: (String) -> Unit,
) {
    if (button.kind == "folder") {
        FolderTile(button = button, onClick = { button.childTabId?.let(onFolderTap) })
    } else {
        ProductMenuTile(
            button = button,
            onClick = { button.productRef?.let(onProductTap) },
            onLongPress = { button.productRef?.let(onProductLongPress) },
        )
    }
}

/**
 * A folder tile — same corner-badge language as a product tile's "+"
 * (small translucent circle, top-right corner) instead of a large inline
 * "📁" glyph competing with the tab name for space, per user-testing
 * feedback asking for folders to read as "more in the style of the little +
 * for modifiers".
 */
@Composable
private fun FolderTile(button: PosMenuButtonDto, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    val fill = button.color?.let { parseHexColor(it) } ?: colors.surface2
    val textColor = contrastTextColor(button.color ?: "#F0ECE3")
    Box(
        modifier = Modifier
            .fillMaxSize()
            .clip(RoundedCornerShape(14.dp))
            .background(fill)
            .clickable(onClick = onClick),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                button.childTabName ?: "Folder",
                modifier = Modifier.padding(end = 28.dp),
                color = textColor,
                fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.titleSmall,
                maxLines = 2,
            )
            Text(
                "${button.childTabButtonCount ?: 0} item${if (button.childTabButtonCount == 1) "" else "s"}",
                color = textColor.copy(alpha = 0.75f),
                style = MaterialTheme.typography.labelSmall,
            )
        }
        Box(
            modifier = Modifier
                .padding(8.dp)
                .align(Alignment.TopEnd)
                .size(22.dp)
                .clip(CircleShape)
                .background(Color.Black.copy(alpha = 0.18f)),
            contentAlignment = Alignment.Center,
        ) {
            Text("›", color = textColor, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelMedium)
        }
    }
}

/**
 * A product tile — same visual language as [ProductTile] in the
 * category-based grid (bold small name, plain-body price font — the
 * mockup's own bolder/larger price treatment was deliberately not adopted
 * per user-testing feedback preferring the existing build), a full-bleed
 * photo background when the linked product has one, falling back to its
 * colour otherwise, and a decorative round "+" badge. A sold-out product
 * greys the tile out (no photo, no "+" badge) with "SOLD OUT" written over
 * it and blocks the short-tap add-to-cart; press-and-hold still opens the
 * detail popup either way, so staff can clear it again — see [onLongPress].
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ProductMenuTile(button: PosMenuButtonDto, onClick: () -> Unit, onLongPress: () -> Unit) {
    val colors = LocalZedReadColors.current
    val isSoldOut = button.isSoldOut == true
    val fillColor = when {
        isSoldOut -> SoldOutTileColor
        button.color != null -> parseHexColor(button.color)
        button.categoryColor != null -> parseHexColor(button.categoryColor)
        else -> colors.accent
    }
    val textColor = if (isSoldOut) Color.White else contrastTextColor(button.color ?: button.categoryColor ?: "#554C44")
    val isInactive = button.isActive == false

    Box(
        modifier = Modifier
            .fillMaxSize()
            .clip(RoundedCornerShape(12.dp))
            .background(fillColor)
            // enabled only gates isInactive (a POS-layout-disabled button) —
            // NOT isSoldOut. combinedClickable's enabled flag disables both
            // onClick and onLongClick together, and long-press must always
            // register even while sold out (that's how staff reopen this
            // popup to toggle it back on); the short-tap add-to-cart is
            // instead a no-op for a sold-out product at the ViewModel level
            // (SellViewModel.addToCart), not disabled here.
            .combinedClickable(enabled = !isInactive, onClick = onClick, onLongClick = onLongPress),
    ) {
        if (button.productPhotoUrl != null && !isSoldOut) {
            AsyncImage(
                model = button.productPhotoUrl,
                contentDescription = button.productName,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
            // Legibility scrim so the name/price stay readable over an arbitrary photo.
            Box(modifier = Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.28f)))
        }
        Column(modifier = Modifier.padding(10.dp)) {
            Text(
                button.productName ?: "—",
                // Reserve room for the "+" badge's top-right corner, same fix as
                // ProductTile in the category grid — a wrapped name previously
                // rendered under the badge, reading as if the "+" were part of it.
                modifier = if (!isInactive && !isSoldOut) Modifier.padding(end = 22.dp) else Modifier,
                color = textColor,
                fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.titleSmall,
                maxLines = 2,
            )
            Spacer(Modifier.height(4.dp))
            Text(formatMenuTileCents(button.priceCents ?: 0L), color = textColor, style = MaterialTheme.typography.bodyMedium)
        }
        if (!isInactive && !isSoldOut) {
            Box(
                modifier = Modifier
                    .padding(5.dp)
                    .align(Alignment.TopEnd)
                    .size(18.dp)
                    .clip(CircleShape)
                    .background(Color.Black.copy(alpha = 0.18f)),
                contentAlignment = Alignment.Center,
            ) {
                Text("+", color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
            }
        }
        if (isSoldOut) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("SOLD OUT", color = textColor, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}

private fun formatMenuTileCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
