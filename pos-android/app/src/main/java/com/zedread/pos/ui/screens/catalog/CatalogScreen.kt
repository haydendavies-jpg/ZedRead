package com.zedread.pos.ui.screens.catalog

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.viewmodel.CatalogViewModel
import com.zedread.pos.ui.viewmodel.InvoiceCreateState

/** Product catalog screen — category tabs + product grid, pull-to-refresh. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CatalogScreen(
    onProceedToCart: (invoiceId: String) -> Unit,
    viewModel: CatalogViewModel = hiltViewModel(),
) {
    val categories by viewModel.categories.collectAsState()
    val products by viewModel.products.collectAsState()
    val selectedCatId by viewModel.selectedCategoryId.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()
    val invoiceState by viewModel.invoiceUiState.collectAsState()

    LaunchedEffect(invoiceState) {
        if (invoiceState is InvoiceCreateState.Created) {
            onProceedToCart((invoiceState as InvoiceCreateState.Created).invoiceId)
            viewModel.resetInvoiceState()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Menu") })
        },
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .padding(innerPadding)
                .fillMaxSize(),
        ) {
            // ── Category tabs ────────────────────────────────────────────────
            val allTabIndex = 0
            val selectedIndex = if (selectedCatId == null) 0
                                else categories.indexOfFirst { it.id == selectedCatId } + 1

            ScrollableTabRow(selectedTabIndex = selectedIndex) {
                Tab(
                    selected = selectedCatId == null,
                    onClick = { viewModel.selectCategory(null) },
                    text = { Text("All") },
                )
                categories.forEach { cat ->
                    Tab(
                        selected = selectedCatId == cat.id,
                        onClick = { viewModel.selectCategory(cat.id) },
                        text = { Text(cat.name) },
                    )
                }
            }

            // ── Product grid with pull-to-refresh ────────────────────────────
            PullToRefreshBox(
                isRefreshing = isRefreshing,
                onRefresh = { viewModel.refresh() },
                modifier = Modifier.fillMaxSize(),
            ) {
                if (products.isEmpty() && !isRefreshing) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("No products available", style = MaterialTheme.typography.bodyLarge)
                    }
                } else {
                    LazyVerticalGrid(
                        columns = GridCells.Adaptive(160.dp),
                        contentPadding = PaddingValues(8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(products) { product ->
                            ProductCard(
                                name = product.name,
                                priceCents = product.basePriceCents,
                                onClick = {
                                    // Tapping any product opens a draft invoice.
                                    viewModel.startInvoice()
                                },
                            )
                        }
                    }
                }

                if (invoiceState is InvoiceCreateState.Loading) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
            }
        }
    }
}

/** Single product tile in the grid. */
@Composable
private fun ProductCard(
    name: String,
    priceCents: Long,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Column(Modifier.padding(12.dp)) {
            Text(name, style = MaterialTheme.typography.titleSmall)
            Text(
                formatCents(priceCents),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.primary,
            )
        }
    }
}

/** Format a cent value as a dollar string (e.g. 1099 → "$10.99"). */
private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
