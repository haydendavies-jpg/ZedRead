package com.zedread.pos.ui.screens.register

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
import com.zedread.pos.ui.viewmodel.RegisterGateState
import com.zedread.pos.ui.viewmodel.RegisterSessionViewModel

/**
 * No-UI-in-the-happy-path gate: checks GET /register-sessions/current on
 * every launch/resume and routes to the cash-in screen when the till isn't
 * open yet — POST /invoices rejects with 400 otherwise.
 */
@Composable
fun RegisterGateScreen(
    onNeedsCashIn: () -> Unit,
    onOpen: () -> Unit,
    onSessionExpired: () -> Unit,
    viewModel: RegisterSessionViewModel = hiltViewModel(),
) {
    val state by viewModel.gateState.collectAsState()

    LaunchedEffect(Unit) { viewModel.checkCurrentSession() }

    LaunchedEffect(state) {
        when (state) {
            is RegisterGateState.NeedsCashIn -> onNeedsCashIn()
            is RegisterGateState.Open -> onOpen()
            is RegisterGateState.SessionExpired -> onSessionExpired()
            else -> Unit
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        when (val current = state) {
            is RegisterGateState.Error -> {
                Text(
                    current.message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = { viewModel.checkCurrentSession() },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Retry") }
            }
            else -> CircularProgressIndicator()
        }
    }
}
