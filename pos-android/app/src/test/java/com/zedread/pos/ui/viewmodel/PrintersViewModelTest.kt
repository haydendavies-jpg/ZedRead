package com.zedread.pos.ui.viewmodel

import android.content.Context
import com.zedread.pos.data.local.dao.FakeSavedPrinterDao
import com.zedread.pos.data.repository.PrinterRepository
import com.zedread.pos.printing.driver.DiscoveredPrinter
import com.zedread.pos.printing.driver.FakePrinterDriver
import com.zedread.pos.printing.driver.PrinterDriverRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.mockito.Mockito.mock

@OptIn(ExperimentalCoroutinesApi::class)
class PrintersViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun fakeContext(): Context = mock(Context::class.java)

    @Test
    fun `discovery results dedupe by MAC as they stream in`() = runTest(dispatcher) {
        val discoverFlow = flowOf(
            DiscoveredPrinter("AA:BB:CC:DD:EE:FF", "1.1.1.1", null, "Printer A", "fake"),
            // Same MAC reported again (e.g. a duplicate broadcast) — should not add a second entry.
            DiscoveredPrinter("AA:BB:CC:DD:EE:FF", "1.1.1.2", null, "Printer A", "fake"),
            DiscoveredPrinter("11:22:33:44:55:66", "2.2.2.2", null, "Printer B", "fake"),
        )
        val driver = FakePrinterDriver(driverId = "fake", discoverFlow = discoverFlow)
        val repo = PrinterRepository(FakeSavedPrinterDao(), PrinterDriverRegistry(setOf(driver)), fakeContext())
        val viewModel = PrintersViewModel(repo)

        viewModel.startDiscovery()
        advanceUntilIdle()

        val state = viewModel.discoveryState.value as DiscoveryUiState.Scanning
        assertEquals(2, state.found.size)
        assertEquals(setOf("AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"), state.found.map { it.macAddress }.toSet())
    }

    @Test
    fun `addDiscovered saves the printer via the repository`() = runTest(dispatcher) {
        val dao = FakeSavedPrinterDao()
        val repo = PrinterRepository(dao, PrinterDriverRegistry(setOf(FakePrinterDriver())), fakeContext())
        val viewModel = PrintersViewModel(repo)
        val discovered = DiscoveredPrinter("AA:BB:CC:DD:EE:FF", "1.1.1.1", null, "Printer A", "fake")

        viewModel.addDiscovered(discovered)
        advanceUntilIdle()

        assertEquals(1, dao.observeAll().first().size)
    }
}
