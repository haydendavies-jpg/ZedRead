package com.zedread.pos.ui.screens.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Print
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.data.api.SettingDto
import com.zedread.pos.ui.components.PosTopBar
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.SettingsUiState
import com.zedread.pos.ui.viewmodel.SettingsViewModel
import com.zedread.pos.ui.viewmodel.SyncViewModel
import com.zedread.pos.ui.viewmodel.TopBarViewModel

/**
 * Searchable list of every setting resolved for this terminal's site.
 * Boolean and single-select settings are editable locally at the till; a
 * per-row "Save as default" pushes the edit back to become the site's
 * backend override (Manager+ access profile only — see
 * SettingsViewModel/SettingsRepository). Other setting types (datetime,
 * multi-select — neither has a real catalog entry yet) render read-only.
 */
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onPrinters: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
    syncViewModel: SyncViewModel = hiltViewModel(),
    topBarViewModel: TopBarViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    val search by viewModel.search.collectAsState()
    val savingKeys by viewModel.savingKeys.collectAsState()
    val saveError by viewModel.saveError.collectAsState()
    val canPushDefaults by viewModel.canPushDefaults.collectAsState()
    val deviceName by topBarViewModel.deviceName.collectAsState()
    val isOnline by syncViewModel.isOnline.collectAsState()
    val pendingCount by syncViewModel.pendingCount.collectAsState()

    Column(modifier = Modifier.fillMaxSize()) {
        PosTopBar(
            title = deviceName ?: "Register",
            subtitle = "Settings",
            onBack = onBack,
            isOnline = isOnline,
            pendingCount = pendingCount,
            onSyncClick = {},
        ) {
            IconButton(onClick = onPrinters) {
                Icon(Icons.Default.Print, contentDescription = "Printers", tint = Color.White)
            }
            IconButton(onClick = { viewModel.load(forceRefresh = true) }) {
                Icon(Icons.Default.Refresh, contentDescription = "Refresh settings", tint = Color.White)
            }
        }
        Column(modifier = Modifier.fillMaxSize()) {
            OutlinedTextField(
                value = search,
                onValueChange = viewModel::setSearch,
                label = { Text("Search settings") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            )

            if (saveError != null) {
                Text(
                    saveError.orEmpty(),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }

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
                                SettingRow(
                                    setting = setting,
                                    value = viewModel.displayValue(setting),
                                    isDirty = viewModel.isDirty(setting),
                                    isSaving = setting.key in savingKeys,
                                    canPushDefaults = canPushDefaults,
                                    onValueChange = { viewModel.setLocalValue(setting.key, it) },
                                    onSaveAsDefault = { viewModel.saveAsDefault(setting.key) },
                                )
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
private fun SettingRow(
    setting: SettingDto,
    value: Any?,
    isDirty: Boolean,
    isSaving: Boolean,
    canPushDefaults: Boolean,
    onValueChange: (Any?) -> Unit,
    onSaveAsDefault: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
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
            SettingValueEditor(setting = setting, value = value, onValueChange = onValueChange)
        }
        if (isDirty) {
            if (canPushDefaults) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = onSaveAsDefault, enabled = !isSaving) {
                        Text(if (isSaving) "Saving…" else "Save as default")
                    }
                }
            } else {
                // The value already applies to THIS device the moment it's
                // toggled (SettingsRepository.applyLocalOverride — every
                // other reader of the settings cache, e.g. CashIn/CashUp's
                // cash_in_mode, sees it immediately) regardless of role; only
                // pushing it as every device's shared default is gated to
                // the three system tiers allowed to write to the server
                // (Master User/Admin/Manager — see app/routes/settings.py's
                // _POS_SETTINGS_WRITE_PROFILE_NAMES). Previously this read as
                // "I can't change POS settings" with no clarification that
                // the change was, in fact, already in effect here.
                Text(
                    "Applied to this device. Ask a Manager or Admin to make it every device's default.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

/** Renders the right-hand value control — editable for boolean/single_select, read-only text otherwise. */
@Composable
private fun SettingValueEditor(setting: SettingDto, value: Any?, onValueChange: (Any?) -> Unit) {
    when (setting.type) {
        "boolean" -> Switch(checked = value as? Boolean ?: false, onCheckedChange = onValueChange)
        "single_select" -> SingleSelectEditor(options = setting.options.orEmpty(), value = value as? String, onValueChange = onValueChange)
        else -> Text(formatSettingValue(value), style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
    }
}

/**
 * A single-select value control styled as an obvious dropdown (bordered
 * pill + a "▾" arrow, matching OrderEntryScreen's MenuSelectorRow
 * convention) — previously a bare [TextButton] with no border/affordance,
 * user-testing feedback that it wasn't obvious this was tappable at all.
 * Option/value text is capitalized for display — the raw catalog values
 * (e.g. "denomination") are lowercase machine identifiers, not meant to be
 * shown to a cashier verbatim.
 */
@Composable
private fun SingleSelectEditor(options: List<String>, value: String?, onValueChange: (Any?) -> Unit) {
    val colors = LocalZedReadColors.current
    var expanded by remember { mutableStateOf(false) }
    Box {
        Row(
            modifier = Modifier
                .clip(RoundedCornerShape(8.dp))
                .background(colors.surface)
                .border(width = 1.dp, color = colors.inputBorder, shape = RoundedCornerShape(8.dp))
                .clickable { expanded = true }
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(value?.capitalizeForDisplay() ?: "—", color = colors.text)
            Text("▾", color = colors.muted)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option.capitalizeForDisplay()) },
                    onClick = { onValueChange(option); expanded = false },
                )
            }
        }
    }
}

private fun String.capitalizeForDisplay(): String = replaceFirstChar { it.uppercase() }

/** Render a setting's effective value for display — the shape depends on its SettingType. */
private fun formatSettingValue(value: Any?): String = when (value) {
    null -> "Not set"
    is Boolean -> if (value) "On" else "Off"
    is List<*> -> value.joinToString(", ").ifBlank { "None" }
    else -> value.toString()
}
