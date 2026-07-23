package com.zedread.pos.ui.screens.orderentry

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.lazy.items as columnItems
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.List as ListIcon
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import coil.compose.AsyncImage
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.api.PosMenuLayoutDto
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.ProductEntity
import com.zedread.pos.ui.components.PosTopBar
import com.zedread.pos.ui.components.SyncPanel
import com.zedread.pos.ui.screens.payment.PaymentModal
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.theme.SoldOutTileColor
import com.zedread.pos.ui.theme.ZedReadColors
import com.zedread.pos.ui.theme.contrastTextColor
import com.zedread.pos.ui.theme.parseHexColor
import com.zedread.pos.ui.viewmodel.CartActionState
import com.zedread.pos.ui.viewmodel.HeldOrdersViewModel
import com.zedread.pos.ui.viewmodel.ModifierSheetState
import com.zedread.pos.ui.viewmodel.OrderType
import com.zedread.pos.ui.viewmodel.SellViewModel
import com.zedread.pos.ui.viewmodel.SyncViewModel
import com.zedread.pos.ui.viewmodel.TopBarViewModel

/**
 * Register (order-entry) screen — exact-match layout to
 * `design_handoff_zedread/ZedRead Register.dc.html`'s three-region design:
 * category rail, product grid, order pane. Replaces the earlier separate
 * Catalog/Cart screens — the design has no "go to cart" navigation step,
 * the order pane is always visible alongside the grid.
 *
 * The modifier customise sheet and payment modal are both overlays on this
 * one screen in the design bundle — not separate nav destinations, see
 * SellViewModel's class doc — so they're rendered here as siblings over the
 * base layout, driven by [SellViewModel.modifierSheetState]/[SellViewModel.paymentState].
 *
 * Switch-operator and cash-up controls have no home in the exact-match
 * design itself — they live in the persistent top nav bar
 * (README-tables-floormap.md), which is out of Phase 1 scope. Kept as
 * header icon buttons here as a functional stand-in until that nav ships.
 */
@Composable
fun OrderEntryScreen(
    onSwitchUser: () -> Unit,
    onCashUp: () -> Unit,
    onSettings: () -> Unit,
    onInvoiceSearch: () -> Unit,
    viewModel: SellViewModel = hiltViewModel(),
    syncViewModel: SyncViewModel = hiltViewModel(),
    topBarViewModel: TopBarViewModel = hiltViewModel(),
    heldOrdersViewModel: HeldOrdersViewModel = hiltViewModel(),
) {
    val colors = LocalZedReadColors.current
    val deviceName by topBarViewModel.deviceName.collectAsState()
    val categories by viewModel.categories.collectAsState()
    val products by viewModel.products.collectAsState()
    val selectedCatId by viewModel.selectedCategoryId.collectAsState()
    val lineItems by viewModel.lineItems.collectAsState()
    val discountCents by viewModel.discountCents.collectAsState()
    val cartActionState by viewModel.cartActionState.collectAsState()
    val ticketNumber by viewModel.ticketNumber.collectAsState()
    val orderType by viewModel.orderType.collectAsState()
    val selectedLineItemId by viewModel.selectedLineItemId.collectAsState()
    val modifierSheetState by viewModel.modifierSheetState.collectAsState()
    val paymentState by viewModel.paymentState.collectAsState()
    val menuLayouts by viewModel.menuLayouts.collectAsState()
    val selectedMenuLayoutId by viewModel.selectedMenuLayoutId.collectAsState()
    val isMenuManualOverride by viewModel.isMenuManualOverride.collectAsState()
    val currentMenuLayout by viewModel.currentMenuLayout.collectAsState()
    val effectiveTabId by viewModel.effectiveTabId.collectAsState()
    val isAutoMenuEnabled by viewModel.isAutoMenuEnabled.collectAsState()
    val productDetail by viewModel.productDetail.collectAsState()
    val soldOutActionError by viewModel.soldOutActionError.collectAsState()

    val isOnline by syncViewModel.isOnline.collectAsState()
    val pendingCount by syncViewModel.pendingCount.collectAsState()
    val syncItems by syncViewModel.items.collectAsState()
    var showSyncPanel by remember { mutableStateOf(false) }
    var showDiscountDialog by remember { mutableStateOf(false) }
    var showHeldOrders by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize().background(colors.bg)) {
            PosTopBar(
                title = deviceName ?: "Register",
                subtitle = currentMenuLayout?.tabs?.firstOrNull { it.id == effectiveTabId }?.name
                    ?: categories.firstOrNull { it.id == selectedCatId }?.name
                    ?: "All Items",
                isOnline = isOnline,
                pendingCount = pendingCount,
                onSyncClick = { showSyncPanel = true },
            ) {
                // Fixed white, not colors.muted — this row renders inside PosTopBar's
                // own always-dark (#332E29) background, not the theme-aware surface
                // these screens otherwise sit on.
                IconButton(onClick = { showHeldOrders = true; heldOrdersViewModel.refresh() }) {
                    Icon(ListIcon, contentDescription = "Held orders", tint = Color.White)
                }
                IconButton(onClick = onInvoiceSearch) {
                    Icon(Icons.Default.History, contentDescription = "Invoice search", tint = Color.White)
                }
                IconButton(onClick = onSettings) {
                    Icon(Icons.Default.Settings, contentDescription = "Settings", tint = Color.White)
                }
                IconButton(onClick = onCashUp) {
                    Icon(Icons.Default.AttachMoney, contentDescription = "Cash up", tint = Color.White)
                }
                IconButton(onClick = onSwitchUser) {
                    Icon(Icons.Default.Person, contentDescription = "Switch operator", tint = Color.White)
                }
            }

            Row(modifier = Modifier.fillMaxSize()) {
                Column(modifier = Modifier.fillMaxHeight()) {
                    MenuSelectorRow(
                        layouts = menuLayouts,
                        selectedId = selectedMenuLayoutId,
                        isManualOverride = isMenuManualOverride,
                        showAllItemsOption = isAutoMenuEnabled,
                        onSelect = viewModel::selectMenuLayout,
                    )
                    // The unfiltered category rail/grid is itself the "all items" view —
                    // gated behind Auto Menu same as the selector's dropdown option below,
                    // so a site with no active/default layout can't silently fall back to
                    // showing the whole catalog when Auto Menu is off (see NoMenuAvailable).
                    val layoutForRail = currentMenuLayout
                    if (layoutForRail != null) {
                        MenuTabRail(
                            layout = layoutForRail,
                            effectiveTabId = effectiveTabId,
                            onSelectTab = viewModel::selectTab,
                            modifier = Modifier.weight(1f),
                        )
                    } else if (isAutoMenuEnabled) {
                        CategoryRail(
                            categories = categories,
                            selectedCatId = selectedCatId,
                            onSelect = viewModel::selectCategory,
                            modifier = Modifier.weight(1f),
                        )
                    } else {
                        Spacer(Modifier.weight(1f))
                    }
                }

                Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
                    val layoutForGrid = currentMenuLayout
                    if (layoutForGrid != null) {
                        Column(modifier = Modifier.fillMaxSize()) {
                            MenuBreadcrumb(layout = layoutForGrid, tabId = effectiveTabId, onSelectTab = viewModel::selectTab)
                            MenuTileGrid(
                                layout = layoutForGrid,
                                tabId = effectiveTabId,
                                onProductTap = viewModel::addToCartByRef,
                                onProductLongPress = viewModel::openProductDetailByRef,
                                onFolderTap = viewModel::selectTab,
                                modifier = Modifier.weight(1f),
                            )
                        }
                    } else if (isAutoMenuEnabled) {
                        ProductGrid(
                            products = products,
                            onProductTap = viewModel::addToCart,
                            onProductLongPress = viewModel::openProductDetail,
                        )
                    } else {
                        NoMenuAvailable()
                    }
                    if (cartActionState is CartActionState.Loading) {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }
                }

                OrderPane(
                    modifier = Modifier.width(360.dp).fillMaxHeight(),
                    ticketNumber = ticketNumber,
                    orderType = orderType,
                    onSelectOrderType = viewModel::selectOrderType,
                    lineItems = lineItems,
                    products = products,
                    selectedLineItemId = selectedLineItemId,
                    onSelectLine = viewModel::selectLine,
                    onQuantityChange = viewModel::setLineQuantity,
                    subtotalCents = viewModel.subtotalCents,
                    taxCents = viewModel.taxCents,
                    discountCents = discountCents,
                    totalCents = viewModel.totalCents,
                    onClearOrder = viewModel::clearOrder,
                    onDiscount = { showDiscountDialog = true },
                    onHold = viewModel::holdOrder,
                    onPay = viewModel::openPayment,
                    errorMessage = (cartActionState as? CartActionState.Error)?.message,
                )
            }
        }

        if (showDiscountDialog) {
            DiscountDialog(
                baseCents = viewModel.subtotalCents + viewModel.taxCents,
                currentDiscountCents = discountCents,
                onDismiss = { showDiscountDialog = false },
                onApply = { cents -> viewModel.setDiscount(cents); showDiscountDialog = false },
                onRemove = { viewModel.clearDiscount(); showDiscountDialog = false },
            )
        }

        if (showHeldOrders) {
            HeldOrdersOverlay(
                viewModel = heldOrdersViewModel,
                onDismiss = { showHeldOrders = false },
                onRecall = { invoiceId ->
                    viewModel.recallHeldOrder(invoiceId)
                    showHeldOrders = false
                },
            )
        }

        if (modifierSheetState !is ModifierSheetState.Closed) {
            ModifierSheetOverlay(
                state = modifierSheetState,
                onDismiss = viewModel::closeModifierSheet,
                onToggleChoice = viewModel::toggleModifierChoice,
                onToggleNested = viewModel::toggleNestedModifierChoice,
                onQtyDec = { viewModel.changeModifierSheetQuantity(-1) },
                onQtyInc = { viewModel.changeModifierSheetQuantity(1) },
                onConfirm = viewModel::confirmModifierSheet,
                totalPriceCents = viewModel::modifierSheetTotalCents,
            )
        }

        val currentPaymentState = paymentState
        if (currentPaymentState != null) {
            PaymentModal(
                state = currentPaymentState,
                totalCents = viewModel.totalCents,
                remainingCents = viewModel.remainingCents(currentPaymentState),
                isOnline = isOnline,
                onClose = viewModel::closePayment,
                onSelectMethod = viewModel::selectPaymentMethod,
                onToggleSplit = viewModel::toggleSplitMode,
                onSplitAmountChange = viewModel::setSplitAmountCents,
                onPickTender = viewModel::pickTender,
                onVoucherReferenceChange = viewModel::setVoucherReference,
                onConfirmCard = viewModel::confirmCardPayment,
                onConfirmCash = viewModel::confirmCashPayment,
                onConfirmVoucher = viewModel::confirmVoucherPayment,
                onNewOrder = viewModel::completePaymentAndStartNewOrder,
            )
        }

        if (showSyncPanel) {
            SyncPanel(
                isOnline = isOnline,
                items = syncItems,
                onSyncNow = syncViewModel::syncNow,
                onDismiss = { showSyncPanel = false },
            )
        }

        val currentProductDetail = productDetail
        if (currentProductDetail != null) {
            ProductDetailDialog(
                product = currentProductDetail,
                errorMessage = soldOutActionError,
                onToggleSoldOut = viewModel::toggleSoldOut,
                onDismiss = viewModel::closeProductDetail,
            )
        }
    }
}

@Composable
private fun CategoryRail(
    categories: List<CategoryEntity>,
    selectedCatId: String?,
    onSelect: (String?) -> Unit,
    modifier: Modifier = Modifier.fillMaxHeight(),
) {
    val colors = LocalZedReadColors.current
    LazyColumn(
        modifier = modifier
            .width(200.dp)
            .background(colors.surface)
            .border(width = 1.dp, color = colors.border),
    ) {
        item { CategoryRailRow(name = "All", color = null, selected = selectedCatId == null, onClick = { onSelect(null) }) }
        columnItems(categories) { cat ->
            CategoryRailRow(
                name = cat.name,
                color = parseHexColor(cat.defaultColor),
                selected = selectedCatId == cat.id,
                onClick = { onSelect(cat.id) },
            )
        }
    }
}

/**
 * Menu selector (Android POS Phase 3 — Menu Studio -> POS integration
 * depth): lets staff switch among the site's currently-active published
 * menu layouts, filtering the product grid to that layout's product_refs.
 * Renders nothing when the site has none (the grid stays unfiltered, same
 * as before this control existed — no empty/disabled control cluttering
 * the rail for a brand that hasn't adopted Menu Studio layouts).
 *
 * A star marks the schedule-active default; a "MANUAL" chip replaces it
 * once staff pick anything else, distinguishing an intentional override
 * from the schedule's own choice. Per user-testing feedback the selection
 * now persists across a completed sale rather than resetting to the star
 * each time (see SellViewModel.completePaymentAndStartNewOrder) — it only
 * moves on its own via [SellViewModel.refreshMenuLayouts], e.g. a daypart
 * boundary or the next login/sync.
 *
 * [showAllItemsOption] gates the unfiltered "All items" choice behind the
 * "Auto Menu" backend setting (Menu Studio's POS Layout tab) — per
 * user-testing feedback, the only menus visible should be the ones
 * published from Menu Studio unless a site/brand has explicitly opted in.
 */
@Composable
private fun MenuSelectorRow(
    layouts: List<PosMenuLayoutDto>,
    selectedId: String?,
    isManualOverride: Boolean,
    showAllItemsOption: Boolean,
    onSelect: (String?) -> Unit,
) {
    if (layouts.isEmpty()) return
    val colors = LocalZedReadColors.current
    var expanded by remember { mutableStateOf(false) }
    val selected = layouts.firstOrNull { it.id == selectedId }

    Box(modifier = Modifier.width(226.dp)) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(colors.surface)
                .border(width = 1.dp, color = colors.border)
                .clickable { expanded = true }
                .padding(horizontal = 14.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(selected?.color?.let { parseHexColor(it) } ?: colors.accent),
                )
                Spacer(Modifier.width(8.dp))
                Column {
                    Text(selected?.name ?: "All items", style = MaterialTheme.typography.labelLarge, color = colors.text)
                    Text(
                        // Spelled out rather than a bare "MANUAL"/"SCHEDULED" —
                        // user-testing feedback that the single-word chip
                        // wasn't self-explanatory on its own.
                        if (isManualOverride) "Manually selected" else if (selected != null) "Scheduled default" else "",
                        style = MaterialTheme.typography.labelSmall,
                        color = if (isManualOverride) colors.accent else colors.faint,
                    )
                }
            }
            Text("▾", color = colors.muted)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            if (showAllItemsOption) {
                DropdownMenuItem(text = { Text("All items") }, onClick = { onSelect(null); expanded = false })
            }
            layouts.forEach { layout ->
                DropdownMenuItem(
                    text = { Text(layout.name + if (layout.isEffectiveDefault) " ★" else "") },
                    onClick = { onSelect(layout.id); expanded = false },
                )
            }
        }
    }
}

@Composable
private fun CategoryRailRow(name: String, color: Color?, selected: Boolean, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    val fill = if (selected) (color ?: colors.accent) else Color.Transparent
    val textColor = if (selected) contrastTextColor((color ?: colors.accent).toHex()) else colors.text
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .background(fill)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp),
    ) {
        Text(
            name,
            color = textColor,
            maxLines = 1,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

private fun Color.toHex(): String {
    val r = (red * 255).toInt().coerceIn(0, 255)
    val g = (green * 255).toInt().coerceIn(0, 255)
    val b = (blue * 255).toInt().coerceIn(0, 255)
    return "#%02X%02X%02X".format(r, g, b)
}

/**
 * Shown instead of the unfiltered category rail/grid when Auto Menu is off
 * and no menu layout is currently active for this site — per user-testing
 * feedback, "the only menus visible should be the ones published from Menu
 * Studio", so a site with nothing scheduled/published shouldn't silently
 * fall back to the full catalog just because Auto Menu happens to be the
 * only thing standing between "no active layout" and "sell everything".
 */
@Composable
private fun NoMenuAvailable() {
    val colors = LocalZedReadColors.current
    Box(Modifier.fillMaxSize().background(colors.bg), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("No menu available", style = MaterialTheme.typography.titleMedium, color = colors.text)
            Spacer(Modifier.height(4.dp))
            Text(
                "Publish a menu layout in Menu Studio, or enable Auto Menu to browse the full catalog.",
                style = MaterialTheme.typography.bodySmall,
                color = colors.muted,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 32.dp),
            )
        }
    }
}

/**
 * The "All items" / category browsing grid — per user-testing feedback,
 * always laid out as [MENU_GRID_COLUMNS] fixed columns (matching the Menu
 * Studio grid's own 6-column convention, not the previous responsive
 * [GridCells.Adaptive]) and padded with empty placeholder cells up to at
 * least 6 rows, so a sparsely-stocked category doesn't collapse to a couple
 * of tiles floating at the top of an otherwise-empty screen.
 */
@Composable
private fun ProductGrid(
    products: List<ProductEntity>,
    onProductTap: (String) -> Unit,
    onProductLongPress: (String) -> Unit,
) {
    val colors = LocalZedReadColors.current
    if (products.isEmpty()) {
        Box(Modifier.fillMaxSize().background(colors.bg), contentAlignment = Alignment.Center) {
            Text("No products available", style = MaterialTheme.typography.bodyLarge, color = colors.muted)
        }
        return
    }
    val minCells = 6 * MENU_GRID_COLUMNS
    val paddedCount = maxOf(minCells, ((products.size + MENU_GRID_COLUMNS - 1) / MENU_GRID_COLUMNS) * MENU_GRID_COLUMNS)
    // A List<ProductEntity?>, not the items(count: Int) overload — this
    // project's pinned Compose Foundation version only resolves
    // LazyGridScope.items' Array/List overloads under the `items as
    // gridItems` import used elsewhere in this file, so the count-based
    // overload fails to compile ("None of the following candidates is
    // applicable"). A null entry renders as an empty placeholder cell.
    val paddedItems: List<ProductEntity?> = List(paddedCount) { products.getOrNull(it) }
    LazyVerticalGrid(
        columns = GridCells.Fixed(MENU_GRID_COLUMNS),
        modifier = Modifier.fillMaxSize().background(colors.bg),
        contentPadding = PaddingValues(18.dp, 18.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        gridItems(paddedItems) { product ->
            if (product != null) {
                ProductTile(
                    product = product,
                    onClick = { onProductTap(product.id) },
                    onLongPress = { onProductLongPress(product.id) },
                )
            } else {
                Spacer(Modifier.aspectRatio(1f))
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ProductTile(product: ProductEntity, onClick: () -> Unit, onLongPress: () -> Unit) {
    val colors = LocalZedReadColors.current
    val fillColor = if (product.isSoldOut) SoldOutTileColor else parseHexColor(product.categoryColor)
    val textColor = if (product.isSoldOut) Color.White else contrastTextColor(product.categoryColor)
    val hasModifiers = !product.modifierNames.isNullOrBlank()

    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(fillColor)
            .combinedClickable(onClick = onClick, onLongClick = onLongPress),
    ) {
        Column {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    product.name,
                    // Reserve room for the "+" badge's top-right corner (22.dp + 8.dp
                    // padding either side) so a wrapped name never renders under it —
                    // previously read as if the badge's "+" were part of the name.
                    modifier = if (hasModifiers && !product.isSoldOut) Modifier.padding(end = 22.dp) else Modifier,
                    color = textColor,
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 2,
                )
                Spacer(Modifier.height(4.dp))
                Text(formatCents(product.basePriceCents), color = textColor, style = MaterialTheme.typography.bodyMedium)
            }
            if (product.photoUrl != null) {
                AsyncImage(
                    model = product.photoUrl,
                    contentDescription = product.name,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(90.dp),
                )
            }
        }
        if (hasModifiers && !product.isSoldOut) {
            Box(
                modifier = Modifier
                    .padding(5.dp)
                    .align(Alignment.TopEnd)
                    .size(18.dp)
                    .clip(CircleShape)
                    .background(Color.Black.copy(alpha = 0.18f)),
                contentAlignment = Alignment.Center,
            ) {
                Text("+", color = textColor, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
            }
        }
        if (product.isSoldOut) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    "SOLD OUT",
                    color = textColor,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
        }
    }
}

@Composable
private fun OrderPane(
    modifier: Modifier,
    ticketNumber: Int?,
    orderType: OrderType,
    onSelectOrderType: (OrderType) -> Unit,
    lineItems: List<LineItemDto>,
    products: List<ProductEntity>,
    selectedLineItemId: String?,
    onSelectLine: (String) -> Unit,
    onQuantityChange: (String, Int) -> Unit,
    subtotalCents: Long,
    taxCents: Long,
    discountCents: Long,
    totalCents: Long,
    onClearOrder: () -> Unit,
    onDiscount: () -> Unit,
    onHold: () -> Unit,
    onPay: () -> Unit,
    errorMessage: String?,
) {
    val colors = LocalZedReadColors.current
    Column(
        modifier = modifier
            .background(colors.surface)
            .border(width = 1.dp, color = colors.border),
    ) {
        // ── Header: ticket chip, title, clear-order, order-type segments ──
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(32.dp)
                            .clip(CircleShape)
                            .background(colors.accentSoft),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            ticketNumber?.let { "#$it" } ?: "–",
                            color = colors.accent,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.labelMedium,
                        )
                    }
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text("Current Order", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = colors.text)
                        Text("${lineItems.size} item${if (lineItems.size == 1) "" else "s"}", style = MaterialTheme.typography.labelSmall, color = colors.faint)
                    }
                }
                if (lineItems.isNotEmpty()) {
                    IconButton(onClick = onClearOrder) {
                        Text("✕", color = colors.muted, fontWeight = FontWeight.Bold)
                    }
                }
            }

            Spacer(Modifier.height(12.dp))

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(11.dp))
                    .background(colors.surface2)
                    .padding(4.dp),
            ) {
                OrderType.values().forEach { type ->
                    val selected = type == orderType
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(9.dp))
                            .background(if (selected) colors.surface else Color.Transparent)
                            .clickable { onSelectOrderType(type) }
                            .padding(vertical = 8.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            type.label,
                            color = if (selected) colors.text else colors.muted,
                            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                            style = MaterialTheme.typography.labelMedium,
                        )
                    }
                }
            }
        }

        if (errorMessage != null) {
            Text(
                errorMessage,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }

        // ── Line list ──
        if (lineItems.isEmpty()) {
            Box(modifier = Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("🧾", style = MaterialTheme.typography.headlineMedium)
                    Spacer(Modifier.height(8.dp))
                    Text("No items yet.", color = colors.muted, style = MaterialTheme.typography.bodyMedium)
                }
            }
        } else {
            LazyColumn(modifier = Modifier.weight(1f).fillMaxWidth()) {
                columnItems(lineItems, key = { it.id }) { item ->
                    val categoryColor = products.firstOrNull { it.id == item.productId }?.categoryColor
                    OrderLineRow(
                        item = item,
                        categoryColor = categoryColor?.let { parseHexColor(it) } ?: colors.faint,
                        selected = item.id == selectedLineItemId,
                        onSelect = { onSelectLine(item.id) },
                        onQuantityChange = { qty -> onQuantityChange(item.id, qty) },
                    )
                }
            }
        }

        // ── Totals + actions ──
        Column(modifier = Modifier.padding(16.dp)) {
            TotalsRow("Subtotal", subtotalCents, colors)
            TotalsRow("GST (incl. 10%)", taxCents, colors)
            if (discountCents > 0) {
                Row(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Discount", color = colors.accent, style = MaterialTheme.typography.bodySmall)
                    Text("−${formatCents(discountCents)}", color = colors.accent, style = MaterialTheme.typography.bodySmall)
                }
            }
            Spacer(Modifier.height(6.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Total", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = colors.text)
                Text(formatCents(totalCents), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineSmall, color = colors.text)
            }

            Spacer(Modifier.height(10.dp))

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(40.dp)
                    .clip(RoundedCornerShape(9.dp))
                    .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(9.dp))
                    .clickable(enabled = lineItems.isNotEmpty(), onClick = onDiscount),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    if (discountCents > 0) "Edit discount" else "Discount",
                    color = if (lineItems.isNotEmpty()) colors.text else colors.faint,
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }

            Spacer(Modifier.height(10.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                Box(
                    modifier = Modifier
                        .height(48.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(10.dp))
                        .clickable(enabled = lineItems.isNotEmpty(), onClick = onHold)
                        .padding(horizontal = 20.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Hold", color = colors.text, fontWeight = FontWeight.SemiBold)
                }
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(if (lineItems.isNotEmpty()) colors.accent else colors.faint)
                        .clickable(enabled = lineItems.isNotEmpty(), onClick = onPay),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Pay ${formatCents(totalCents)}", color = Color.White, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun TotalsRow(label: String, cents: Long, colors: ZedReadColors) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = colors.muted, style = MaterialTheme.typography.bodySmall)
        Text(formatCents(cents), color = colors.muted, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun OrderLineRow(
    item: LineItemDto,
    categoryColor: Color,
    selected: Boolean,
    onSelect: () -> Unit,
    onQuantityChange: (Int) -> Unit,
) {
    val colors = LocalZedReadColors.current
    // Modifiers apply as a flat addition to the whole line, not scaled by
    // quantity — matches the backend's own invoice.subtotal_cents rollup,
    // see SellViewModel.modifierTotalCents()'s doc for why.
    val modifierTotalCents = item.modifiers.sumOf { it.priceDeltaCents }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(if (selected) colors.accentSoft else Color.Transparent)
            .clickable(onClick = onSelect)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .width(3.dp)
                .height(36.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(categoryColor),
        )
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(item.productName, color = colors.text, style = MaterialTheme.typography.bodyMedium)
            item.modifiers.forEach { mod ->
                Text(
                    "· ${mod.modifierName}" + if (mod.priceDeltaCents > 0) " +${formatCents(mod.priceDeltaCents)}" else "",
                    color = colors.muted,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            Text(
                "${formatCents(item.unitPriceCents)} ea",
                color = colors.faint,
                style = MaterialTheme.typography.labelSmall,
            )
        }
        QtyStepper(quantity = item.quantity, onChange = onQuantityChange)
        Spacer(Modifier.width(10.dp))
        Text(
            formatCents(item.subtotalCents + item.taxCents + modifierTotalCents),
            color = colors.text,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun QtyStepper(quantity: Int, onChange: (Int) -> Unit) {
    val colors = LocalZedReadColors.current
    Row(verticalAlignment = Alignment.CenterVertically) {
        StepperButton(symbol = "−", onClick = { onChange(quantity - 1) })
        Text(
            "$quantity",
            modifier = Modifier.width(28.dp),
            textAlign = TextAlign.Center,
            color = colors.text,
            style = MaterialTheme.typography.bodyMedium,
        )
        StepperButton(symbol = "+", onClick = { onChange(quantity + 1) })
    }
}

@Composable
private fun StepperButton(symbol: String, onClick: () -> Unit) {
    val colors = LocalZedReadColors.current
    Box(
        modifier = Modifier
            .size(28.dp)
            .clip(CircleShape)
            .background(colors.surface2)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(symbol, color = colors.text, fontWeight = FontWeight.Bold)
    }
}

private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
