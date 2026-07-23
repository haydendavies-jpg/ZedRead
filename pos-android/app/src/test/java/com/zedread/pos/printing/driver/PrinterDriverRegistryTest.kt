package com.zedread.pos.printing.driver

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PrinterDriverRegistryTest {

    @Test
    fun `get resolves a driver by id, all returns every registered driver`() {
        val driverA = FakePrinterDriver(driverId = "a")
        val driverB = FakePrinterDriver(driverId = "b")
        val registry = PrinterDriverRegistry(setOf(driverA, driverB))

        assertEquals(driverA, registry.get("a"))
        assertEquals(driverB, registry.get("b"))
        assertNull(registry.get("unknown"))
        assertEquals(setOf(driverA, driverB), registry.all().toSet())
    }
}
