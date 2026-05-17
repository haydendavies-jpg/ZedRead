package com.zedread.pos.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.zedread.pos.ui.viewmodel.InlineAuthState
import com.zedread.pos.ui.viewmodel.SwitchUserViewModel

/**
 * Inline manager auth prompt — shown as an overlay on the current screen when an
 * elevated-privilege action (void, refund, discount) is attempted.
 *
 * The manager enters their PIN without switching the active cashier session.
 *
 * @param actionLabel Human-readable description shown in the prompt (e.g. "Void invoice").
 * @param onAuthorised Called when the manager PIN is verified — caller should proceed with the action.
 * @param onDismiss Called when the manager cancels or after too many failed attempts.
 * @param viewModel Shared [SwitchUserViewModel] — callers should pass the one already in scope.
 */
@Composable
fun InlineAuthPrompt(
    actionLabel: String,
    onAuthorised: () -> Unit,
    onDismiss: () -> Unit,
    state: InlineAuthState,
    onSubmit: (pin: String) -> Unit,
    onReset: () -> Unit,
) {
    var pin by remember { mutableStateOf("") }

    // React to authorisation result.
    if (state is InlineAuthState.Authorised) {
        onAuthorised()
        onReset()
        return
    }

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        shape = MaterialTheme.shapes.large,
        tonalElevation = 8.dp,
        shadowElevation = 8.dp,
    ) {
        Column(
            modifier = Modifier.padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Manager Authorisation Required", style = MaterialTheme.typography.titleMedium)
            Text("Action: $actionLabel", style = MaterialTheme.typography.bodyMedium)

            OutlinedTextField(
                value = pin,
                onValueChange = { if (it.length <= 6) pin = it },
                label = { Text("Manager PIN") },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                isError = state is InlineAuthState.Denied,
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            when (state) {
                is InlineAuthState.Denied -> Text("Incorrect PIN", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                is InlineAuthState.Error -> Text(state.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                else -> Spacer(Modifier.height(0.dp))
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp, androidx.compose.ui.Alignment.End),
            ) {
                TextButton(onClick = onDismiss) { Text("Cancel") }

                Button(
                    onClick = { onSubmit(pin) },
                    enabled = pin.isNotBlank() && state !is InlineAuthState.Loading,
                ) {
                    if (state is InlineAuthState.Loading) CircularProgressIndicator(modifier = Modifier.height(18.dp))
                    else Text("Authorise")
                }
            }
        }
    }
}
