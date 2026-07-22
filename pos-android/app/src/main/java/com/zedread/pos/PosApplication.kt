package com.zedread.pos

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import com.zedread.pos.data.sync.OutboxScheduler
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

/**
 * Application entry point. @HiltAndroidApp triggers Hilt code generation.
 *
 * Implements [Configuration.Provider] so WorkManager uses [HiltWorkerFactory]
 * to construct workers — [com.zedread.pos.data.sync.OutboxSyncWorker] needs
 * constructor-injected repositories/DAOs, which the default WorkManager
 * initializer can't supply. The manifest removes the default
 * androidx.startup-driven initializer so this configuration is the only one
 * that runs (see AndroidManifest.xml's `WorkManagerInitializer` `tools:node="remove"`).
 */
@HiltAndroidApp
class PosApplication : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()

    override fun onCreate() {
        super.onCreate()
        // A cycling resync pass as long as the app process is alive — the
        // fallback in case an immediate sync request (fired at enqueue time
        // or on reconnect) was missed, e.g. the app was killed offline and
        // relaunched still offline.
        OutboxScheduler.schedulePeriodicSync(this)
    }
}
