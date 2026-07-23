package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.squareup.moshi.Moshi
import com.zedread.pos.data.local.entity.OutboxItemEntity
import com.zedread.pos.data.repository.OutboxRepository
import com.zedread.pos.data.sync.ConnectivityObserver
import com.zedread.pos.data.sync.OutboxOperation
import com.zedread.pos.data.sync.OutboxPayloads
import com.zedread.pos.data.sync.OutboxStatus
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

/**
 * Backs the persistent offline/pending-sync badge (visible from Register at
 * all times, never a blocking modal — staff keep selling while offline) and
 * the sync panel it opens into. [pendingCount] and [items] both read
 * straight from Room, so they update the instant something is enqueued —
 * not after the eventual round trip.
 */
@HiltViewModel
class SyncViewModel @Inject constructor(
    private val outboxRepo: OutboxRepository,
    connectivityObserver: ConnectivityObserver,
    private val moshi: Moshi,
) : ViewModel() {

    val isOnline: StateFlow<Boolean> =
        connectivityObserver.isOnline.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), true)

    val pendingCount: StateFlow<Int> =
        outboxRepo.observePendingCount().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

    val items: StateFlow<List<SyncItemUi>> =
        outboxRepo.observeItems()
            .map { list -> list.map { toUi(it) } }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /** True once there's something worth showing the badge for at all — pending work, or a failed one to review. */
    val hasActivity: StateFlow<Boolean> =
        combine(pendingCount, items) { pending, all -> pending > 0 || all.isNotEmpty() }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), false)

    fun syncNow() { outboxRepo.syncNow() }

    private fun toUi(item: OutboxItemEntity): SyncItemUi {
        val title = runCatching {
            when (OutboxOperation.valueOf(item.operation)) {
                OutboxOperation.SYNC_SALE -> {
                    val payload = OutboxPayloads.decodeSale(moshi, item.payloadJson)
                    // payments is empty for a held order (see SellViewModel.holdOrder) — no
                    // amount to show yet, since nothing has been paid on it.
                    if (payload.payments.isEmpty()) {
                        "Held order"
                    } else {
                        "Sale · ${formatSyncCents(payload.payments.sumOf { it.amountCents })}"
                    }
                }
                OutboxOperation.OPEN_REGISTER_SESSION -> "Till opened"
                OutboxOperation.CLOSE_REGISTER_SESSION -> "Till closed"
            }
        }.getOrDefault("Queued item")

        val isFailed = item.status == OutboxStatus.FAILED.name
        val subtitle = when {
            isFailed -> item.lastError ?: "Couldn't sync — will need attention"
            item.attemptCount > 0 -> "Waiting to sync — retried ${item.attemptCount} time${if (item.attemptCount == 1) "" else "s"}"
            else -> "Waiting to sync"
        }
        return SyncItemUi(id = item.id, title = title, subtitle = subtitle, isFailed = isFailed)
    }
}

/** One row in the sync panel — a plain-language summary, never a raw error code (see [SyncViewModel.toUi]). */
data class SyncItemUi(
    val id: Long,
    val title: String,
    val subtitle: String,
    val isFailed: Boolean,
)

private fun formatSyncCents(cents: Long): String {
    val dollars = cents / 100
    val remainder = cents % 100
    return "$${dollars}.${remainder.toString().padStart(2, '0')}"
}
