package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.api.LineModifierDto
import com.zedread.pos.data.api.PosMenuLayoutDto
import com.zedread.pos.data.api.ProductModifierGroupDto
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.ProductEntity
import com.zedread.pos.data.repository.CatalogRepository
import com.zedread.pos.data.repository.InvoiceRepository
import com.zedread.pos.data.repository.MenuLayoutRepository
import com.zedread.pos.data.repository.OutboxRepository
import com.zedread.pos.data.sync.OutboxSaleLine
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.io.IOException
import java.util.UUID
import javax.inject.Inject

/**
 * Owns one sale end to end: browsing the catalog, building the cart
 * (including the modifier customise sheet), and taking payment.
 *
 * The modifier sheet and payment modal are both overlays on the Register
 * screen itself in the design bundle (not separate nav destinations — see
 * `ZedRead Register.dc.html`'s own `mod`/`pay` state living alongside
 * `order[]` on one Component), so their state lives here as plain StateFlows
 * rather than being routed through Compose Navigation — the Register screen
 * is a single flat nav destination (`Screen.OrderEntry`), and this ViewModel
 * scopes to it via the default `hiltViewModel()`. There is no
 * `GET /invoices/{id}/line-items` to reconstruct the cart from, so a fresh
 * sale after "New order" is a same-instance state reset
 * ([completePaymentAndStartNewOrder]) rather than a new ViewModel instance.
 *
 * **Offline write-queue scope** (Android POS Phase 2): a sale that fails to
 * sync on its very first action — [currentInvoiceId] is still null, so
 * nothing for this sale exists server-side yet — continues entirely
 * locally from that point ([isOfflineSale]), using synthesized [LineItemDto]
 * rows (a client-generated id, quantity × unit price for the subtotal, and
 * `taxCents = 0` since tax rules live server-side and can't be reproduced
 * on-device — see OutboxModels.kt's doc), and is queued as one bundle at
 * Pay time via [OutboxRepository.enqueueSale]. A sale that only drops
 * offline *after* a line item already exists on the server is a
 * deliberately unhandled case: silently switching it to local-only mode
 * would risk creating a second, duplicate invoice once the queued bundle
 * syncs (a plain retry of the same call, with client_ref, doesn't have
 * that risk — a mid-sale switch to a different sync mechanism does). That
 * action instead surfaces the existing error state so the operator can
 * retry it once reconnected. Split payment is unsupported for a sale
 * already in offline mode ([toggleSplitMode]) — a queued bundle carries
 * exactly one payment call, not multiple partial legs against one invoice.
 */
@HiltViewModel
class SellViewModel @Inject constructor(
    private val catalogRepo: CatalogRepository,
    private val invoiceRepo: InvoiceRepository,
    private val outboxRepo: OutboxRepository,
    private val menuLayoutRepo: MenuLayoutRepository,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    // ── Tables handoff (Android POS Phase 4) ────────────────────────────────
    //
    // "Open order →" on the Tables screen navigates here with a
    // `tableSessionId` nav arg (see PosNavHost's Screen.OrderEntry route).
    // Hilt's hiltViewModel() automatically backs [SavedStateHandle] with the
    // current nav back stack entry's arguments, so this is populated without
    // the screen itself having to pass anything through. Consumed exactly
    // once — on this sell session's very first invoice creation, same as
    // [currentInvoiceId]'s own lazy-create-on-first-item pattern below —
    // then cleared, so a subsequent "New order" on the same screen instance
    // doesn't keep re-attaching to the same table.
    private var pendingTableSessionId: String? = savedStateHandle.get<String>("tableSessionId")

    // ── Category / product browsing ─────────────────────────────────────────

    /** null = "All" tab showing every product. */
    private val _selectedCategoryId = MutableStateFlow<String?>(null)
    val selectedCategoryId: StateFlow<String?> = _selectedCategoryId.asStateFlow()

    val categories: StateFlow<List<CategoryEntity>> =
        catalogRepo.observeCategories()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun selectCategory(categoryId: String?) { _selectedCategoryId.value = categoryId }

    // ── Menu selector (Phase 3 — Menu Studio -> POS integration depth) ──────
    //
    // Lists every currently-active published layout for the site
    // (GET /pos/menu-layout) so staff can switch which one filters the
    // product grid below. isEffectiveDefault (server-resolved: a site's own
    // daypart default takes precedence over the brand-wide one) marks the
    // schedule-active choice; selecting anything else is a manual override,
    // exposed via [isMenuManualOverride] so the UI can distinguish the two.
    // A layout with no product buttons at all (or none selected) falls back
    // to showing the full unfiltered catalog below, same as before this
    // selector existed. Declared ahead of [products] since its combine()
    // reads these flows at construction time — property initializers run in
    // declaration order, so referencing them before this point would read
    // an unset backing field.

    private val _menuLayouts = MutableStateFlow<List<PosMenuLayoutDto>>(emptyList())
    val menuLayouts: StateFlow<List<PosMenuLayoutDto>> = _menuLayouts.asStateFlow()

    private val _selectedMenuLayoutId = MutableStateFlow<String?>(null)
    val selectedMenuLayoutId: StateFlow<String?> = _selectedMenuLayoutId.asStateFlow()

    val isMenuManualOverride: StateFlow<Boolean> =
        combine(_selectedMenuLayoutId, _menuLayouts) { selectedId, layouts ->
            selectedId != null && selectedId != layouts.firstOrNull { it.isEffectiveDefault }?.id
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), false)

    /** Staff picking a layout from the menu selector — a manual override until the next completed sale. */
    fun selectMenuLayout(layoutId: String?) { _selectedMenuLayoutId.value = layoutId }

    /**
     * Re-fetch the site's active layouts.
     *
     * [forceDefaultSelection] is true only right after a completed
     * transaction — it discards whatever was manually selected and re-picks
     * the schedule's own default at that moment, per the "reverts after a
     * completed transaction" requirement. On a plain refresh (app launch,
     * pull-to-refresh) the current selection is kept if it's still among
     * the active set, falling back to the default only if it's gone.
     * Failure is silent — the grid already falls back to the unfiltered
     * catalog when no layout resolves, so a network hiccup here never
     * blocks a sale.
     */
    fun refreshMenuLayouts(forceDefaultSelection: Boolean = false) {
        viewModelScope.launch {
            runCatching { menuLayoutRepo.getMenuLayouts() }
                .onSuccess { layouts ->
                    _menuLayouts.value = layouts
                    val keepCurrent = !forceDefaultSelection && layouts.any { it.id == _selectedMenuLayoutId.value }
                    if (!keepCurrent) {
                        _selectedMenuLayoutId.value = layouts.firstOrNull { it.isEffectiveDefault }?.id
                    }
                }
        }
    }

    private val categoryFilteredProducts: Flow<List<ProductEntity>> =
        _selectedCategoryId.flatMapLatest { catId -> catalogRepo.observeProducts(catId) }

    /** Category-filtered products, further narrowed to the selected menu layout's product_refs, if any. */
    val products: StateFlow<List<ProductEntity>> =
        combine(categoryFilteredProducts, _selectedMenuLayoutId, _menuLayouts) { catalogProducts, layoutId, layouts ->
            val refs = layouts.firstOrNull { it.id == layoutId }?.productRefs
            if (refs.isNullOrEmpty()) catalogProducts else catalogProducts.filter { it.ref in refs }
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    private val _refreshError = MutableStateFlow<String?>(null)
    val refreshError: StateFlow<String?> = _refreshError.asStateFlow()

    /** Fetch fresh catalog from the network and update the Room cache. */
    fun refresh() {
        _isRefreshing.value = true
        _refreshError.value = null
        viewModelScope.launch {
            runCatching { catalogRepo.refresh() }
                .onFailure { e -> _refreshError.value = e.message }
            _isRefreshing.value = false
        }
    }

    init { refresh(); refreshMenuLayouts() }

    // ── Cart (the current sale's invoice) ───────────────────────────────────

    /** The draft invoice this sale is building, created lazily on the first item added. Null once [isOfflineSale]. */
    private var currentInvoiceId: String? = null

    /** True once this sale has fallen back to local-only offline mode — see the class doc. */
    private var isOfflineSale = false
    val isCurrentSaleOffline: Boolean get() = isOfflineSale

    private val _lineItems = MutableStateFlow<List<LineItemDto>>(emptyList())
    val lineItems: StateFlow<List<LineItemDto>> = _lineItems.asStateFlow()

    /**
     * A line's modifiers apply as a flat addition to the whole line, not
     * scaled by quantity — matching add_line_modifier()/
     * _recompute_invoice_totals()'s snapshot model on the backend (one
     * InvoiceLineModifier row per line, its price_delta_cents added once).
     * Mirrored here so the client-computed totals below match the backend's
     * authoritative invoice.total_cents without an extra round trip per cart
     * mutation.
     */
    private fun modifierTotalCents(item: LineItemDto): Long = item.modifiers.sumOf { it.priceDeltaCents }

    /** Subtotal across all lines, including each line's flat modifier total (matches invoice.subtotal_cents). */
    val subtotalCents: Long get() = _lineItems.value.sumOf { it.subtotalCents + modifierTotalCents(it) }

    /** Tax across all lines — modifiers carry no tax of their own (matches invoice.tax_cents). */
    val taxCents: Long get() = _lineItems.value.sumOf { it.taxCents }

    /** Computed total in cents across all line items (subtotal, incl. modifiers, + tax). */
    val totalCents: Long get() = subtotalCents + taxCents

    private val _cartActionState = MutableStateFlow<CartActionState>(CartActionState.Idle)
    val cartActionState: StateFlow<CartActionState> = _cartActionState.asStateFlow()

    /**
     * Tap a product tile. A product with a modifier set — [ProductEntity.modifierNames]
     * non-blank, the same field that backs the grid's "+" badge — opens the
     * customise sheet instead of adding directly; a plain product adds
     * straight to the order, same as before.
     */
    fun addToCart(productId: String) {
        val product = products.value.firstOrNull { it.id == productId } ?: return
        if (!product.modifierNames.isNullOrBlank()) {
            openModifierSheet(product)
            return
        }
        addPlainLineItem(productId, quantity = 1)
    }

    /** Opens the draft invoice first if this is the first item, then appends the line. */
    private fun addPlainLineItem(productId: String, quantity: Int) {
        if (isOfflineSale) {
            addOfflineLine(productId, quantity, modifiers = emptyList())
            return
        }
        _cartActionState.value = CartActionState.Loading
        viewModelScope.launch {
            runCatching {
                val invoiceId = currentInvoiceId
                    ?: invoiceRepo.createInvoice(tableSessionId = pendingTableSessionId).id.also {
                        currentInvoiceId = it
                        pendingTableSessionId = null
                        issueTicketNumber()
                    }
                invoiceRepo.addLineItem(invoiceId, productId, quantity)
            }
                .onSuccess { item ->
                    _lineItems.value = _lineItems.value + item
                    _cartActionState.value = CartActionState.Idle
                }
                .onFailure { e ->
                    if (e is IOException && currentInvoiceId == null) {
                        beginOfflineSale()
                        addOfflineLine(productId, quantity, modifiers = emptyList())
                    } else {
                        _cartActionState.value = CartActionState.Error(e.message ?: "Failed to add item")
                    }
                }
        }
    }

    /**
     * Switch this sale to local-only offline mode — see the class doc for
     * why this is only ever entered when nothing for the sale exists
     * server-side yet ([currentInvoiceId] still null at the point of
     * failure).
     */
    private fun beginOfflineSale() {
        isOfflineSale = true
        if (_ticketNumber.value == null) issueTicketNumber()
    }

    /** Build and append a locally-synthesized line — see the class doc's "Offline write-queue scope" note. */
    private fun addOfflineLine(productId: String, quantity: Int, modifiers: List<ModifierGroupSelection>) {
        val product = products.value.firstOrNull { it.id == productId } ?: return
        val lineId = UUID.randomUUID().toString()
        val optionIds = modifiers.flatMap { gs ->
            gs.selected.mapNotNull { idx ->
                val option = gs.group.options.getOrNull(idx) ?: return@mapNotNull null
                if (gs.isSingleSelect || option.priceDeltaCents > 0) option else null
            }
        }
        val modifierDtos = optionIds.map { option ->
            LineModifierDto(
                id = UUID.randomUUID().toString(),
                lineItemId = lineId,
                modifierOptionId = option.id,
                modifierName = option.name,
                priceDeltaCents = option.priceDeltaCents,
            )
        }
        val item = LineItemDto(
            id = lineId,
            productId = product.id,
            productName = product.name,
            quantity = quantity,
            unitPriceCents = product.basePriceCents,
            subtotalCents = product.basePriceCents * quantity,
            // Tax rules live server-side (inclusive/exclusive/compound) and
            // can't be reproduced on-device — confirmed once this sale syncs.
            taxCents = 0L,
            modifiers = modifierDtos,
        )
        _lineItems.value = _lineItems.value + item
        _cartActionState.value = CartActionState.Idle
    }

    /**
     * Change a line's quantity via the Register screen's qty stepper.
     * Dropping to 0 removes the line entirely, same as tapping remove.
     */
    fun setLineQuantity(lineItemId: String, quantity: Int) {
        if (quantity < 1) { removeLine(lineItemId); return }
        if (isOfflineSale) {
            _lineItems.value = _lineItems.value.map {
                if (it.id == lineItemId) it.copy(quantity = quantity, subtotalCents = it.unitPriceCents * quantity) else it
            }
            return
        }
        val invoiceId = currentInvoiceId ?: return
        _cartActionState.value = CartActionState.Loading
        viewModelScope.launch {
            runCatching { invoiceRepo.updateLineItemQuantity(invoiceId, lineItemId, quantity) }
                .onSuccess { updated ->
                    // PATCH's response has no modifiers field (LineItemResponse, not
                    // LineItemDetailResponse) — keep whatever this line's modifiers
                    // already were rather than dropping them from the display.
                    val previousModifiers = _lineItems.value.firstOrNull { it.id == lineItemId }?.modifiers ?: emptyList()
                    _lineItems.value = _lineItems.value.map {
                        if (it.id == lineItemId) updated.copy(modifiers = previousModifiers) else it
                    }
                    _cartActionState.value = CartActionState.Idle
                }
                .onFailure { e -> _cartActionState.value = CartActionState.Error(e.message ?: "Failed to update quantity") }
        }
    }

    /** Remove a line from the order. */
    fun removeLine(lineItemId: String) {
        if (isOfflineSale) {
            _lineItems.value = _lineItems.value.filterNot { it.id == lineItemId }
            if (_selectedLineItemId.value == lineItemId) _selectedLineItemId.value = null
            return
        }
        val invoiceId = currentInvoiceId ?: return
        _cartActionState.value = CartActionState.Loading
        viewModelScope.launch {
            runCatching { invoiceRepo.removeLineItem(invoiceId, lineItemId) }
                .onSuccess {
                    _lineItems.value = _lineItems.value.filterNot { it.id == lineItemId }
                    if (_selectedLineItemId.value == lineItemId) _selectedLineItemId.value = null
                    _cartActionState.value = CartActionState.Idle
                }
                .onFailure { e -> _cartActionState.value = CartActionState.Error(e.message ?: "Failed to remove item") }
        }
    }

    fun resetCartActionState() { _cartActionState.value = CartActionState.Idle }

    // ── Modifier customise sheet ────────────────────────────────────────────
    //
    // Mirrors the design bundle's own state machine (`mod: {prod, sets, sel,
    // qty}`, `toggleChoice()`, `modAddToOrder()`): single-select groups
    // default to their first option and always keep exactly one selected;
    // multi-select groups toggle freely with no default. On confirm, a
    // single-select group's chosen option is always attached as a line
    // modifier (even a free one, e.g. "Small" at +$0, so it still shows on
    // the receipt); a multi-select choice is only attached when it carries a
    // price — exactly modAddToOrder's `c.price>0 || g.type==='single'` filter.

    private val _modifierSheetState = MutableStateFlow<ModifierSheetState>(ModifierSheetState.Closed)
    val modifierSheetState: StateFlow<ModifierSheetState> = _modifierSheetState.asStateFlow()

    private fun openModifierSheet(product: ProductEntity) {
        _modifierSheetState.value = ModifierSheetState.Loading(product)
        viewModelScope.launch {
            runCatching { catalogRepo.getProductModifiers(product.id) }
                .onSuccess { groups ->
                    val selections = groups.map { group ->
                        val defaultSelected =
                            if (group.maxSelections <= 1 && group.options.isNotEmpty()) setOf(0) else emptySet()
                        ModifierGroupSelection(group, defaultSelected)
                    }
                    _modifierSheetState.value = ModifierSheetState.Ready(product, selections, quantity = 1)
                }
                .onFailure { e ->
                    // Modifier prices aren't cached locally (see CatalogRepository.getProductModifiers'
                    // doc), so a customisable item genuinely can't be rung up offline — a plain item
                    // still can (addPlainLineItem's own offline fallback).
                    val message = if (e is IOException) {
                        "This item can't be customised while offline — try a plain item instead."
                    } else {
                        e.message ?: "Failed to load modifiers"
                    }
                    _modifierSheetState.value = ModifierSheetState.Error(product, message)
                }
        }
    }

    /** Radio-style select for a single-select group, checkbox-style toggle for multi-select. */
    fun toggleModifierChoice(groupIndex: Int, optionIndex: Int) {
        val state = _modifierSheetState.value as? ModifierSheetState.Ready ?: return
        val groups = state.groups.toMutableList()
        val current = groups.getOrNull(groupIndex) ?: return
        val newSelected = when {
            current.isSingleSelect -> setOf(optionIndex)
            current.selected.contains(optionIndex) -> current.selected - optionIndex
            else -> current.selected + optionIndex
        }
        groups[groupIndex] = current.copy(selected = newSelected)
        _modifierSheetState.value = state.copy(groups = groups)
    }

    fun changeModifierSheetQuantity(delta: Int) {
        val state = _modifierSheetState.value as? ModifierSheetState.Ready ?: return
        _modifierSheetState.value = state.copy(quantity = (state.quantity + delta).coerceAtLeast(1))
    }

    fun closeModifierSheet() { _modifierSheetState.value = ModifierSheetState.Closed }

    /** Per-unit price including selected modifiers — mirrors modAddToOrder's live `unit` calc. */
    fun modifierSheetUnitPriceCents(state: ModifierSheetState.Ready): Long {
        var unit = state.product.basePriceCents
        state.groups.forEach { gs ->
            gs.selected.forEach { idx -> unit += gs.group.options.getOrNull(idx)?.priceDeltaCents ?: 0 }
        }
        return unit
    }

    /** Footer total ("Add to order $total") — unit price × quantity, mirrors modTotalLabel. */
    fun modifierSheetTotalCents(state: ModifierSheetState.Ready): Long =
        modifierSheetUnitPriceCents(state) * state.quantity

    /**
     * Add the customised product to the order: the line item at the sheet's
     * quantity, then each qualifying selected option attached as a line
     * modifier (see the class doc above). Refetches the line afterward when
     * any modifier was attached, so the order pane can show the "· modifier"
     * sub-lines and modifier-inclusive total immediately rather than the
     * pre-modifier snapshot POST /line-items itself returns.
     */
    fun confirmModifierSheet() {
        val state = _modifierSheetState.value as? ModifierSheetState.Ready ?: return
        if (isOfflineSale) {
            addOfflineLine(state.product.id, state.quantity, modifiers = state.groups)
            _modifierSheetState.value = ModifierSheetState.Closed
            return
        }
        _cartActionState.value = CartActionState.Loading
        _modifierSheetState.value = ModifierSheetState.Closed
        viewModelScope.launch {
            runCatching {
                val invoiceId = currentInvoiceId
                    ?: invoiceRepo.createInvoice(tableSessionId = pendingTableSessionId).id.also {
                        currentInvoiceId = it
                        pendingTableSessionId = null
                        issueTicketNumber()
                    }
                val item = invoiceRepo.addLineItem(invoiceId, state.product.id, state.quantity)

                val optionIds = state.groups.flatMap { gs ->
                    gs.selected.mapNotNull { idx ->
                        val option = gs.group.options.getOrNull(idx) ?: return@mapNotNull null
                        if (gs.isSingleSelect || option.priceDeltaCents > 0) option.id else null
                    }
                }
                optionIds.forEach { optionId -> invoiceRepo.addLineModifier(invoiceId, item.id, optionId) }

                if (optionIds.isEmpty()) item else invoiceRepo.getLineItem(invoiceId, item.id)
            }
                .onSuccess { item ->
                    _lineItems.value = _lineItems.value + item
                    _cartActionState.value = CartActionState.Idle
                }
                .onFailure { e ->
                    if (e is IOException && currentInvoiceId == null) {
                        beginOfflineSale()
                        addOfflineLine(state.product.id, state.quantity, modifiers = state.groups)
                    } else {
                        _cartActionState.value = CartActionState.Error(e.message ?: "Failed to add item")
                    }
                }
        }
    }

    // ── Order pane presentation state (Register screen) ────────────────────
    //
    // Ticket number and order type are visual/interaction fidelity for the
    // design bundle's order pane — neither is backed by an Invoice field
    // today (no invoice_type/ticket_number column), so they're kept as local
    // UI state only. The ticket number resets with every new SellViewModel
    // instance (a fresh sale), not persisted across app restarts.

    private var ticketSeq = 0
    private val _ticketNumber = MutableStateFlow<Int?>(null)
    val ticketNumber: StateFlow<Int?> = _ticketNumber.asStateFlow()
    private fun issueTicketNumber() { _ticketNumber.value = ++ticketSeq }

    private val _orderType = MutableStateFlow(OrderType.DINE_IN)
    val orderType: StateFlow<OrderType> = _orderType.asStateFlow()
    fun selectOrderType(type: OrderType) { _orderType.value = type }

    private val _selectedLineItemId = MutableStateFlow<String?>(null)
    val selectedLineItemId: StateFlow<String?> = _selectedLineItemId.asStateFlow()
    fun selectLine(lineItemId: String) {
        _selectedLineItemId.value = if (_selectedLineItemId.value == lineItemId) null else lineItemId
    }

    /**
     * Clears the order pane back to empty — the design bundle's "clear order"
     * ✕ and Hold action, and also what a completed payment's "New order"
     * button resets to. The invoice itself (if any items were added) is NOT
     * voided or deleted here; it's simply left open/uncollected on the
     * backend when triggered by ✕/Hold. There's no "recall a held order"
     * list yet to bring it back — that's a real gap Hold leaves open,
     * flagged rather than silently dropped.
     */
    fun clearOrder() {
        currentInvoiceId = null
        isOfflineSale = false
        _lineItems.value = emptyList()
        _ticketNumber.value = null
        _selectedLineItemId.value = null
        _paymentState.value = null
    }

    // ── Payment ──────────────────────────────────────────────────────────────
    //
    // Mirrors the design bundle's `pay: {stage, method, tendered}` shape
    // (openPay/pickTender/confirmCard/confirmCash/newOrder), extended with
    // the Voucher tab and Split toggle the mockup predates the backend
    // capability for: splitMode/splitAmountCents track a partial-amount leg,
    // paidCents is the running total already paid on this sale, and
    // voucherReference backs the Voucher tab's reference-code input.

    private val _paymentState = MutableStateFlow<PaymentUiState?>(null)
    val paymentState: StateFlow<PaymentUiState?> = _paymentState.asStateFlow()

    /** Amount still owed on this sale — the full total until a split leg has been paid. */
    fun remainingCents(state: PaymentUiState): Long = (totalCents - state.paidCents).coerceAtLeast(0)

    fun openPayment() {
        if (_lineItems.value.isEmpty()) return
        _paymentState.value = PaymentUiState()
    }

    fun closePayment() { _paymentState.value = null }

    fun selectPaymentMethod(method: PaymentMethod) {
        val s = _paymentState.value ?: return
        if (s.stage != PaymentStage.CHOOSING) return
        _paymentState.value = s.copy(method = method, tendered = 0L, errorMessage = null)
    }

    fun toggleSplitMode(enabled: Boolean) {
        val s = _paymentState.value ?: return
        // A queued offline sale syncs as one bundle with exactly one payment
        // call — see the class doc's "Offline write-queue scope" note.
        if (isOfflineSale) return
        _paymentState.value = s.copy(splitMode = enabled, splitAmountCents = 0L, tendered = 0L, errorMessage = null)
    }

    fun setSplitAmountCents(cents: Long) {
        val s = _paymentState.value ?: return
        _paymentState.value = s.copy(splitAmountCents = cents.coerceAtLeast(0L), errorMessage = null)
    }

    /** Cash tab's tender-preset grid — a full amount tendered, may exceed what's due (change). */
    fun pickTender(amountCents: Long) {
        val s = _paymentState.value ?: return
        _paymentState.value = s.copy(tendered = amountCents, errorMessage = null)
    }

    fun setVoucherReference(reference: String) {
        val s = _paymentState.value ?: return
        _paymentState.value = s.copy(voucherReference = reference, errorMessage = null)
    }

    /** Card tab's "Charge $total" (or "Add payment" in split mode). Card never produces change. */
    fun confirmCardPayment() {
        val s = _paymentState.value ?: return
        val amount = if (s.splitMode) s.splitAmountCents else remainingCents(s)
        submitPayment(method = "card", amountCents = amount, reference = null)
    }

    /** Cash tab's "Complete payment" (or "Add payment" in split mode). */
    fun confirmCashPayment() {
        val s = _paymentState.value ?: return
        if (s.splitMode) {
            submitPayment(method = "cash", amountCents = s.splitAmountCents, reference = null)
            return
        }
        val due = remainingCents(s)
        if (s.tendered < due) {
            _paymentState.value = s.copy(errorMessage = "Insufficient amount")
            return
        }
        submitPayment(method = "cash", amountCents = s.tendered, reference = null)
    }

    /** Voucher tab's charge button — a reference code is required. */
    fun confirmVoucherPayment() {
        val s = _paymentState.value ?: return
        if (s.voucherReference.isBlank()) {
            _paymentState.value = s.copy(errorMessage = "Enter a voucher reference")
            return
        }
        val amount = if (s.splitMode) s.splitAmountCents else remainingCents(s)
        submitPayment(method = "voucher", amountCents = amount, reference = s.voucherReference)
    }

    private fun submitPayment(method: String, amountCents: Long, reference: String?) {
        val current = _paymentState.value ?: return
        if (amountCents <= 0) {
            _paymentState.value = current.copy(errorMessage = "Enter an amount")
            return
        }
        if (isOfflineSale) {
            submitOfflinePayment(method, amountCents, reference, current)
            return
        }
        val invoiceId = currentInvoiceId ?: return
        _paymentState.value = current.copy(isSubmitting = true, errorMessage = null)
        viewModelScope.launch {
            runCatching { invoiceRepo.pay(invoiceId, method, amountCents, reference) }
                .onSuccess { dto ->
                    val before = _paymentState.value ?: return@onSuccess
                    if (dto.status == "paid") {
                        // Cash change is whatever this payment overshot the balance that
                        // was still due before it — 0 for card/voucher, and for a
                        // non-split cash tender this is exactly amountCents - remaining.
                        val dueBeforeThisPayment = totalCents - before.paidCents
                        val change = (amountCents - dueBeforeThisPayment).coerceAtLeast(0)
                        _paymentState.value = before.copy(
                            stage = PaymentStage.DONE,
                            isSubmitting = false,
                            paidCents = before.paidCents + amountCents,
                            doneMethodLabel = method.replaceFirstChar { it.uppercase() },
                            doneAmountCents = totalCents,
                            doneChangeCents = if (method == "cash") change else 0L,
                        )
                    } else {
                        // Split leg recorded but the balance isn't covered yet — reset to
                        // a fresh Choosing state with the running paidCents carried over,
                        // per "Add another payment" keeping the modal open.
                        _paymentState.value = PaymentUiState(paidCents = before.paidCents + amountCents)
                    }
                }
                .onFailure { e ->
                    val before = _paymentState.value ?: return@onFailure
                    _paymentState.value = before.copy(isSubmitting = false, errorMessage = e.message ?: "Payment failed")
                }
        }
    }

    /**
     * Queue this whole sale as one outbox bundle instead of calling the
     * network directly — see [OutboxRepository.enqueueSale] and the class
     * doc's "Offline write-queue scope" note. Change can't be confirmed
     * until the sale actually syncs (a cash tender's change depends on the
     * server-computed total, unknown while offline), so the Done screen is
     * told via [PaymentUiState.doneIsPendingSync] rather than shown a
     * (potentially wrong) figure.
     */
    private fun submitOfflinePayment(method: String, amountCents: Long, reference: String?, current: PaymentUiState) {
        _paymentState.value = current.copy(isSubmitting = true, errorMessage = null)
        viewModelScope.launch {
            runCatching {
                outboxRepo.enqueueSale(
                    lines = _lineItems.value.map { item ->
                        OutboxSaleLine(
                            productId = item.productId ?: error("Offline line item is missing its product id"),
                            quantity = item.quantity,
                            modifierOptionIds = item.modifiers.mapNotNull { it.modifierOptionId },
                        )
                    },
                    method = method,
                    amountCents = amountCents,
                    reference = reference,
                )
            }
                .onSuccess {
                    val before = _paymentState.value ?: return@onSuccess
                    _paymentState.value = before.copy(
                        stage = PaymentStage.DONE,
                        isSubmitting = false,
                        paidCents = before.paidCents + amountCents,
                        doneMethodLabel = method.replaceFirstChar { it.uppercase() },
                        doneAmountCents = totalCents,
                        doneChangeCents = 0L,
                        doneIsPendingSync = true,
                    )
                }
                .onFailure { e ->
                    val before = _paymentState.value ?: return@onFailure
                    _paymentState.value = before.copy(isSubmitting = false, errorMessage = e.message ?: "Couldn't queue this sale")
                }
        }
    }

    /** "New order" action from the Done screen — resets the sale and closes the modal. */
    fun completePaymentAndStartNewOrder() {
        clearOrder()
        // Re-resolve the schedule and drop back to its own default, discarding
        // any manual menu-selector override for the sale that just finished.
        refreshMenuLayouts(forceDefaultSelection = true)
    }
}

/** Order pane segmented control — visual/local only, see the ticket/order-type note above. */
enum class OrderType(val label: String) {
    DINE_IN("Dine-in"),
    TAKEAWAY("Takeaway"),
}

sealed class CartActionState {
    object Idle : CartActionState()
    object Loading : CartActionState()
    data class Error(val message: String) : CartActionState()
}

/** Modifier customise sheet state — mirrors the design bundle's `mod: {prod, sets, sel, qty}` shape. */
sealed class ModifierSheetState {
    object Closed : ModifierSheetState()
    data class Loading(val product: ProductEntity) : ModifierSheetState()
    data class Ready(
        val product: ProductEntity,
        val groups: List<ModifierGroupSelection>,
        val quantity: Int,
    ) : ModifierSheetState()
    data class Error(val product: ProductEntity, val message: String) : ModifierSheetState()
}

/** One modifier group's option list plus which option indices are currently selected. */
data class ModifierGroupSelection(
    val group: ProductModifierGroupDto,
    val selected: Set<Int>,
) {
    /** Radio-style (at most 1 choice) vs checkbox-style (multiple) — mirrors the mockup's g.type. */
    val isSingleSelect: Boolean get() = group.maxSelections <= 1
    val isRequired: Boolean get() = group.minSelections >= 1
}

/** Method tabs on the payment modal — Voucher is the flagged addition the design bundle predates. */
enum class PaymentMethod(val label: String) { CARD("Card"), CASH("Cash"), VOUCHER("Voucher") }

enum class PaymentStage { CHOOSING, DONE }

/**
 * Payment modal state — mirrors the design bundle's `pay: {stage, method,
 * tendered}` shape, extended with the split-payment fields the mockup
 * predates (splitMode/splitAmountCents/paidCents) and the Voucher tab's
 * reference-code input.
 */
data class PaymentUiState(
    val stage: PaymentStage = PaymentStage.CHOOSING,
    val method: PaymentMethod = PaymentMethod.CARD,
    val tendered: Long = 0L,
    val splitMode: Boolean = false,
    val splitAmountCents: Long = 0L,
    val voucherReference: String = "",
    val paidCents: Long = 0L,
    val isSubmitting: Boolean = false,
    val errorMessage: String? = null,
    val doneMethodLabel: String = "",
    val doneAmountCents: Long = 0L,
    val doneChangeCents: Long = 0L,
    /** True when this payment was queued to the offline outbox rather than confirmed by the server. */
    val doneIsPendingSync: Boolean = false,
)
