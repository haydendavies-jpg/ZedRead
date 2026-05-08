package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.repository.InvoiceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Drives the dedicated payment screen — supports single, cash/card split, and exact-change flows. */
@HiltViewModel
class PaymentViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val invoiceRepo: InvoiceRepository,
) : ViewModel() {

    val invoiceId: String = checkNotNull(savedStateHandle["invoiceId"])

    /** Total amount due in cents, passed from cart screen. */
    val totalCents: Long = checkNotNull(savedStateHandle["totalCents"])

    private val _state = MutableStateFlow<PaymentFlowState>(PaymentFlowState.Idle)
    val state: StateFlow<PaymentFlowState> = _state.asStateFlow()

    /** Running tally of cents already paid via earlier split payments. */
    private var paidCents: Long = 0L

    /**
     * Submit a single payment or one leg of a split payment.
     * Automatically flags [PaymentFlowState.Complete] when total is covered.
     */
    fun pay(method: String, amountCents: Long) {
        _state.value = PaymentFlowState.Loading
        viewModelScope.launch {
            runCatching { invoiceRepo.pay(invoiceId, method, amountCents) }
                .onSuccess { dto ->
                    paidCents += amountCents
                    _state.value = when (dto.status) {
                        "paid" -> PaymentFlowState.Complete(dto.id)
                        else -> PaymentFlowState.PartiallyPaid(
                            paidCents = paidCents,
                            remainingCents = totalCents - paidCents,
                        )
                    }
                }
                .onFailure { e ->
                    _state.value = PaymentFlowState.Error(e.message ?: "Payment failed")
                }
        }
    }

    fun resetError() { if (_state.value is PaymentFlowState.Error) _state.value = PaymentFlowState.Idle }
}

sealed class PaymentFlowState {
    object Idle : PaymentFlowState()
    object Loading : PaymentFlowState()
    data class PartiallyPaid(val paidCents: Long, val remainingCents: Long) : PaymentFlowState()
    data class Complete(val invoiceId: String) : PaymentFlowState()
    data class Error(val message: String) : PaymentFlowState()
}
