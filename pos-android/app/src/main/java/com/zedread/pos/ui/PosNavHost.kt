package com.zedread.pos.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.zedread.pos.ui.screens.auth.DeviceSetupScreen
import com.zedread.pos.ui.screens.auth.LoginScreen
import com.zedread.pos.ui.screens.auth.PinSetScreen
import com.zedread.pos.ui.screens.auth.SiteSelectorScreen
import com.zedread.pos.ui.screens.cart.CartScreen
import com.zedread.pos.ui.screens.catalog.CatalogScreen
import com.zedread.pos.ui.screens.payment.PaymentScreen
import com.zedread.pos.ui.screens.register.CashInScreen
import com.zedread.pos.ui.screens.register.RegisterGateScreen
import com.zedread.pos.ui.screens.switchuser.SwitchUserScreen
import com.zedread.pos.ui.viewmodel.AppEntryViewModel
import com.zedread.pos.ui.viewmodel.StartDestination

/**
 * Top-level Compose navigation graph covering every screen in the POS terminal.
 *
 * Waits for [AppEntryViewModel] to resolve where a relaunch should land
 * (device setup / login / straight past both into the register gate) before
 * composing the graph — Compose Navigation doesn't support changing
 * startDestination after the NavHost is first created.
 */
@Composable
fun PosNavHost() {
    val entryViewModel: AppEntryViewModel = hiltViewModel()
    val startDestination by entryViewModel.startDestination.collectAsState()

    val resolved = startDestination
    if (resolved == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    val navController = rememberNavController()
    val startRoute = when (resolved) {
        StartDestination.DeviceSetup -> Screen.DeviceSetup.route
        StartDestination.Login -> Screen.Login.route
        StartDestination.RegisterGate -> Screen.RegisterGate.route
    }

    NavHost(navController = navController, startDestination = startRoute) {
        composable(Screen.DeviceSetup.route) {
            DeviceSetupScreen(
                onPaired = {
                    navController.navigate(Screen.Login.route) {
                        popUpTo(Screen.DeviceSetup.route) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.Login.route) {
            LoginScreen(
                onNeedsSiteSelection = { navController.navigate(Screen.SiteSelector.route) },
                onAuthenticated = { needsPinSetup -> navigateAfterAuth(navController, needsPinSetup) },
            )
        }

        composable(Screen.SiteSelector.route) {
            SiteSelectorScreen(
                onAuthenticated = { needsPinSetup -> navigateAfterAuth(navController, needsPinSetup) },
            )
        }

        composable(Screen.PinSet.route) {
            PinSetScreen(
                onPinSet = {
                    navController.navigate(Screen.RegisterGate.route) {
                        popUpTo(Screen.Login.route) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.RegisterGate.route) {
            RegisterGateScreen(
                onNeedsCashIn = {
                    navController.navigate(Screen.CashIn.route) {
                        popUpTo(Screen.RegisterGate.route) { inclusive = true }
                    }
                },
                onOpen = {
                    navController.navigate(Screen.Catalog.route) {
                        popUpTo(Screen.RegisterGate.route) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.CashIn.route) {
            CashInScreen(
                onOpened = {
                    navController.navigate(Screen.Catalog.route) {
                        popUpTo(Screen.CashIn.route) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.Catalog.route) {
            CatalogScreen(
                onProceedToCart = { invoiceId ->
                    navController.navigate(Screen.Cart.route + "/$invoiceId")
                },
                onSwitchUser = { navController.navigate(Screen.SwitchUser.route) },
            )
        }

        composable(Screen.Cart.route + "/{invoiceId}") { backStackEntry ->
            val invoiceId = backStackEntry.arguments?.getString("invoiceId") ?: ""
            CartScreen(
                invoiceId = invoiceId,
                onProceedToPayment = { totalCents ->
                    navController.navigate(Screen.Payment.route + "/$invoiceId/$totalCents")
                },
            )
        }

        composable(Screen.Payment.route + "/{invoiceId}/{totalCents}") {
            PaymentScreen(
                onPaymentComplete = { _ ->
                    navController.navigate(Screen.Catalog.route) {
                        popUpTo(Screen.Catalog.route) { inclusive = false }
                    }
                },
            )
        }

        composable(Screen.SwitchUser.route) {
            SwitchUserScreen(
                onSwitched = { needsPinSetup ->
                    if (needsPinSetup) {
                        navController.navigate(Screen.PinSet.route) {
                            popUpTo(Screen.SwitchUser.route) { inclusive = true }
                        }
                    } else {
                        navController.popBackStack()
                    }
                },
                onCancel = { navController.popBackStack() },
            )
        }
    }
}

/** After login/site-select: PIN set if the backend flagged is_pin_reset_required, else the register gate. */
private fun navigateAfterAuth(navController: NavHostController, needsPinSetup: Boolean) {
    val target = if (needsPinSetup) Screen.PinSet.route else Screen.RegisterGate.route
    navController.navigate(target) {
        popUpTo(Screen.Login.route) { inclusive = true }
    }
}

/** Sealed class of all navigation destinations. */
sealed class Screen(val route: String) {
    object DeviceSetup : Screen("device_setup")
    object Login : Screen("login")
    object SiteSelector : Screen("site_selector")
    object PinSet : Screen("pin_set")
    object RegisterGate : Screen("register_gate")
    object CashIn : Screen("cash_in")
    object Catalog : Screen("catalog")
    object Cart : Screen("cart")
    object Payment : Screen("payment")
    object SwitchUser : Screen("switch_user")
}
