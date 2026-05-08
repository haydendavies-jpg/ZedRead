package com.zedread.pos.ui.screens.auth

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.viewmodel.AuthViewModel
import com.zedread.pos.ui.viewmodel.SiteUiState

/** Displays the list of sites returned after login — operator picks their active site. */
@Composable
fun SiteSelectorScreen(
    onSiteSelected: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val siteState by viewModel.siteUiState.collectAsState()
    val sites = viewModel.sitesFromLogin()

    LaunchedEffect(siteState) {
        if (siteState is SiteUiState.Done) onSiteSelected()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
    ) {
        Text("Select Site", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(16.dp))

        if (siteState is SiteUiState.Error) {
            Text(
                text = (siteState as SiteUiState.Error).message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
            Spacer(Modifier.height(8.dp))
        }

        if (siteState is SiteUiState.Loading) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn {
                items(sites.filter { it.isActive }) { site ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp)
                            .clickable { viewModel.selectSite(site.id) },
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(site.name, style = MaterialTheme.typography.titleMedium)
                        }
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}
