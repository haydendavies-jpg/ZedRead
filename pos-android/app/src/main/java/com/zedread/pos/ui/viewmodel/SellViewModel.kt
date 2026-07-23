package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.api.LineModifierDto
import com.zedread.pos.data.api.LinkedGroupDto
import com.zedread.pos.data.api.PosMenuLayoutDto
import com.zedread.pos.data.api.ProductModifierGroupDto
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.ProductEntity
import com.zedread.pos.data.repository.CatalogRepository
import com.zedread.pos.data.repository.MenuLayoutRepository
import com.zedread.pos.data.repository.OutboxRepository
import com.zedread.pos.data.repository.SettingKeys
import com.zedread.pos.data.repository.SettingsRepository
import com.zedread.pos.data.sync.OutboxSaleLine
import com.zedread.pos.data.sync.SyncPaymentLeg
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
 * **Local-first cart, sync-on-commit** (post-round-4 user feedback): the
 * cart is built ENTIRELY on-device — [addToCart]/[confirmModifierSheet]/
 * [setLineQuantity]/[removeLine] never touch the network. Every
 * [LineItemDto] here is synthesized locally, its subtotal/tax computed by
 * [computeLocalLineTax] (a Kotlin port of `invoice_service.add_line_item()`'s
 * own formula — both taxable and non-taxable products already snapshot
 * everything that formula needs on the product row itself, so no separate
 * tax-rate sync is needed), so the running total shown while building the
 * order is correct, not a placeholder — and there is deliberately no
 * loading state for any of these: they're synchronous in-memory operations,
 * nothing to wait on.
 *
 * The sale only ever touches the server at two points: [holdOrder] (queues
 * the lines with zero payment legs — the created invoice is left open,
 * unpaid) and a completed payment ([submitPayment], one leg for a plain
 * sale or several accumulated legs for a split payment — see
 * [PaymentUiState.legs]). Both go through [OutboxRepository.enqueueSale],
 * which is now the ONLY way an invoice is ever created (see
 * [com.zedread.pos.data.sync.OutboxOperation]'s doc) — not an offline
 * fallback anymore. Whether that queued row drains in milliseconds (online)
 * or after connectivity returns (offline) is invisible here; both cases are
 * silent from the cashier's perspective by construction, since nothing
 * blocks on the network to get this far.
 */
@HiltViewModel
class SellViewModel @Inject constructor(
    private val catalogRepo: CatalogRepository,
    private val outboxRepo: OutboxRepository,
    private val menuLayoutRepo: MenuLayoutRepository,
    private val settingsRepo: SettingsRepository,
) : ViewModel() {

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

    /** The currently selected menu layout's full detail (tabs/buttons), or null when none is selected/available. */
    val currentMenuLayout: StateFlow<PosMenuLayoutDto?> =
        combine(_menuLayouts, _selectedMenuLayoutId) { layouts, id -> layouts.firstOrNull { it.id == id } }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Folder navigation — which tab's buttons the grid is currently showing. Null means "not yet drilled into a folder". */
    private val _selectedTabId = MutableStateFlow<String?>(null)

    /**
     * The tab the grid actually renders: [_selectedTabId] if it's still a
     * tab of the current layout, else the layout's first top-level (rail)
     * tab — so switching layouts (or a layout losing the tab you were in)
     * naturally resets to the top without any manual reset call needed.
     */
    val effectiveTabId: StateFlow<String?> =
        combine(currentMenuLayout, _selectedTabId) { layout, tabId ->
            when {
                layout == null -> null
                tabId != null && layout.tabs.any { it.id == tabId } -> tabId
                else -> layout.topLevelTabs.firstOrNull()?.id
            }
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Switch the rail tab, or drill into/out of a folder tile's nested tab. */
    fun selectTab(tabId: String?) { _selectedTabId.value = tabId }

    /**
     * Fetch the site's active layouts — called once at construction (the
     * one-time sync; see CatalogRepository/SettingsRepository's own docs on
     * the same architecture) rather than on every screen action. The
     * current selection is kept if it's still among the active set,
     * falling back to the schedule's own default only if it's gone.
     * Failure is silent — the grid already falls back to the unfiltered
     * catalog when no layout resolves, so a network hiccup here never
     * blocks a sale.
     */
    fun refreshMenuLayouts() {
        viewModelScope.launch {
            runCatching { menuLayoutRepo.getMenuLayouts() }
                .onSuccess { layouts ->
                    _menuLayouts.value = layouts
                    val keepCurrent = layouts.any { it.id == _selectedMenuLayoutId.value }
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

    /**
     * Every cached product, unfiltered — used only to resolve a menu-grid
     * product tile's product_ref back to a local product id on tap
     * ([addToCartByRef]). [products] above is category/menu-filtered for
     * display, which isn't what a tap handler needs.
     *
     * [SharingStarted.Eagerly], not WhileSubscribed like every other flow in
     * this class — nothing ever calls .collect() on [allProducts] itself (it's
     * only ever read via its plain .value property from addToCart/
     * addToCartByRef/productByRef), and a StateFlow.value read does not count
     * as subscribing. Under WhileSubscribed the upstream Room flow would
     * therefore never start, leaving .value permanently stuck at the initial
     * emptyList() — every tap on a product tile silently failing to add to
     * the order, since the ref/id lookup below always came back null. Fixed
     * in user testing as "buttons are not selectable and cannot add to the
     * order".
     */
    private val allProducts: StateFlow<List<ProductEntity>> =
        catalogRepo.observeProducts(null).stateIn(viewModelScope, SharingStarted.Eagerly, emptyList())

    /** Resolve a menu-grid tile's product_ref to its cached product — used by [addToCartByRef] and the long-press popup. */
    private fun productByRef(productRef: String): ProductEntity? =
        allProducts.value.firstOrNull { it.ref == productRef }

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

    // ── Auto Menu (Menu Studio "auto_menu_enabled" backend setting) ─────────
    //
    // Per user-testing feedback, the Register's menu selector should only
    // offer an unfiltered "All items" option when a site/brand has this
    // setting turned on from Menu Studio's POS Layout tab — otherwise staff
    // may only browse the layouts actually published from Menu Studio.

    private val _isAutoMenuEnabled = MutableStateFlow(false)
    val isAutoMenuEnabled: StateFlow<Boolean> = _isAutoMenuEnabled.asStateFlow()

    private fun refreshAutoMenuSetting() {
        viewModelScope.launch {
            runCatching { settingsRepo.getSettings() }
                .onSuccess { settings ->
                    _isAutoMenuEnabled.value = settings
                        .firstOrNull { it.key == SettingKeys.AUTO_MENU_ENABLED }
                        ?.effectiveValue as? Boolean ?: false
                }
        }
    }

    init { refresh(); refreshMenuLayouts(); refreshAutoMenuSetting() }

    // ── Product detail popup (long-press) ────────────────────────────────────
    //
    // Press-and-hold on a product tile — either grid — pops up a window
    // showing the product's short description and a sold-out toggle. Always
    // opens, sold-out or not, so staff can press-and-hold a sold-out tile to
    // clear it again (a plain tap on a sold-out tile is blocked in
    // [addToCart] instead, never reaching this popup).

    private val _productDetailId = MutableStateFlow<String?>(null)

    /** The product currently shown in the long-press popup, or null when closed. Resolved live from [allProducts] so a toggle is reflected immediately. */
    val productDetail: StateFlow<ProductEntity?> =
        combine(_productDetailId, allProducts) { id, all -> all.firstOrNull { it.id == id } }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    private val _soldOutActionError = MutableStateFlow<String?>(null)
    val soldOutActionError: StateFlow<String?> = _soldOutActionError.asStateFlow()

    /** Open the long-press popup for a product already resolved to a local id (category-based grid tiles). */
    fun openProductDetail(productId: String) {
        _soldOutActionError.value = null
        _productDetailId.value = productId
    }

    /** Open the long-press popup from a menu-grid tile's product_ref. */
    fun openProductDetailByRef(productRef: String) {
        productByRef(productRef)?.let { openProductDetail(it.id) }
    }

    fun closeProductDetail() {
        _productDetailId.value = null
    }

    /**
     * Flip the currently-open popup's product between sold-out and
     * available. Pushes to the backend first ([CatalogRepository.setSoldOut]
     * already patches the local cache from the confirmed response) — on
     * failure the cache is left untouched and an error is surfaced in the
     * popup rather than optimistically toggling, since a silent local-only
     * flip would let staff believe a sold-out item is sellable again when
     * the backend never actually heard about it.
     */
    fun toggleSoldOut() {
        val product = productDetail.value ?: return
        _soldOutActionError.value = null
        viewModelScope.launch {
            runCatching { catalogRepo.setSoldOut(product.id, !product.isSoldOut) }
                .onFailure { e -> _soldOutActionError.value = e.message ?: "Failed to update product" }
        }
    }

    // ── Cart (built entirely on-device — see the class doc) ─────────────────

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

    // Retained for the modifier sheet's own Loading/Ready/Closed states
    // (see ModifierSheetState below) and as a defensive surface for the
    // vanishingly-rare local Room failure — cart mutations themselves are
    // synchronous and don't set this to Loading (there's nothing to wait on).
    private val _cartActionState = MutableStateFlow<CartActionState>(CartActionState.Idle)
    val cartActionState: StateFlow<CartActionState> = _cartActionState.asStateFlow()

    /**
     * Tap a product tile. A sold-out product ([ProductEntity.isSoldOut] — set
     * from this same tile's long-press popup, see [openProductDetail]) never
     * adds to the order, matching the backend's own catalog state; a product
     * with a modifier set — [ProductEntity.modifierNames] non-blank, the same
     * field that backs the grid's "+" badge — opens the customise sheet
     * instead of adding directly; a plain product adds straight to the
     * order, same as before. Purely local — see [addLocalLine].
     */
    fun addToCart(productId: String) {
        val product = allProducts.value.firstOrNull { it.id == productId } ?: return
        if (product.isSoldOut) return
        if (!product.modifierNames.isNullOrBlank()) {
            openModifierSheet(product)
            return
        }
        addLocalLine(productId, quantity = 1, modifiers = emptyList())
    }

    /** Menu-grid tile tap — resolves the tile's product_ref to its locally-cached product, then behaves like [addToCart]. */
    fun addToCartByRef(productRef: String) {
        val product = productByRef(productRef) ?: return
        addToCart(product.id)
    }

    /**
     * Build and append a line item entirely on-device — no network call, no
     * loading state. [computeLocalLineTax] mirrors the backend's own
     * add_line_item() formula exactly, so the totals shown here match what
     * the server will compute once the sale is actually created (at Hold or
     * Pay — see the class doc).
     */
    private fun addLocalLine(productId: String, quantity: Int, modifiers: List<ModifierGroupSelection>) {
        val product = allProducts.value.firstOrNull { it.id == productId } ?: return
        if (_ticketNumber.value == null) issueTicketNumber()
        val lineId = UUID.randomUUID().toString()
        val tax = computeLocalLineTax(product, quantity)
        val item = LineItemDto(
            id = lineId,
            productId = product.id,
            productName = product.name,
            quantity = quantity,
            unitPriceCents = tax.unitPriceCents,
            subtotalCents = tax.subtotalCents,
            taxCents = tax.taxCents,
            modifiers = resolveModifierDtos(lineId, modifiers),
        )
        _lineItems.value = _lineItems.value + item
    }

    /**
     * Flatten a modifier sheet's selections into [LineModifierDto] rows —
     * same attach rule at both nesting levels (single-select groups always
     * attach their one choice; multi-select only when it costs extra), just
     * applied one level deeper for a linked ("comboed") group. Ported from
     * the sheet's own online-confirm logic now that this is the only path —
     * unlike the old offline fallback, linked selections are NOT dropped
     * here; that shortcut was only acceptable for a rare emergency path, not
     * the everyday one.
     */
    private fun resolveModifierDtos(lineId: String, groups: List<ModifierGroupSelection>): List<LineModifierDto> {
        data class Chosen(val id: String, val name: String, val priceDeltaCents: Long)
        val chosen = mutableListOf<Chosen>()
        groups.forEach { gs ->
            gs.selected.forEach { idx ->
                val option = gs.group.options.getOrNull(idx) ?: return@forEach
                if (gs.isSingleSelect || option.priceDeltaCents > 0) {
                    chosen += Chosen(option.id, option.name, option.priceDeltaCents)
                }
                gs.linkedSelections[idx].orEmpty().forEach { linked ->
                    linked.selected.forEach linkedLoop@{ linkedIdx ->
                        val linkedOption = linked.group.options.getOrNull(linkedIdx) ?: return@linkedLoop
                        if (linked.isSingleSelect || linkedOption.priceDeltaCents > 0) {
                            chosen += Chosen(linkedOption.id, linkedOption.name, linkedOption.priceDeltaCents)
                        }
                    }
                }
            }
        }
        return chosen.map { c ->
            LineModifierDto(
                id = UUID.randomUUID().toString(),
                lineItemId = lineId,
                modifierOptionId = c.id,
                modifierName = c.name,
                priceDeltaCents = c.priceDeltaCents,
            )
        }
    }

    /** This cart's lines in the shape the outbox queues — used by [holdOrder] and [submitPayment]. */
    private fun buildOutboxLines(): List<OutboxSaleLine> = _lineItems.value.map { item ->
        OutboxSaleLine(
            productId = item.productId ?: error("Line item is missing its product id"),
            quantity = item.quantity,
            modifierOptionIds = item.modifiers.mapNotNull { it.modifierOptionId },
        )
    }

    /**
     * Change a line's quantity via the Register screen's qty stepper.
     * Dropping to 0 removes the line entirely, same as tapping remove.
     * Purely local — re-derives tax/subtotal for the new quantity via
     * [computeLocalLineTax], same formula [addLocalLine] uses.
     */
    fun setLineQuantity(lineItemId: String, quantity: Int) {
        if (quantity < 1) { removeLine(lineItemId); return }
        _lineItems.value = _lineItems.value.map { item ->
            if (item.id != lineItemId) return@map item
            val product = allProducts.value.firstOrNull { it.id == item.productId }
                ?: return@map item.copy(quantity = quantity, subtotalCents = item.unitPriceCents * quantity)
            val tax = computeLocalLineTax(product, quantity)
            item.copy(quantity = quantity, unitPriceCents = tax.unitPriceCents, subtotalCents = tax.subtotalCents, taxCents = tax.taxCents)
        }
    }

    /** Remove a line from the order — purely local. */
    fun removeLine(lineItemId: String) {
        _lineItems.value = _lineItems.value.filterNot { it.id == lineItemId }
        if (_selectedLineItemId.value == lineItemId) _selectedLineItemId.value = null
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
                        val defaultLinked = defaultSelected.associateWith { idx ->
                            group.options.getOrNull(idx)?.linkedGroups.orEmpty().map(::defaultLinkedSelection)
                        }.filterValues { it.isNotEmpty() }
                        ModifierGroupSelection(group, defaultSelected, defaultLinked)
                    }
                    _modifierSheetState.value = ModifierSheetState.Ready(product, selections, quantity = 1)
                }
                .onFailure { e ->
                    // Modifier prices aren't cached locally (see CatalogRepository.getProductModifiers'
                    // doc — a deliberately deferred follow-up, not part of this round's local-first
                    // cart rework), so a customisable item genuinely can't be rung up offline; a
                    // plain item always can now — see addLocalLine.
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
        // Seed default linked-group selections the first time an option carrying
        // comboing links becomes selected — a previously-seeded entry for an
        // option no longer selected is left in place (harmless, see the doc).
        val newlySelected = newSelected - current.selected
        val newLinked = current.linkedSelections.toMutableMap()
        newlySelected.forEach { idx ->
            if (idx !in newLinked) {
                val linked = current.group.options.getOrNull(idx)?.linkedGroups.orEmpty().map(::defaultLinkedSelection)
                if (linked.isNotEmpty()) newLinked[idx] = linked
            }
        }
        groups[groupIndex] = current.copy(selected = newSelected, linkedSelections = newLinked)
        _modifierSheetState.value = state.copy(groups = groups)
    }

    /** Radio-style select for a single-select linked group, checkbox-style toggle for multi-select. */
    fun toggleLinkedChoice(groupIndex: Int, optionIndex: Int, linkedGroupIndex: Int, linkedOptionIndex: Int) {
        val state = _modifierSheetState.value as? ModifierSheetState.Ready ?: return
        val groups = state.groups.toMutableList()
        val current = groups.getOrNull(groupIndex) ?: return
        val linkedList = current.linkedSelections[optionIndex] ?: return
        val linkedGroup = linkedList.getOrNull(linkedGroupIndex) ?: return
        val newLinkedSelected = when {
            linkedGroup.isSingleSelect -> setOf(linkedOptionIndex)
            linkedGroup.selected.contains(linkedOptionIndex) -> linkedGroup.selected - linkedOptionIndex
            else -> linkedGroup.selected + linkedOptionIndex
        }
        val newLinkedList = linkedList.toMutableList()
        newLinkedList[linkedGroupIndex] = linkedGroup.copy(selected = newLinkedSelected)
        val newLinked = current.linkedSelections.toMutableMap()
        newLinked[optionIndex] = newLinkedList
        groups[groupIndex] = current.copy(linkedSelections = newLinked)
        _modifierSheetState.value = state.copy(groups = groups)
    }

    fun changeModifierSheetQuantity(delta: Int) {
        val state = _modifierSheetState.value as? ModifierSheetState.Ready ?: return
        _modifierSheetState.value = state.copy(quantity = (state.quantity + delta).coerceAtLeast(1))
    }

    fun closeModifierSheet() { _modifierSheetState.value = ModifierSheetState.Closed }

    /**
     * Per-unit price including selected modifiers and any selected comboed
     * (linked) options one level deep — mirrors modAddToOrder's live `unit`
     * calc, extended for comboing since the mockup predates it. The base
     * (pre-modifier) starting point uses [computeLocalLineTax]'s own
     * unitPriceCents rather than product.basePriceCents directly, so a
     * non-taxable product's preview here matches what it's actually charged
     * once added — basePriceCents alone is the taxable price only.
     */
    fun modifierSheetUnitPriceCents(state: ModifierSheetState.Ready): Long {
        var unit = computeLocalLineTax(state.product, 1).unitPriceCents
        state.groups.forEach { gs ->
            gs.selected.forEach { idx ->
                unit += gs.group.options.getOrNull(idx)?.priceDeltaCents ?: 0
                gs.linkedSelections[idx]?.forEach { linked ->
                    linked.selected.forEach { linkedIdx ->
                        unit += linked.group.options.getOrNull(linkedIdx)?.priceDeltaCents ?: 0
                    }
                }
            }
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
        _modifierSheetState.value = ModifierSheetState.Closed
        addLocalLine(state.product.id, state.quantity, modifiers = state.groups)
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
     * Clears the order pane back to empty — the ✕ "clear order" action, and
     * also what [holdOrder] and a completed payment's "New order" button
     * reset to once their own work is done. Clearing on its own never
     * touches the server or the sync queue — a plain ✕ discards a cart that
     * was never created anywhere in the first place, since nothing is
     * created until Hold or Pay (see the class doc).
     */
    fun clearOrder() {
        _lineItems.value = emptyList()
        _ticketNumber.value = null
        _selectedLineItemId.value = null
        _paymentState.value = null
    }

    /**
     * Hold — queues the cart as an unpaid sale (zero payment legs, see
     * [OutboxRepository.enqueueSale]) and clears the order pane once it's
     * queued. The resulting invoice is created and left OPEN on the server,
     * same as before this round's rework, just via the sync queue instead
     * of a live call — still no "recall a held order" list on this device
     * (a manager can find it via the portal's invoice reports), a known,
     * flagged gap rather than something this round silently drops.
     */
    fun holdOrder() {
        if (_lineItems.value.isEmpty()) { clearOrder(); return }
        val lines = buildOutboxLines()
        val total = totalCents
        viewModelScope.launch {
            runCatching { outboxRepo.enqueueSale(lines = lines, payments = emptyList(), isPaid = false, totalCents = total) }
                .onSuccess { clearOrder() }
                .onFailure { e -> _cartActionState.value = CartActionState.Error(e.message ?: "Couldn't hold this order") }
        }
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

    /**
     * Record one payment leg locally. A plain (non-split) sale's single leg
     * always covers the full remaining amount, so this both accumulates the
     * leg AND — once [PaymentUiState.legs] fully covers [totalCents] —
     * enqueues the whole sale (lines + every leg so far) as one outbox
     * bundle via [OutboxRepository.enqueueSale]. A split leg that doesn't
     * yet cover the balance is recorded and the modal resets to a fresh
     * Choosing state with the running total carried over, same as before
     * this round's rework — the only change is that split payment now works
     * regardless of connectivity, since nothing here depends on the network
     * (the old restriction blocking split mode once offline is gone).
     */
    private fun submitPayment(method: String, amountCents: Long, reference: String?) {
        val current = _paymentState.value ?: return
        if (amountCents <= 0) {
            _paymentState.value = current.copy(errorMessage = "Enter an amount")
            return
        }
        val leg = SyncPaymentLeg(method, amountCents, reference)
        val updatedLegs = current.legs + leg
        val updatedPaidCents = current.paidCents + amountCents
        // Change is whatever this payment overshot the balance that was
        // still due before it — 0 for card/voucher, and for a non-split
        // cash tender this is exactly amountCents - remaining. Computable
        // locally now (unlike before this round), since totalCents is
        // itself always locally correct — see LocalTaxCalculator.
        val dueBeforeThisPayment = totalCents - current.paidCents
        val change = (amountCents - dueBeforeThisPayment).coerceAtLeast(0)

        if (updatedPaidCents < totalCents) {
            _paymentState.value = PaymentUiState(paidCents = updatedPaidCents, legs = updatedLegs)
            return
        }

        val lines = buildOutboxLines()
        val total = totalCents
        _paymentState.value = current.copy(isSubmitting = true, errorMessage = null)
        viewModelScope.launch {
            runCatching { outboxRepo.enqueueSale(lines = lines, payments = updatedLegs, isPaid = true, totalCents = total) }
                .onSuccess {
                    _paymentState.value = current.copy(
                        stage = PaymentStage.DONE,
                        isSubmitting = false,
                        paidCents = updatedPaidCents,
                        legs = updatedLegs,
                        doneMethodLabel = method.replaceFirstChar { it.uppercase() },
                        doneAmountCents = total,
                        doneChangeCents = if (method == "cash") change else 0L,
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
        // Drop back to the schedule's own default, discarding any manual
        // menu-selector override for the sale that just finished — resolved
        // from the already-cached layout list, not a fresh network call.
        // Per the one-time-sync architecture (see CatalogRepository/
        // SettingsRepository's own docs), catalog/menu-layout data syncs
        // once and is read locally thereafter; only invoices and register
        // open/close talk to the server in real time. A sale completing is
        // exactly the kind of frequent, per-action event that must not
        // trigger its own round trip.
        _selectedMenuLayoutId.value = _menuLayouts.value.firstOrNull { it.isEffectiveDefault }?.id
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

/**
 * One modifier group's option list plus which option indices are currently selected.
 *
 * linkedSelections carries "comboing" state: keyed by the top-level option
 * index that owns the link, one [LinkedGroupSelection] per group that
 * option links to (same order as that option's own linkedGroups list — one
 * level of nesting only, matching the backend). Entries persist even after
 * their owning option is deselected (harmless — the sheet only ever renders
 * a currently-selected option's linked blocks) rather than being pruned on
 * every toggle.
 */
data class ModifierGroupSelection(
    val group: ProductModifierGroupDto,
    val selected: Set<Int>,
    val linkedSelections: Map<Int, List<LinkedGroupSelection>> = emptyMap(),
) {
    /** Radio-style (at most 1 choice) vs checkbox-style (multiple) — mirrors the mockup's g.type. */
    val isSingleSelect: Boolean get() = group.maxSelections <= 1
    val isRequired: Boolean get() = group.minSelections >= 1
}

/** A linked ("combo") group's own option list plus which option indices are currently selected. */
data class LinkedGroupSelection(
    val group: LinkedGroupDto,
    val selected: Set<Int>,
) {
    val isSingleSelect: Boolean get() = group.maxSelections <= 1
    val isRequired: Boolean get() = group.minSelections >= 1
}

/** Default selection for a linked group when its owning option is first selected — mirrors the top-level default rule. */
private fun defaultLinkedSelection(group: LinkedGroupDto): LinkedGroupSelection =
    LinkedGroupSelection(group, if (group.maxSelections <= 1 && group.options.isNotEmpty()) setOf(0) else emptySet())

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
    /** Every payment leg confirmed so far this sale — enqueued together, once, when they fully cover the total. See SellViewModel.submitPayment. */
    val legs: List<SyncPaymentLeg> = emptyList(),
    val isSubmitting: Boolean = false,
    val errorMessage: String? = null,
    val doneMethodLabel: String = "",
    val doneAmountCents: Long = 0L,
    val doneChangeCents: Long = 0L,
)
