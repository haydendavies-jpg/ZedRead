package com.zedread.pos.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.navigation
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
import com.zedread.pos.ui.viewmodel.SellViewModel
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
                    navController.navigate(Screen.SellGraph.route) {
                        popUpTo(Screen.RegisterGate.route) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.CashIn.route) {
            CashInScreen(
                onOpened = {
                    navController.navigate(Screen.SellGraph.route) {
                        popUpTo(Screen.CashIn.route) { inclusive = true }
                    }
                },
            )
        }

        // ── Sell sub-graph: Catalog → Cart → Payment share one SellViewModel ────
        //
        // There is no backend endpoint to reconstruct a draft invoice's line
        // items, so the cart has to live in a ViewModel that survives
        // navigating between these three screens rather than a fresh instance
        // per screen. Re-entering this route (popUpTo inclusive after payment)
        // discards the graph's back stack entry and its ViewModelStore,
        // which is what resets the cart for the next sale.
        navigation(startDestination = Screen.Catalog.route, route = Screen.SellGraph.route) {
            composable(Screen.Catalog.route) { backStackEntry ->
                val sellViewModel = sellViewModel(navController, backStackEntry)
                CatalogScreen(
                    viewModel = sellViewModel,
                    onProceedToCart = { navController.navigate(Screen.Cart.route) },
                    onSwitchUser = { navController.navigate(Screen.SwitchUser.route) },
                )
            }

            composable(Screen.Cart.route) { backStackEntry ->
                val sellViewModel = sellViewModel(navController, backStackEntry)
                CartScreen(
                    viewModel = sellViewModel,
                    onProceedToPayment = { navController.navigate(Screen.Payment.route) },
                )
            }

            composable(Screen.Payment.route) { backStackEntry ->
                val sellViewModel = sellViewModel(navController, backStackEntry)
                PaymentScreen(
                    viewModel = sellViewModel,
                    onPaymentComplete = { _ ->
                        navController.navigate(Screen.SellGraph.route) {
                            popUpTo(Screen.SellGraph.route) { inclusive = true }
                        }
                    },
                )
            }
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

/** Resolves the SellViewModel shared by every screen in the "sell" sub-graph. */
@Composable
private fun sellViewModel(
    navController: NavHostController,
    backStackEntry: NavBackStackEntry,
): SellViewModel {
    val graphEntry = remember(backStackEntry) { navController.getBackStackEntry(Screen.SellGraph.route) }
    return hiltViewModel(graphEntry)
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
    object SellGraph : Screen("sell")
    object Catalog : Screen("catalog")
    object Cart : Screen("cart")
    object Payment : Screen("payment")
    object SwitchUser : Screen("switch_user")
}
