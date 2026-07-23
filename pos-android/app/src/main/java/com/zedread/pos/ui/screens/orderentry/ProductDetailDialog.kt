package com.zedread.pos.ui.screens.orderentry

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.zedread.pos.data.local.entity.ProductEntity
import com.zedread.pos.ui.theme.LocalZedReadColors

/**
 * Press-and-hold product popup — shows the product's short description
 * (ProductEntity.description) and a sold-out toggle. Setting the toggle
 * greys the product's tile out with "SOLD OUT" written over it and blocks
 * adding it to an order until toggled off again from this same popup — see
 * SellViewModel.toggleSoldOut/addToCart.
 *
 * Centered per the design ask ("pop up a window in the center"); Material3's
 * AlertDialog already centers by default, so no custom Dialog/window
 * plumbing is needed.
 */
@Composable
fun ProductDetailDialog(
    product: ProductEntity,
    errorMessage: String?,
    onToggleSoldOut: () -> Unit,
    onDismiss: () -> Unit,
) {
    val colors = LocalZedReadColors.current
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(product.name) },
        text = {
            Column {
                Text(
                    product.description?.takeIf { it.isNotBlank() } ?: "No description available.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                )
                if (errorMessage != null) {
                    Text(
                        errorMessage,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "Sold out",
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.text,
                        modifier = Modifier.weight(1f),
                    )
                    Switch(
                        checked = product.isSoldOut,
                        onCheckedChange = { onToggleSoldOut() },
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = colors.accent,
                            checkedTrackColor = colors.accentSoft2,
                        ),
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Done") }
        },
    )
}
