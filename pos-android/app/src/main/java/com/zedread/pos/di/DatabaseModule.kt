package com.zedread.pos.di

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.zedread.pos.data.local.AppDatabase
import com.zedread.pos.data.local.dao.CategoryDao
import com.zedread.pos.data.local.dao.InvoiceCacheDao
import com.zedread.pos.data.local.dao.OutboxDao
import com.zedread.pos.data.local.dao.ProductDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Adds the offline write-queue's `outbox_items` table and the `invoice_cache`
 * search table (schema version 2 -> 3). Unlike the catalog tables (safe to
 * wipe — see [DatabaseModule.provideDatabase]'s `fallbackToDestructiveMigration`),
 * `outbox_items` holds unsynced writes that must survive an app update, so
 * this path is a real migration rather than a destructive rebuild.
 */
private val MIGRATION_2_3 = object : Migration(2, 3) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS outbox_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                operation TEXT NOT NULL,
                client_ref TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                last_error TEXT,
                created_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS invoice_cache (
                id TEXT PRIMARY KEY NOT NULL,
                status TEXT NOT NULL,
                total_cents INTEGER NOT NULL,
                created_at_millis INTEGER NOT NULL,
                payment_method TEXT,
                is_synced INTEGER NOT NULL
            )
            """.trimIndent()
        )
    }
}

/** Provides the Room database and its DAOs. */
@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, "zedread_pos.db")
            .addMigrations(MIGRATION_2_3)
            .fallbackToDestructiveMigration() // last resort only — MIGRATION_2_3 handles the one hop that exists today
            .build()

    @Provides
    fun provideProductDao(db: AppDatabase): ProductDao = db.productDao()

    @Provides
    fun provideCategoryDao(db: AppDatabase): CategoryDao = db.categoryDao()

    @Provides
    fun provideOutboxDao(db: AppDatabase): OutboxDao = db.outboxDao()

    @Provides
    fun provideInvoiceCacheDao(db: AppDatabase): InvoiceCacheDao = db.invoiceCacheDao()
}
