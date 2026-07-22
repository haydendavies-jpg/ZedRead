package com.zedread.pos.ui.screens.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.api.SettingDto
import com.zedread.pos.ui.viewmodel.SettingsUiState
import com.zedread.pos.ui.viewmodel.SettingsViewModel

/**
 * Read-only, searchable list of every setting resolved for this terminal's
 * site — booleans, datetimes, single/multi-select. Overrides are managed
 * from the management portal's Settings page, not here; this screen exists
 * so a cashier or manager can check what's currently in effect without
 * needing portal access.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    val search by viewModel.search.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            OutlinedTextField(
                value = search,
                onValueChange = viewModel::setSearch,
                label = { Text("Search settings") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            )

            when (val current = state) {
                is SettingsUiState.Loading -> {
                    Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator(modifier = Modifier.padding(top = 32.dp))
                    }
                }

                is SettingsUiState.Error -> {
                    Text(
                        current.message,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(16.dp),
                    )
                }

                is SettingsUiState.Ready -> {
                    val filtered = current.settings.filter { s -> matchesSearch(s, search) }
                    if (filtered.isEmpty()) {
                        Text(
                            "No settings match \"$search\".",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(16.dp),
                        )
                    } else {
                        LazyColumn(contentPadding = PaddingValues(bottom = 24.dp)) {
                            items(filtered, key = { it.key }) { setting ->
                                SettingRow(setting)
                                HorizontalDivider()
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun matchesSearch(setting: SettingDto, search: String): Boolean {
    if (search.isBlank()) return true
    val needle = search.trim().lowercase()
    return setting.key.lowercase().contains(needle) ||
        setting.label.lowercase().contains(needle) ||
        setting.category.lowercase().contains(needle)
}

@Composable
private fun SettingRow(setting: SettingDto) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(setting.label, fontWeight = FontWeight.Medium, style = MaterialTheme.typography.bodyLarge)
            Text(
                setting.category,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(
            formatSettingValue(setting.effectiveValue),
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/** Render a setting's effective value for display — the shape depends on its SettingType. */
private fun formatSettingValue(value: Any?): String = when (value) {
    null -> "Not set"
    is Boolean -> if (value) "On" else "Off"
    is List<*> -> value.joinToString(", ").ifBlank { "None" }
    else -> value.toString()
}
