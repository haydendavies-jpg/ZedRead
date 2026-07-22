package com.zedread.pos.ui.screens.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.viewmodel.AuthViewModel
import com.zedread.pos.ui.viewmodel.PinSetUiState

/**
 * PIN set screen — shown right after login/switch-user when the backend
 * flags is_pin_reset_required, so the operator has a PIN on file for future
 * quick switch-user checks (POST /auth/pos/pin/verify).
 */
@Composable
fun PinSetScreen(
    onPinSet: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val uiState by viewModel.pinSetUiState.collectAsState()
    var newPin by remember { mutableStateOf("") }
    var confirmPin by remember { mutableStateOf("") }

    LaunchedEffect(uiState) {
        if (uiState is PinSetUiState.Done) onPinSet()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .imePadding()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Set Your PIN", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Set a PIN so you can quickly switch back in on this terminal later.",
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(32.dp))

        OutlinedTextField(
            value = newPin,
            onValueChange = { if (it.length <= 6) newPin = it },
            label = { Text("New PIN") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(16.dp))

        OutlinedTextField(
            value = confirmPin,
            onValueChange = { if (it.length <= 6) confirmPin = it },
            label = { Text("Confirm PIN") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            isError = confirmPin.isNotBlank() && confirmPin != newPin,
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(8.dp))

        if (confirmPin.isNotBlank() && confirmPin != newPin) {
            Text("PINs do not match", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }

        if (uiState is PinSetUiState.Error) {
            Text(
                (uiState as PinSetUiState.Error).message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        }

        Spacer(Modifier.height(24.dp))

        val canSubmit = newPin.length in 4..6 && newPin == confirmPin && uiState !is PinSetUiState.Loading

        Button(
            onClick = { viewModel.setPin(newPin) },
            enabled = canSubmit,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (uiState is PinSetUiState.Loading) {
                CircularProgressIndicator(modifier = Modifier.height(20.dp))
            } else {
                Text("Save PIN")
            }
        }
    }
}
