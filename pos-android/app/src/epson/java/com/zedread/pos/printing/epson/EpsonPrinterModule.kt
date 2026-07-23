package com.zedread.pos.printing.epson

import com.zedread.pos.printing.driver.PrinterDriver
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dagger.multibindings.IntoSet

/**
 * Separate from [com.zedread.pos.di.PrinterModule] deliberately — this file
 * lives under `app/src/epson/java/`, only added as a source root in
 * `app/build.gradle.kts` when the Epson SDK AAR is present (see that
 * file's `epsonSdkAvailable` doc). Keeping the binding here means
 * [com.zedread.pos.di.PrinterModule] never references [EpsonPrinterDriver]
 * directly, so it stays compilable — and every other driver keeps working
 * — regardless of whether the Epson SDK is present.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class EpsonPrinterModule {

    @Binds
    @IntoSet
    abstract fun bindEpsonDriver(impl: EpsonPrinterDriver): PrinterDriver
}
