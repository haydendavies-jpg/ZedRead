package com.zedread.pos.data.repository

import android.content.Context
import com.zedread.pos.data.local.dao.FakeSavedPrinterDao
import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.printing.Docket
import com.zedread.pos.printing.PrintResult
import com.zedread.pos.printing.driver.DiscoveredPrinter
import com.zedread.pos.printing.driver.FakePrinterDriver
import com.zedread.pos.printing.driver.PrinterDriverRegistry
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito.mock

private fun testPrinter(
    id: String = "p1",
    driverId: String = "fake",
    connectionType: String = "NETWORK",
    macAddress: String = "AA:BB:CC:DD:EE:FF",
    lastKnownIp: String? = "1.1.1.1",
    isEnabled: Boolean = true,
): SavedPrinterEntity = SavedPrinterEntity(
    id = id,
    name = "Test Printer",
    driverId = driverId,
    connectionType = connectionType,
    macAddress = macAddress,
    lastKnownIp = lastKnownIp,
    port = 9100,
    isEnabled = isEnabled,
    createdAtMillis = 0L,
)

private fun testDocket(): Docket = Docket(
    invoiceId = "inv1",
    siteName = "Test Site",
    lineItems = emptyList(),
    totalCents = 500L,
    paymentMethod = "cash",
)

/** Fake Android Context is only ever forwarded to a driver's own discover() — never touched by these fakes. */
private fun fakeContext(): Context = mock(Context::class.java)

class PrinterRepositoryTest {

    @Test
    fun `savePrinter upserts by MAC instead of duplicating`() = runTest {
        val dao = FakeSavedPrinterDao()
        val repo = PrinterRepository(dao, PrinterDriverRegistry(setOf(FakePrinterDriver())), fakeContext())
        val discovered = DiscoveredPrinter(
            macAddress = "AA:BB:CC:DD:EE:FF", ipAddress = "1.1.1.1", bluetoothAddress = null, name = "Printer A", driverId = "fake",
        )

        repo.savePrinter(discovered, "Printer A")
        repo.savePrinter(discovered.copy(ipAddress = "2.2.2.2"), "Printer A (renamed)")

        val saved = repo.observeSavedPrinters().first()
        assertEquals(1, saved.size)
        assertEquals("2.2.2.2", saved.single().lastKnownIp)
        assertEquals("Printer A (renamed)", saved.single().name)
    }

    @Test
    fun `rediscoverByMac only patches IP on a genuine MAC match`() = runTest {
        val dao = FakeSavedPrinterDao()
        val printer = testPrinter(lastKnownIp = "1.1.1.1")
        dao.upsert(printer)

        val noMatch = FakePrinterDriver(
            driverId = "fake",
            discoverFlow = flowOf(DiscoveredPrinter("11:22:33:44:55:66", "9.9.9.9", null, "Other", "fake")),
        )
        val unchanged = PrinterRepository(dao, PrinterDriverRegistry(setOf(noMatch)), fakeContext()).rediscoverByMac(printer)
        assertEquals("1.1.1.1", unchanged.lastKnownIp)

        val match = FakePrinterDriver(
            driverId = "fake",
            discoverFlow = flowOf(DiscoveredPrinter(printer.macAddress, "2.2.2.2", null, printer.name, "fake")),
        )
        val updated = PrinterRepository(dao, PrinterDriverRegistry(setOf(match)), fakeContext()).rediscoverByMac(printer)
        assertEquals("2.2.2.2", updated.lastKnownIp)
    }

    @Test
    fun `sendToPrinter retries once via rediscover for a NETWORK printer`() = runTest {
        val dao = FakeSavedPrinterDao()
        val printer = testPrinter(connectionType = "NETWORK", lastKnownIp = "1.1.1.1")
        dao.upsert(printer)

        val driver = FakePrinterDriver(
            driverId = "fake",
            discoverFlow = flowOf(DiscoveredPrinter(printer.macAddress, "2.2.2.2", null, printer.name, "fake")),
            sendResults = listOf(PrintResult.Failure("offline"), PrintResult.Success),
        )
        val repo = PrinterRepository(dao, PrinterDriverRegistry(setOf(driver)), fakeContext())

        val result = repo.sendToPrinter(printer, testDocket())

        assertTrue(result is PrintResult.Success)
        assertEquals(2, driver.sendCallCount)
        assertEquals("2.2.2.2", dao.findById(printer.id)?.lastKnownIp)
    }

    @Test
    fun `sendToPrinter does not retry for a BLUETOOTH printer`() = runTest {
        val dao = FakeSavedPrinterDao()
        val printer = testPrinter(connectionType = "BLUETOOTH", lastKnownIp = null)
        dao.upsert(printer)

        val driver = FakePrinterDriver(driverId = "fake", sendResults = listOf(PrintResult.Failure("out of range")))
        val repo = PrinterRepository(dao, PrinterDriverRegistry(setOf(driver)), fakeContext())

        val result = repo.sendToPrinter(printer, testDocket())

        assertTrue(result is PrintResult.Failure)
        assertEquals(1, driver.sendCallCount)
        assertEquals(0, driver.discoverCallCount)
    }

    @Test
    fun `sendToAllEnabled only sends to enabled printers`() = runTest {
        val dao = FakeSavedPrinterDao()
        val enabled = testPrinter(id = "p1", macAddress = "AA:AA:AA:AA:AA:AA", isEnabled = true)
        val disabled = testPrinter(id = "p2", macAddress = "BB:BB:BB:BB:BB:BB", isEnabled = false)
        dao.upsert(enabled)
        dao.upsert(disabled)

        val driver = FakePrinterDriver(driverId = "fake", sendResults = listOf(PrintResult.Success))
        val repo = PrinterRepository(dao, PrinterDriverRegistry(setOf(driver)), fakeContext())

        val results = repo.sendToAllEnabled(testDocket())

        assertEquals(setOf(enabled), results.keys)
        assertEquals(1, driver.sendCallCount)
    }
}
