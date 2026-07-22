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
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
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
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.ProductEntity
import com.zedread.pos.ui.screens.payment.PaymentModal
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.theme.ZedReadColors
import com.zedread.pos.ui.theme.contrastTextColor
import com.zedread.pos.ui.theme.parseHexColor
import com.zedread.pos.ui.viewmodel.CartActionState
import com.zedread.pos.ui.viewmodel.ModifierSheetState
import com.zedread.pos.ui.viewmodel.OrderType
import com.zedread.pos.ui.viewmodel.SellViewModel

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
    viewModel: SellViewModel = hiltViewModel(),
) {
    val colors = LocalZedReadColors.current
    val categories by viewModel.categories.collectAsState()
    val products by viewModel.products.collectAsState()
    val selectedCatId by viewModel.selectedCategoryId.collectAsState()
    val lineItems by viewModel.lineItems.collectAsState()
    val cartActionState by viewModel.cartActionState.collectAsState()
    val ticketNumber by viewModel.ticketNumber.collectAsState()
    val orderType by viewModel.orderType.collectAsState()
    val selectedLineItemId by viewModel.selectedLineItemId.collectAsState()
    val modifierSheetState by viewModel.modifierSheetState.collectAsState()
    val paymentState by viewModel.paymentState.collectAsState()

    Box(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize().background(colors.bg)) {
            RegisterHeader(
                selectedCategoryName = categories.firstOrNull { it.id == selectedCatId }?.name,
                onSwitchUser = onSwitchUser,
                onCashUp = onCashUp,
                onSettings = onSettings,
            )

            Row(modifier = Modifier.fillMaxSize()) {
                CategoryRail(
                    categories = categories,
                    selectedCatId = selectedCatId,
                    onSelect = viewModel::selectCategory,
                )

                Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
                    ProductGrid(
                        products = products,
                        onProductTap = viewModel::addToCart,
                    )
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
                    totalCents = viewModel.totalCents,
                    onClearOrder = viewModel::clearOrder,
                    onHold = viewModel::clearOrder,
                    onPay = viewModel::openPayment,
                    errorMessage = (cartActionState as? CartActionState.Error)?.message,
                )
            }
        }

        if (modifierSheetState !is ModifierSheetState.Closed) {
            ModifierSheetOverlay(
                state = modifierSheetState,
                onDismiss = viewModel::closeModifierSheet,
                onToggleChoice = viewModel::toggleModifierChoice,
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
    }
}

@Composable
private fun RegisterHeader(
    selectedCategoryName: String?,
    onSwitchUser: () -> Unit,
    onCashUp: () -> Unit,
    onSettings: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.surface)
            .border(width = 1.dp, color = colors.border)
            .padding(horizontal = 22.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Text("Register", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge, color = colors.text)
            Text(
                (selectedCategoryName ?: "All Items").uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = colors.faint,
            )
        }
        Row {
            IconButton(onClick = onSettings) {
                Icon(Icons.Default.Settings, contentDescription = "Settings", tint = colors.muted)
            }
            IconButton(onClick = onCashUp) {
                Icon(Icons.Default.AttachMoney, contentDescription = "Cash up", tint = colors.muted)
            }
            IconButton(onClick = onSwitchUser) {
                Icon(Icons.Default.Person, contentDescription = "Switch operator", tint = colors.muted)
            }
        }
    }
}

@Composable
private fun CategoryRail(categories: List<CategoryEntity>, selectedCatId: String?, onSelect: (String?) -> Unit) {
    val colors = LocalZedReadColors.current
    LazyColumn(
        modifier = Modifier
            .width(200.dp)
            .fillMaxHeight()
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

@Composable
private fun ProductGrid(products: List<ProductEntity>, onProductTap: (String) -> Unit) {
    val colors = LocalZedReadColors.current
    if (products.isEmpty()) {
        Box(Modifier.fillMaxSize().background(colors.bg), contentAlignment = Alignment.Center) {
            Text("No products available", style = MaterialTheme.typography.bodyLarge, color = colors.muted)
        }
        return
    }
    LazyVerticalGrid(
        columns = GridCells.Adaptive(180.dp),
        modifier = Modifier.fillMaxSize().background(colors.bg),
        contentPadding = PaddingValues(18.dp, 18.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        gridItems(products) { product -> ProductTile(product = product, onClick = { onProductTap(product.id) }) }
    }
}

@Composable
private fun ProductTile(product: ProductEntity, onClick: () -> Unit) {
    val fillColor = parseHexColor(product.categoryColor)
    val textColor = contrastTextColor(product.categoryColor)
    val hasModifiers = !product.modifierNames.isNullOrBlank()

    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(fillColor)
            .clickable(onClick = onClick),
    ) {
        Column {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    product.name,
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
        if (hasModifiers) {
            Box(
                modifier = Modifier
                    .padding(8.dp)
                    .align(Alignment.TopEnd)
                    .size(22.dp)
                    .clip(CircleShape)
                    .background(Color.Black.copy(alpha = 0.18f)),
                contentAlignment = Alignment.Center,
            ) {
                Text("+", color = textColor, fontWeight = FontWeight.Bold)
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
    totalCents: Long,
    onClearOrder: () -> Unit,
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
                            ticketNumber?.toString() ?: "–",
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
            Spacer(Modifier.height(6.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Total", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = colors.text)
                Text(formatCents(totalCents), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineSmall, color = colors.text)
            }

            Spacer(Modifier.height(14.dp))

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
