package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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

/** Drives the catalog screen: categories, products, refresh, and invoice creation. */
@HiltViewModel
class CatalogViewModel @Inject constructor(
    private val catalogRepo: CatalogRepository,
    private val invoiceRepo: InvoiceRepository,
) : ViewModel() {

    // ── Category selection ────────────────────────────────────────────────────

    /** null = "All" tab showing every product. */
    private val _selectedCategoryId = MutableStateFlow<String?>(null)
    val selectedCategoryId: StateFlow<String?> = _selectedCategoryId.asStateFlow()

    val categories: StateFlow<List<CategoryEntity>> =
        catalogRepo.observeCategories()
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun selectCategory(categoryId: String?) { _selectedCategoryId.value = categoryId }

    // ── Product list ──────────────────────────────────────────────────────────

    val products: StateFlow<List<ProductEntity>> =
        _selectedCategoryId
            .flatMapLatest { catId -> catalogRepo.observeProducts(catId) }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    // ── Refresh ───────────────────────────────────────────────────────────────

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

    // ── Invoice creation ──────────────────────────────────────────────────────

    private val _invoiceUiState = MutableStateFlow<InvoiceCreateState>(InvoiceCreateState.Idle)
    val invoiceUiState: StateFlow<InvoiceCreateState> = _invoiceUiState.asStateFlow()

    /** Open a draft invoice, then navigate to the cart. */
    fun startInvoice() {
        _invoiceUiState.value = InvoiceCreateState.Loading
        viewModelScope.launch {
            runCatching { invoiceRepo.createInvoice() }
                .onSuccess { dto -> _invoiceUiState.value = InvoiceCreateState.Created(dto.id) }
                .onFailure { e -> _invoiceUiState.value = InvoiceCreateState.Error(e.message ?: "Failed to create invoice") }
        }
    }

    fun resetInvoiceState() { _invoiceUiState.value = InvoiceCreateState.Idle }

    init { refresh() }
}

sealed class InvoiceCreateState {
    object Idle : InvoiceCreateState()
    object Loading : InvoiceCreateState()
    data class Created(val invoiceId: String) : InvoiceCreateState()
    data class Error(val message: String) : InvoiceCreateState()
}
