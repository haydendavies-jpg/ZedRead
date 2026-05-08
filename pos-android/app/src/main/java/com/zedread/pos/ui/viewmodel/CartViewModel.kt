package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.LineItemDto
import com.zedread.pos.data.repository.InvoiceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Manages the cart / invoice builder screen: line items, payment, total display. */
@HiltViewModel
class CartViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val invoiceRepo: InvoiceRepository,
) : ViewModel() {

    /** Invoice ID injected from nav back-stack entry. */
    val invoiceId: String = checkNotNull(savedStateHandle["invoiceId"]) {
        "CartViewModel requires invoiceId in SavedStateHandle"
    }

    // ── Line items ─────────────────────────────────────────────────────────────

    private val _lineItems = MutableStateFlow<List<LineItemDto>>(emptyList())
    val lineItems: StateFlow<List<LineItemDto>> = _lineItems.asStateFlow()

    /** Computed total across all line items (subtotal + tax). */
    val totalCents: Long
        get() = _lineItems.value.sumOf { it.subtotalCents + it.taxCents }

    // ── Add item state ─────────────────────────────────────────────────────────

    private val _addItemState = MutableStateFlow<AddItemState>(AddItemState.Idle)
    val addItemState: StateFlow<AddItemState> = _addItemState.asStateFlow()

    /** Add a product to the open invoice. Appends to [lineItems] on success. */
    fun addItem(productId: String, quantity: Int = 1, modifierIds: List<String> = emptyList()) {
        _addItemState.value = AddItemState.Loading
        viewModelScope.launch {
            runCatching {
                invoiceRepo.addLineItem(invoiceId, productId, quantity, modifierIds)
            }
                .onSuccess { item ->
                    _lineItems.value = _lineItems.value + item
                    _addItemState.value = AddItemState.Done
                }
                .onFailure { e ->
                    _addItemState.value = AddItemState.Error(e.message ?: "Failed to add item")
                }
        }
    }

    fun resetAddItemState() { _addItemState.value = AddItemState.Idle }

    // ── Payment state ──────────────────────────────────────────────────────────

    private val _paymentState = MutableStateFlow<PaymentState>(PaymentState.Idle)
    val paymentState: StateFlow<PaymentState> = _paymentState.asStateFlow()

    /** Pay the invoice. For split payments, call with partial amounts; final call completes. */
    fun pay(method: String, amountCents: Long) {
        _paymentState.value = PaymentState.Loading
        viewModelScope.launch {
            runCatching { invoiceRepo.pay(invoiceId, method, amountCents) }
                .onSuccess { dto ->
                    _paymentState.value = if (dto.status == "paid") PaymentState.Complete
                                         else PaymentState.PartiallyPaid(dto.totalCents - dto.subtotalCents)
                }
                .onFailure { e ->
                    _paymentState.value = PaymentState.Error(e.message ?: "Payment failed")
                }
        }
    }
}

sealed class AddItemState {
    object Idle : AddItemState()
    object Loading : AddItemState()
    object Done : AddItemState()
    data class Error(val message: String) : AddItemState()
}

sealed class PaymentState {
    object Idle : PaymentState()
    object Loading : PaymentState()
    object Complete : PaymentState()
    data class PartiallyPaid(val remainingCents: Long) : PaymentState()
    data class Error(val message: String) : PaymentState()
}
