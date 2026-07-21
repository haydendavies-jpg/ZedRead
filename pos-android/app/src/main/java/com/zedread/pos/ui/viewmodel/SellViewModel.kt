package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.ProductEntity
import com.zedread.pos.data.repository.CatalogRepository
import com.zedread.pos.data.repository.InvoiceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Owns one sale end to end: browsing the catalog, building the cart, and
 * taking payment. Scoped to the "sell" nav sub-graph (Catalog/Cart/Payment
 * share one instance via `hiltViewModel(navController.getBackStackEntry(...))`)
 * so the cart survives navigating between those screens — there is no
 * `GET /invoices/{id}/line-items` to reconstruct it from if each screen held
 * its own short-lived ViewModel instead.
 */
@HiltViewModel
class SellViewModel @Inject constructor(
    private val catalogRepo: CatalogRepository,
    private val invoiceRepo: InvoiceRepository,
) : ViewModel() {

    // ── Category / product browsing ─────────────────────────────────────────

    /** null = "All" tab showing every product. */
    private val _selectedCategoryId = MutableStateFlow<String?>(null)
    val selectedCategoryId: StateFlow<String?> = _selectedCategoryId.asStateFlow()

    val categories: StateFlow<List<CategoryEntity>> =
        catalogRepo.observeCategories()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun selectCategory(categoryId: String?) { _selectedCategoryId.value = categoryId }

    val products: StateFlow<List<ProductEntity>> =
        _selectedCategoryId
            .flatMapLatest { catId -> catalogRepo.observeProducts(catId) }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

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

    init { refresh() }

    // ── Cart (the current sale's invoice) ───────────────────────────────────

    /** The draft invoice this sale is building, created lazily on the first item added. */
    private var currentInvoiceId: String? = null

    private val _lineItems = MutableStateFlow<List<LineItemDto>>(emptyList())
    val lineItems: StateFlow<List<LineItemDto>> = _lineItems.asStateFlow()

    /** Computed total in cents across all line items (subtotal + tax). */
    val totalCents: Long get() = _lineItems.value.sumOf { it.subtotalCents + it.taxCents }

    private val _cartActionState = MutableStateFlow<CartActionState>(CartActionState.Idle)
    val cartActionState: StateFlow<CartActionState> = _cartActionState.asStateFlow()

    /** Add a product to this sale — opens the draft invoice first if this is the first item. */
    fun addToCart(productId: String) {
        _cartActionState.value = CartActionState.Loading
        viewModelScope.launch {
            runCatching {
                val invoiceId = currentInvoiceId
                    ?: invoiceRepo.createInvoice().id.also { currentInvoiceId = it; issueTicketNumber() }
                invoiceRepo.addLineItem(invoiceId, productId, quantity = 1)
            }
                .onSuccess { item ->
                    _lineItems.value = _lineItems.value + item
                    _cartActionState.value = CartActionState.Idle
                }
                .onFailure { e -> _cartActionState.value = CartActionState.Error(e.message ?: "Failed to add item") }
        }
    }

    /**
     * Change a line's quantity via the Register screen's qty stepper.
     * Dropping to 0 removes the line entirely, same as tapping remove.
     */
    fun setLineQuantity(lineItemId: String, quantity: Int) {
        if (quantity < 1) { removeLine(lineItemId); return }
        val invoiceId = currentInvoiceId ?: return
        _cartActionState.value = CartActionState.Loading
        viewModelScope.launch {
            runCatching { invoiceRepo.updateLineItemQuantity(invoiceId, lineItemId, quantity) }
                .onSuccess { updated ->
                    _lineItems.value = _lineItems.value.map { if (it.id == lineItemId) updated else it }
                    _cartActionState.value = CartActionState.Idle
                }
                .onFailure { e -> _cartActionState.value = CartActionState.Error(e.message ?: "Failed to update quantity") }
        }
    }

    /** Remove a line from the order. */
    fun removeLine(lineItemId: String) {
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
     * ✕ and Hold action. The invoice itself (if any items were added) is
     * NOT voided or deleted here; it's simply left open/uncollected on the
     * backend. There's no "recall a held order" list yet to bring it back —
     * that's a real gap Hold leaves open, flagged rather than silently
     * dropped.
     */
    fun clearOrder() {
        currentInvoiceId = null
        _lineItems.value = emptyList()
        _ticketNumber.value = null
        _selectedLineItemId.value = null
        paidCents = 0L
    }

    // ── Payment ──────────────────────────────────────────────────────────────

    private val _paymentState = MutableStateFlow<PaymentFlowState>(PaymentFlowState.Idle)
    val paymentState: StateFlow<PaymentFlowState> = _paymentState.asStateFlow()

    /** Running tally of cents already paid via earlier split payments. */
    private var paidCents: Long = 0L

    /**
     * Submit a single payment or one leg of a split payment.
     * Automatically flags [PaymentFlowState.Complete] when the total is covered.
     */
    fun pay(method: String, amountCents: Long) {
        val invoiceId = currentInvoiceId
        if (invoiceId == null) {
            _paymentState.value = PaymentFlowState.Error("No open sale to pay")
            return
        }
        _paymentState.value = PaymentFlowState.Loading
        viewModelScope.launch {
            runCatching { invoiceRepo.pay(invoiceId, method, amountCents) }
                .onSuccess { dto ->
                    paidCents += amountCents
                    _paymentState.value = when (dto.status) {
                        "paid" -> PaymentFlowState.Complete(dto.id)
                        else -> PaymentFlowState.PartiallyPaid(
                            paidCents = paidCents,
                            remainingCents = totalCents - paidCents,
                        )
                    }
                }
                .onFailure { e -> _paymentState.value = PaymentFlowState.Error(e.message ?: "Payment failed") }
        }
    }

    fun resetPaymentError() { if (_paymentState.value is PaymentFlowState.Error) _paymentState.value = PaymentFlowState.Idle }
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

sealed class PaymentFlowState {
    object Idle : PaymentFlowState()
    object Loading : PaymentFlowState()
    data class PartiallyPaid(val paidCents: Long, val remainingCents: Long) : PaymentFlowState()
    data class Complete(val invoiceId: String) : PaymentFlowState()
    data class Error(val message: String) : PaymentFlowState()
}
