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
import com.zedread.pos.ui.screens.auth.LoginScreen
import com.zedread.pos.ui.screens.auth.PinSetScreen
import com.zedread.pos.ui.screens.auth.SiteSelectorScreen
import com.zedread.pos.ui.screens.invoicesearch.InvoiceSearchScreen
import com.zedread.pos.ui.screens.orderentry.OrderEntryScreen
import com.zedread.pos.ui.screens.register.CashInScreen
import com.zedread.pos.ui.screens.register.CashUpScreen
import com.zedread.pos.ui.screens.register.RegisterGateScreen
import com.zedread.pos.ui.screens.settings.SettingsScreen
import com.zedread.pos.ui.screens.switchuser.SwitchUserScreen
import com.zedread.pos.ui.viewmodel.AppEntryViewModel
import com.zedread.pos.ui.viewmodel.StartDestination

/**
 * Top-level Compose navigation graph covering every screen in the POS terminal.
 *
 * Waits for [AppEntryViewModel] to resolve where a relaunch should land
 * (login, or straight past it into the register gate) before composing the
 * graph — Compose Navigation doesn't support changing startDestination
 * after the NavHost is first created.
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
        StartDestination.Login -> Screen.Login.route
        StartDestination.RegisterGate -> Screen.RegisterGate.route
    }

    NavHost(navController = navController, startDestination = startRoute) {
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
                    navController.navigate(Screen.OrderEntry.route) {
                        popUpTo(Screen.RegisterGate.route) { inclusive = true }
                    }
                },
                onSessionExpired = {
                    navController.navigate(Screen.Login.route) {
                        popUpTo(Screen.RegisterGate.route) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.CashIn.route) {
            CashInScreen(
                onOpened = {
                    navController.navigate(Screen.OrderEntry.route) {
                        popUpTo(Screen.CashIn.route) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.CashUp.route) {
            CashUpScreen(
                onDone = {
                    // End of shift: the till is closed but the operator stays logged in
                    // on this device — logout is a separate, explicit action (Settings,
                    // not built yet), not something cash-up forces. Land back on the
                    // gate, which will prompt cash-in for the next shift since no
                    // session is open; clear the whole back stack so Back can't return
                    // to the stale, now-closed sale.
                    navController.navigate(Screen.RegisterGate.route) {
                        popUpTo(navController.graph.id) { inclusive = true }
                    }
                },
                onCancel = { navController.popBackStack() },
            )
        }

        // ── Register (order entry) ──────────────────────────────────────────
        //
        // The modifier customise sheet and payment modal are both overlays on
        // this one screen in the design bundle (see SellViewModel's class
        // doc), not separate nav destinations — a fresh SellViewModel comes
        // for free from the default hiltViewModel() scoping to this single
        // back stack entry, and "New order" resets it in place
        // (SellViewModel.completePaymentAndStartNewOrder()) rather than via a
        // navigate-and-pop trick. The design bundle has no separate cart
        // screen either — the order pane lives alongside the product grid on
        // one Register screen — so there's only one entry point here.
        composable(Screen.OrderEntry.route) {
            OrderEntryScreen(
                onSwitchUser = { navController.navigate(Screen.SwitchUser.route) },
                onCashUp = { navController.navigate(Screen.CashUp.route) },
                onSettings = { navController.navigate(Screen.Settings.route) },
                onInvoiceSearch = { navController.navigate(Screen.InvoiceSearch.route) },
            )
        }

        composable(Screen.Settings.route) {
            SettingsScreen(
                onBack = { navController.popBackStack() },
            )
        }

        composable(Screen.InvoiceSearch.route) {
            InvoiceSearchScreen(
                onBack = { navController.popBackStack() },
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
    object Login : Screen("login")
    object SiteSelector : Screen("site_selector")
    object PinSet : Screen("pin_set")
    object RegisterGate : Screen("register_gate")
    object CashIn : Screen("cash_in")
    object CashUp : Screen("cash_up")
    object OrderEntry : Screen("order_entry")
    object SwitchUser : Screen("switch_user")
    object Settings : Screen("settings")
    object InvoiceSearch : Screen("invoice_search")
}
