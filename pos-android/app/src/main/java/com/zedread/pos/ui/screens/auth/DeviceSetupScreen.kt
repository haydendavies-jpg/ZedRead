package com.zedread.pos.ui.screens.auth

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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.viewmodel.DevicePairState
import com.zedread.pos.ui.viewmodel.DeviceViewModel

/**
 * One-time terminal setup — shown only until a device_token is stored.
 *
 * The token is issued by a portal admin registering this physical terminal
 * (POST /pos-devices) and handed to whoever is setting up the terminal; it
 * identifies the device itself, not the operator who later signs in.
 */
@Composable
fun DeviceSetupScreen(
    onPaired: () -> Unit,
    viewModel: DeviceViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    var token by remember { mutableStateOf("") }

    LaunchedEffect(state) {
        if (state is DevicePairState.Done) onPaired()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = "Terminal Setup",
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.primary,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Enter the device token provided by your administrator to pair this terminal.",
            style = MaterialTheme.typography.bodyMedium,
        )

        Spacer(Modifier.height(32.dp))

        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            label = { Text("Device token") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(8.dp))

        if (state is DevicePairState.Error) {
            Text(
                text = (state as DevicePairState.Error).message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        }

        Spacer(Modifier.height(24.dp))

        Button(
            onClick = { viewModel.pair(token) },
            enabled = state !is DevicePairState.Loading,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state is DevicePairState.Loading) {
                CircularProgressIndicator(modifier = Modifier.height(20.dp))
            } else {
                Text("Pair This Terminal")
            }
        }
    }
}
