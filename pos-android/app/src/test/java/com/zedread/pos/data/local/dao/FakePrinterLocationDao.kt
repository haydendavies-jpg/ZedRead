package com.zedread.pos.data.local.dao

import com.zedread.pos.data.local.entity.PrinterLocationEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow

/** In-memory [PrinterLocationDao] test double — no real Room/SQLite involved. */
class FakePrinterLocationDao : PrinterLocationDao {
    private val state = MutableStateFlow<List<PrinterLocationEntity>>(emptyList())

    override fun observeAll(): Flow<List<PrinterLocationEntity>> = state

    override suspend fun getAll(): List<PrinterLocationEntity> = state.value

    override suspend fun replaceAll(locations: List<PrinterLocationEntity>) {
        state.value = locations
    }

    override suspend fun clearAll() {
        state.value = emptyList()
    }
}
