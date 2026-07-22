package com.zedread.pos.ui.screens.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.zedread.pos.ui.theme.LocalZedReadColors
import com.zedread.pos.ui.viewmodel.AuthViewModel
import com.zedread.pos.ui.viewmodel.LoginUiState

// The portal's own brand accent (pos-portal/src/index.css --zr-accent), a
// warm taupe — deliberately distinct from ZedReadColors.accent (the crimson
// from the Register screen's own design_handoff_zedread reference). Per
// user-testing feedback this login screen should read as "the same product
// as the portal's own sign-in page" rather than the POS Register's colour
// scheme, so it borrows the portal's palette for this screen only.
private val PortalAccent = Color(0xFF554C44)
private val PortalAccentTextLight = Color(0xFF403933)
private val PortalAccentTextDark = Color(0xFFC2B6A8)

/**
 * Email + password login — POST /auth/pos/login against this terminal's
 * paired device. Styled to match the portal's own sign-in card
 * (cream/near-black canvas, centered white/dark card, serif wordmark +
 * tagline, taupe accent) rather than a full-bleed generic Material form —
 * see PortalAccent's doc for why the accent colour differs from the rest of
 * this app's Register screens.
 */
@Composable
fun LoginScreen(
    onNeedsSiteSelection: () -> Unit,
    onAuthenticated: (needsPinSetup: Boolean) -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val colors = LocalZedReadColors.current
    val accentText = if (isSystemInDarkTheme()) PortalAccentTextDark else PortalAccentTextLight
    val uiState by viewModel.loginUiState.collectAsState()

    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }

    LaunchedEffect(uiState) {
        when (val state = uiState) {
            is LoginUiState.NeedsSiteSelection -> onNeedsSiteSelection()
            is LoginUiState.Authenticated -> onAuthenticated(state.needsPinSetup)
            else -> Unit
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bg)
            .imePadding(),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 400.dp)
                .fillMaxWidth(0.9f)
                .clip(RoundedCornerShape(18.dp))
                .background(colors.surface)
                .border(width = 1.dp, color = colors.border, shape = RoundedCornerShape(18.dp))
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                "ZedRead",
                fontWeight = FontWeight.Bold,
                fontSize = 30.sp,
                color = accentText,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "POS YOU CAN COUNT ON",
                style = MaterialTheme.typography.labelSmall,
                letterSpacing = 2.sp,
                color = colors.faint,
            )
            Spacer(Modifier.height(20.dp))
            Text(
                "Sign in",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = colors.text,
            )

            Spacer(Modifier.height(24.dp))

            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Email") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = PortalAccent,
                    focusedLabelColor = PortalAccent,
                    unfocusedBorderColor = colors.inputBorder,
                ),
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(16.dp))

            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = PortalAccent,
                    focusedLabelColor = PortalAccent,
                    unfocusedBorderColor = colors.inputBorder,
                ),
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(24.dp))

            if (uiState is LoginUiState.Error) {
                Text(
                    text = (uiState as LoginUiState.Error).message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(8.dp))
            }

            Button(
                onClick = { viewModel.login(email.trim(), password) },
                enabled = email.isNotBlank() && password.isNotBlank() && uiState !is LoginUiState.Loading,
                colors = ButtonDefaults.buttonColors(containerColor = PortalAccent, contentColor = Color.White),
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (uiState is LoginUiState.Loading) {
                    CircularProgressIndicator(modifier = Modifier.height(20.dp), color = Color.White)
                } else {
                    Text("Sign In")
                }
            }
        }
    }
}
