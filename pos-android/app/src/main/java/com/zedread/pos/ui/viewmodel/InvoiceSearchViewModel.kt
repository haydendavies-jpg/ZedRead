package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import com.zedread.pos.data.repository.InvoiceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit
import javax.inject.Inject

/**
 * Invoice search/history: filterable (date range, status, payment method)
 * list reading the local Room cache, so it works offline. Each result
 * shows synced/pending state per item ([InvoiceCacheEntity.isSynced]).
 *
 * [refreshFromServer] backfills the cache from `GET /invoices` — best
 * effort, silently skipped if offline (the cache still serves whatever it
 * already has). Rows for sales still queued in the outbox are written
 * directly by [com.zedread.pos.data.repository.OutboxRepository] at
 * enqueue time, not by this refresh.
 */
@HiltViewModel
class InvoiceSearchViewModel @Inject constructor(
    private val invoiceRepo: InvoiceRepository,
) : ViewModel() {

    private val _statusFilter = MutableStateFlow<String?>(null)
    val statusFilter: StateFlow<String?> = _statusFilter.asStateFlow()

    private val _paymentMethodFilter = MutableStateFlow<String?>(null)
    val paymentMethodFilter: StateFlow<String?> = _paymentMethodFilter.asStateFlow()

    private val _dateRangeFilter = MutableStateFlow(DateRangeFilter.ALL)
    val dateRangeFilter: StateFlow<DateRangeFilter> = _dateRangeFilter.asStateFlow()

    /** Free-text search against the invoice's INV-000001-style ref — the "invoice number" a cashier actually knows. */
    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    fun setStatusFilter(status: String?) { _statusFilter.value = status }
    fun setPaymentMethodFilter(method: String?) { _paymentMethodFilter.value = method }
    fun setDateRangeFilter(range: DateRangeFilter) { _dateRangeFilter.value = range }
    fun setSearchQuery(query: String) { _searchQuery.value = query }

    val results: StateFlow<List<InvoiceCacheEntity>> =
        combine(_statusFilter, _paymentMethodFilter, _dateRangeFilter, _searchQuery) { status, method, range, query ->
            SearchParams(status, method, range, query)
        }
            .flatMapLatest { params ->
                val (from, to) = params.range.toMillisRange()
                invoiceRepo.searchCache(params.status, params.method, from, to, params.query.trim().ifBlank { null })
            }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /** Best-effort backfill from the server — a failure (e.g. offline) is swallowed, the cache just stays as-is. */
    fun refreshFromServer() {
        _isRefreshing.value = true
        viewModelScope.launch {
            runCatching { invoiceRepo.refreshCacheFromServer() }
            _isRefreshing.value = false
        }
    }

    // ── Row expand (click-to-show-line-items) ──────────────────────────────

    private val _expandedInvoiceId = MutableStateFlow<String?>(null)
    val expandedInvoiceId: StateFlow<String?> = _expandedInvoiceId.asStateFlow()

    /** invoiceId -> its line items, once fetched — cached for the lifetime of this ViewModel so re-collapsing/re-expanding a row doesn't re-fetch. */
    private val _lineItemsByInvoice = MutableStateFlow<Map<String, List<LineItemDto>>>(emptyMap())
    val lineItemsByInvoice: StateFlow<Map<String, List<LineItemDto>>> = _lineItemsByInvoice.asStateFlow()

    private val _lineItemsLoading = MutableStateFlow<Set<String>>(emptySet())
    val lineItemsLoading: StateFlow<Set<String>> = _lineItemsLoading.asStateFlow()

    /** Tap a row: expands it (fetching its line items if not already cached), or collapses it if it's already the expanded one. */
    fun toggleExpand(invoiceId: String) {
        _expandedInvoiceId.value = if (_expandedInvoiceId.value == invoiceId) null else invoiceId
        if (_expandedInvoiceId.value == invoiceId) loadLineItems(invoiceId)
    }

    private fun loadLineItems(invoiceId: String) {
        if (invoiceId in _lineItemsByInvoice.value) return
        _lineItemsLoading.value = _lineItemsLoading.value + invoiceId
        viewModelScope.launch {
            runCatching { invoiceRepo.getLineItems(invoiceId) }
                .onSuccess { lines -> _lineItemsByInvoice.value = _lineItemsByInvoice.value + (invoiceId to lines) }
            _lineItemsLoading.value = _lineItemsLoading.value - invoiceId
        }
    }

    // ── Refund ───────────────────────────────────────────────────────────

    private val _refundTarget = MutableStateFlow<InvoiceCacheEntity?>(null)
    val refundTarget: StateFlow<InvoiceCacheEntity?> = _refundTarget.asStateFlow()

    private val _isRefunding = MutableStateFlow(false)
    val isRefunding: StateFlow<Boolean> = _isRefunding.asStateFlow()

    private val _refundError = MutableStateFlow<String?>(null)
    val refundError: StateFlow<String?> = _refundError.asStateFlow()

    /** Opens the refund dialog for [invoice] — also fetches its line items (if not already cached) since the dialog's partial-refund mode needs them. */
    fun openRefundDialog(invoice: InvoiceCacheEntity) {
        _refundError.value = null
        _refundTarget.value = invoice
        loadLineItems(invoice.id)
    }

    fun dismissRefundDialog() {
        _refundTarget.value = null
        _refundError.value = null
    }

    /**
     * Submit the refund for [InvoiceSearchViewModel.refundTarget].
     * [lineItemIds] non-null and non-empty requests a partial refund of just
     * those lines; null/empty refunds the entire invoice. On success,
     * dismisses the dialog and re-syncs the cache so the row picks up
     * is_refunded=true (and, for a full refund, the paid-invoice search list
     * elsewhere already reflects the new refund invoice on its own next sync).
     */
    fun submitRefund(lineItemIds: List<String>?) {
        val invoice = _refundTarget.value ?: return
        _isRefunding.value = true
        _refundError.value = null
        viewModelScope.launch {
            runCatching { invoiceRepo.refund(invoice.id, lineItemIds) }
                .onSuccess {
                    _isRefunding.value = false
                    dismissRefundDialog()
                    refreshFromServer()
                }
                .onFailure { e ->
                    _isRefunding.value = false
                    _refundError.value = e.message ?: "Could not process refund"
                }
        }
    }

    init { refreshFromServer() }
}

/** Combine() intermediate — the four independent filter inputs to [InvoiceSearchViewModel.results]. */
private data class SearchParams(
    val status: String?,
    val method: String?,
    val range: DateRangeFilter,
    val query: String,
)

/** Quick date-range chips — a full date-picker is more chrome than this screen's first cut needs. */
enum class DateRangeFilter(val label: String) {
    ALL("All time"),
    TODAY("Today"),
    LAST_7_DAYS("Last 7 days"),
    LAST_30_DAYS("Last 30 days");

    fun toMillisRange(): Pair<Long?, Long?> {
        if (this == ALL) return null to null
        val now = System.currentTimeMillis()
        val days = when (this) {
            TODAY -> 1L
            LAST_7_DAYS -> 7L
            LAST_30_DAYS -> 30L
            ALL -> 0L
        }
        return (now - TimeUnit.DAYS.toMillis(days)) to now
    }
}
