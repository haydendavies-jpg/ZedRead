package com.zedread.pos.data.local.dao

import com.zedread.pos.data.local.entity.SavedPrinterEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map

/** In-memory [SavedPrinterDao] test double — no real Room/SQLite involved. */
class FakeSavedPrinterDao : SavedPrinterDao {
    private val state = MutableStateFlow<List<SavedPrinterEntity>>(emptyList())

    override fun observeAll(): Flow<List<SavedPrinterEntity>> = state

    override fun observeEnabled(): Flow<List<SavedPrinterEntity>> = state.map { list -> list.filter { it.isEnabled } }

    override suspend fun findByMac(macAddress: String): SavedPrinterEntity? =
        state.value.firstOrNull { it.macAddress.equals(macAddress, ignoreCase = true) }

    override suspend fun findById(id: String): SavedPrinterEntity? = state.value.firstOrNull { it.id == id }

    override suspend fun upsert(printer: SavedPrinterEntity) {
        state.value = state.value.filterNot { it.id == printer.id } + printer
    }

    override suspend fun setEnabled(id: String, isEnabled: Boolean) {
        state.value = state.value.map { if (it.id == id) it.copy(isEnabled = isEnabled) else it }
    }

    override suspend fun updateIpByMac(macAddress: String, ip: String, seenAtMillis: Long) {
        state.value = state.value.map {
            if (it.macAddress.equals(macAddress, ignoreCase = true)) it.copy(lastKnownIp = ip, lastSeenAtMillis = seenAtMillis) else it
        }
    }

    override suspend fun markConnected(id: String, atMillis: Long) {
        state.value = state.value.map { if (it.id == id) it.copy(lastConnectedAtMillis = atMillis) else it }
    }

    override suspend fun delete(id: String) {
        state.value = state.value.filterNot { it.id == id }
    }
}
