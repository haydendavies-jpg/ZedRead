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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.viewmodel.CartActionState
import com.zedread.pos.ui.viewmodel.SellViewModel

/** Product catalog screen — category tabs + product grid, pull-to-refresh, switch-user icon. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CatalogScreen(
    onProceedToCart: () -> Unit,
    onSwitchUser: () -> Unit,
    viewModel: SellViewModel = hiltViewModel(),
) {
    val categories by viewModel.categories.collectAsState()
    val products by viewModel.products.collectAsState()
    val selectedCatId by viewModel.selectedCategoryId.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()
    val lineItems by viewModel.lineItems.collectAsState()
    val cartActionState by viewModel.cartActionState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Menu") },
                actions = {
                    IconButton(onClick = onSwitchUser) {
                        Icon(Icons.Default.Person, contentDescription = "Switch operator")
                    }
                },
            )
        },
        bottomBar = {
            if (lineItems.isNotEmpty()) {
                Button(
                    onClick = onProceedToCart,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                ) {
                    Text("View Cart — ${lineItems.size} item${if (lineItems.size == 1) "" else "s"} · ${formatCents(viewModel.totalCents)}")
                }
            }
        },
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .padding(innerPadding)
                .fillMaxSize(),
        ) {
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

            if (cartActionState is CartActionState.Error) {
                Text(
                    (cartActionState as CartActionState.Error).message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }

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
                                onClick = { viewModel.addToCart(product.id) },
                            )
                        }
                    }
                }

                if (cartActionState is CartActionState.Loading) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
            }
        }
    }
}

@Composable
private fun ProductCard(name: String, priceCents: Long, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Column(Modifier.padding(12.dp)) {
            Text(name, style = MaterialTheme.typography.titleSmall)
            Text(formatCents(priceCents), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
        }
    }
}

private fun formatCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
