package com.zedread.pos.ui

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.zedread.pos.ui.screens.auth.LoginScreen
import com.zedread.pos.ui.screens.auth.PinEntryScreen
import com.zedread.pos.ui.screens.auth.PinSetScreen
import com.zedread.pos.ui.screens.auth.SiteSelectorScreen
import com.zedread.pos.ui.screens.cart.CartScreen
import com.zedread.pos.ui.screens.catalog.CatalogScreen
import com.zedread.pos.ui.screens.payment.PaymentScreen
import com.zedread.pos.ui.screens.switchuser.SwitchUserScreen

/** Top-level Compose navigation graph covering every screen in the POS terminal. */
@Composable
fun PosNavHost() {
    val navController = rememberNavController()

    NavHost(
        navController = navController,
        startDestination = Screen.Login.route,
    ) {
        composable(Screen.Login.route) {
            LoginScreen(
                onLoginSuccess = { navController.navigate(Screen.SiteSelector.route) },
            )
        }

        composable(Screen.SiteSelector.route) {
            SiteSelectorScreen(
                onSiteSelected = {
                    navController.navigate(Screen.PinEntry.route) {
                        popUpTo(Screen.Login.route) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.PinEntry.route) {
            PinEntryScreen(
                onPinVerified = {
                    navController.navigate(Screen.Catalog.route) {
                        popUpTo(Screen.PinEntry.route) { inclusive = true }
                    }
                },
                onMustResetPin = { navController.navigate(Screen.PinSet.route) },
            )
        }

        composable(Screen.PinSet.route) {
            PinSetScreen(
                onPinSet = {
                    navController.navigate(Screen.Catalog.route) {
                        popUpTo(Screen.PinEntry.route) { inclusive = true }
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
                onSwitched = {
                    navController.navigate(Screen.PinEntry.route) {
                        popUpTo(Screen.Catalog.route) { inclusive = false }
                    }
                },
                onCancel = { navController.popBackStack() },
            )
        }
    }
}

/** Sealed class of all navigation destinations. */
sealed class Screen(val route: String) {
    object Login : Screen("login")
    object SiteSelector : Screen("site_selector")
    object PinEntry : Screen("pin_entry")
    object PinSet : Screen("pin_set")
    object Catalog : Screen("catalog")
    object Cart : Screen("cart")
    object Payment : Screen("payment")
    object SwitchUser : Screen("switch_user")
}
