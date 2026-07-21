package com.zedread.pos.ui.screens.switchuser

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
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
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
import com.zedread.pos.ui.viewmodel.SwitchUserState
import com.zedread.pos.ui.viewmodel.SwitchUserViewModel

/**
 * Doubles as ZedRead POS's "PIN entry" screen: lets a different operator take
 * over this terminal (POST /auth/pos/pin/verify), or the current operator
 * re-confirm their own identity, without a full email+password login.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SwitchUserScreen(
    onSwitched: (needsPinSetup: Boolean) -> Unit,
    onCancel: () -> Unit,
    viewModel: SwitchUserViewModel = hiltViewModel(),
) {
    val state by viewModel.switchState.collectAsState()
    val currentUserName by viewModel.currentUserName.collectAsState()
    var email by remember { mutableStateOf("") }
    var pin by remember { mutableStateOf("") }

    LaunchedEffect(state) {
        val switched = state as? SwitchUserState.Switched ?: return@LaunchedEffect
        viewModel.resetSwitchState()
        onSwitched(switched.needsPinSetup)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Switch Operator") },
                navigationIcon = { TextButton(onClick = onCancel) { Text("Cancel") } },
            )
        },
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .padding(innerPadding)
                .padding(32.dp)
                .fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (currentUserName != null) {
                Text(
                    "Currently signed in: $currentUserName",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(16.dp))
            }

            Text("Enter your email and PIN to start", style = MaterialTheme.typography.bodyLarge)
            Spacer(Modifier.height(24.dp))

            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Email") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(16.dp))

            OutlinedTextField(
                value = pin,
                onValueChange = { if (it.length <= 6) pin = it },
                label = { Text("PIN") },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(8.dp))

            when (state) {
                is SwitchUserState.InvalidPin -> Text("Incorrect email or PIN", color = MaterialTheme.colorScheme.error)
                is SwitchUserState.Error -> Text((state as SwitchUserState.Error).message, color = MaterialTheme.colorScheme.error)
                else -> Unit
            }

            Spacer(Modifier.height(24.dp))

            Button(
                onClick = { viewModel.switchOperator(email.trim(), pin) },
                enabled = email.isNotBlank() && pin.isNotBlank() && state !is SwitchUserState.Loading,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (state is SwitchUserState.Loading) CircularProgressIndicator(modifier = Modifier.height(20.dp))
                else Text("Start Session")
            }
        }
    }
}
