package com.zedread.pos.di

import com.zedread.pos.printing.driver.GenericBluetoothPrinterDriver
import com.zedread.pos.printing.driver.GenericNetworkPrinterDriver
import com.zedread.pos.printing.driver.PrinterDriver
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dagger.multibindings.IntoSet

/**
 * Registers every brand-agnostic [PrinterDriver] implementation into the
 * [com.zedread.pos.printing.driver.PrinterDriverRegistry]'s injected
 * `Set<PrinterDriver>`. Adding a new printer brand later is exactly one new
 * driver class + one `@Binds @IntoSet` line — either here, or (like Epson —
 * see `printing/epson/EpsonPrinterModule.kt`) in its own module if the
 * driver's source can only compile once an optional proprietary SDK is
 * present, so this file stays compilable regardless.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class PrinterModule {

    @Binds
    @IntoSet
    abstract fun bindGenericNetworkDriver(impl: GenericNetworkPrinterDriver): PrinterDriver

    @Binds
    @IntoSet
    abstract fun bindGenericBluetoothDriver(impl: GenericBluetoothPrinterDriver): PrinterDriver
}
