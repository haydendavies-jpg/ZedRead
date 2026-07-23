package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.InvoiceDto
import com.zedread.pos.data.repository.InvoiceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Held Orders tab: this site's OPEN invoices (line items added, never paid —
 * exactly what [com.zedread.pos.ui.viewmodel.SellViewModel.holdOrder] leaves
 * behind) so staff can recall and finish one. Always fetched fresh on open
 * (no local cache) — held orders can be created from any device at the site,
 * not just this one, so a stale list would risk showing an order someone
 * else already recalled and paid off elsewhere.
 */
@HiltViewModel
class HeldOrdersViewModel @Inject constructor(
    private val invoiceRepo: InvoiceRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<HeldOrdersUiState>(HeldOrdersUiState.Loading)
    val state: StateFlow<HeldOrdersUiState> = _state.asStateFlow()

    fun refresh() {
        _state.value = HeldOrdersUiState.Loading
        viewModelScope.launch {
            runCatching { invoiceRepo.listInvoices(limit = 100, status = "open") }
                .onSuccess { _state.value = HeldOrdersUiState.Ready(it) }
                .onFailure { e -> _state.value = HeldOrdersUiState.Error(e.message ?: "Couldn't load held orders") }
        }
    }
}

sealed class HeldOrdersUiState {
    object Loading : HeldOrdersUiState()
    data class Ready(val orders: List<InvoiceDto>) : HeldOrdersUiState()
    data class Error(val message: String) : HeldOrdersUiState()
}
