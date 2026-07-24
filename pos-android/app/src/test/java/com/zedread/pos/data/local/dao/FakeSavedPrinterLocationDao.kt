package com.zedread.pos.data.local.dao

import com.zedread.pos.data.local.entity.SavedPrinterEntity
import com.zedread.pos.data.local.entity.SavedPrinterLocationEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map

/**
 * In-memory [SavedPrinterLocationDao] test double — no real Room/SQLite
 * involved. [getEnabledPrintersForLocation] needs [savedPrinters] (normally
 * a real SQL join against saved_printers) supplied directly since there's no
 * database to join against here.
 */
class FakeSavedPrinterLocationDao(private val savedPrinters: () -> List<SavedPrinterEntity> = { emptyList() }) : SavedPrinterLocationDao {
    private val state = MutableStateFlow<List<SavedPrinterLocationEntity>>(emptyList())

    override fun observeLocationIdsForPrinter(printerId: String): Flow<List<String>> =
        state.map { list -> list.filter { it.printerId == printerId }.map { it.printerLocationId } }

    override suspend fun clearForPrinter(printerId: String) {
        state.value = state.value.filterNot { it.printerId == printerId }
    }

    override suspend fun insertAll(assignments: List<SavedPrinterLocationEntity>) {
        state.value = state.value + assignments
    }

    override suspend fun getEnabledPrintersForLocation(printerLocationId: String): List<SavedPrinterEntity> {
        val printerIds = state.value.filter { it.printerLocationId == printerLocationId }.map { it.printerId }.toSet()
        return savedPrinters().filter { it.id in printerIds && it.isEnabled }
    }
}
