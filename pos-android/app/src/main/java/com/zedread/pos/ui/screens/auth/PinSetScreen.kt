package com.zedread.pos.ui.screens.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import com.zedread.pos.ui.viewmodel.PinUiState

/**
 * PIN set screen — shown when [PinVerifyResponse.mustReset] is true.
 * The operator enters a new PIN (confirmed) to replace their temporary one.
 */
@Composable
fun PinSetScreen(
    onPinSet: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val uiState by viewModel.pinUiState.collectAsState()
    var newPin by remember { mutableStateOf("") }
    var confirmPin by remember { mutableStateOf("") }

    LaunchedEffect(uiState) {
        if (uiState is PinUiState.Set) onPinSet()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Set New PIN", style = MaterialTheme.typography.headlineMedium)
        Text(
            "You must set a new PIN before continuing.",
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
            label = { Text("Confirm New PIN") },
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

        if (uiState is PinUiState.Error) {
            Text(
                (uiState as PinUiState.Error).message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        }

        Spacer(Modifier.height(24.dp))

        val canSubmit = newPin.length >= 4 && newPin == confirmPin && uiState !is PinUiState.Loading

        Button(
            onClick = { viewModel.setPin(currentPin = null, newPin = newPin) },
            enabled = canSubmit,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (uiState is PinUiState.Loading) {
                CircularProgressIndicator(modifier = Modifier.height(20.dp))
            } else {
                Text("Save PIN")
            }
        }
    }
}
