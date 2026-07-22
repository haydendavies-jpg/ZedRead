package com.zedread.pos.data.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/**
 * Schedules [OutboxSyncWorker] runs. Two entry points, both constrained to
 * [NetworkType.CONNECTED] so the worker never even starts without a network:
 * a periodic job as the guaranteed-eventually fallback (covers "the app was
 * killed/backgrounded and never got a chance to react to reconnecting"),
 * and an immediate one-time request fired the moment something is enqueued
 * or the connectivity observer sees the device come back online — the
 * periodic job alone could leave a queued sale waiting up to its full
 * interval before the first retry.
 */
object OutboxScheduler {
    private const val PERIODIC_WORK_NAME = "outbox_sync_periodic"
    private const val IMMEDIATE_WORK_NAME = "outbox_sync_immediate"

    private val constraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    /** Call once at app startup — a cycling resync pass as long as the app process is alive. */
    fun schedulePeriodicSync(context: Context) {
        val request = PeriodicWorkRequestBuilder<OutboxSyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork(PERIODIC_WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request)
    }

    /**
     * Fire a drain attempt right now — enqueue-time, reconnect-time, or the
     * sync panel's manual "Sync now". REPLACE so a rapid burst of enqueues
     * (adding several offline sales in a row) collapses to one run rather
     * than queuing a pile of redundant work requests.
     */
    fun requestImmediateSync(context: Context) {
        val request = OneTimeWorkRequestBuilder<OutboxSyncWorker>()
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context)
            .enqueueUniqueWork(IMMEDIATE_WORK_NAME, ExistingWorkPolicy.REPLACE, request)
    }
}
