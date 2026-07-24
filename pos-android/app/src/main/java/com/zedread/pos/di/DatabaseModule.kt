package com.zedread.pos.di

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.zedread.pos.data.local.AppDatabase
import com.zedread.pos.data.local.dao.CategoryDao
import com.zedread.pos.data.local.dao.CompanyProfileDao
import com.zedread.pos.data.local.dao.InvoiceCacheDao
import com.zedread.pos.data.local.dao.OutboxDao
import com.zedread.pos.data.local.dao.PrintTemplateDao
import com.zedread.pos.data.local.dao.PrinterLocationDao
import com.zedread.pos.data.local.dao.ProductDao
import com.zedread.pos.data.local.dao.ProductModifierCacheDao
import com.zedread.pos.data.local.dao.SavedPrinterDao
import com.zedread.pos.data.local.dao.SavedPrinterLocationDao
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

/**
 * Adds products.ref (schema version 3 -> 4) — matches a menu_buttons.product_ref
 * value so the Register screen's menu selector (Android POS Phase 3) can filter
 * the cached catalog to a chosen layout. A real migration, not
 * fallbackToDestructiveMigration, for the same reason MIGRATION_2_3 is one:
 * a destructive rebuild on this hop would also wipe outbox_items/invoice_cache,
 * which must survive an app update. Existing cached rows get an empty ref
 * (refetched with the real value on the very next [CatalogRepository.refresh]
 * call, which already runs on every app launch — never left stale).
 */
private val MIGRATION_3_4 = object : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE products ADD COLUMN ref TEXT NOT NULL DEFAULT ''")
    }
}

/**
 * Adds invoice_cache.ref (schema version 4 -> 5) — the human-readable
 * INV-000001 reference Invoice Search now searches by. A real migration for
 * the same reason MIGRATION_2_3/3_4 are: a destructive rebuild on this hop
 * would also wipe outbox_items. invoice_cache itself is individually
 * re-derivable (AppDatabase's own doc), so an empty default here is fine —
 * corrected on the next GET /invoices backfill (refreshCacheFromServer()),
 * same convention as products.ref's own empty-then-refreshed default.
 */
private val MIGRATION_4_5 = object : Migration(4, 5) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE invoice_cache ADD COLUMN ref TEXT NOT NULL DEFAULT ''")
    }
}

/**
 * Adds `saved_printers` (schema version 8 -> 9) — this terminal's paired
 * printers. Like `outbox_items`, this is NOT a re-derivable cache (a
 * printer's pairing/MAC must survive an app update, and there's nowhere to
 * re-derive it from — it was never backend-synced in the first place), so
 * this is a real migration rather than falling through to
 * `fallbackToDestructiveMigration()`.
 *
 * `internal`, not `private` like the other MIGRATION_* vals above, so
 * `SavedPrinterMigrationTest` (androidTest) can run it directly against a
 * throwaway database — see that test's own doc for why it doesn't go
 * through Room's MigrationTestHelper.
 */
internal val MIGRATION_8_9 = object : Migration(8, 9) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS saved_printers (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                driver_id TEXT NOT NULL,
                connection_type TEXT NOT NULL,
                mac_address TEXT NOT NULL,
                last_known_ip TEXT,
                port INTEGER NOT NULL,
                is_enabled INTEGER NOT NULL,
                last_seen_at_millis INTEGER,
                last_connected_at_millis INTEGER,
                created_at_millis INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            "CREATE UNIQUE INDEX IF NOT EXISTS index_saved_printers_mac_address ON saved_printers(mac_address)"
        )
    }
}

/**
 * Adds `printer_locations`/`print_templates`/`company_profile_cache`
 * (re-derivable print-config caches) and `saved_printer_locations` (NOT
 * re-derivable — a printer's location pairing must survive an app update,
 * same as `saved_printers` itself) plus `products.printer_location_id`
 * (schema version 10 -> 11). A real migration for the same reason
 * [MIGRATION_8_9] is one: `fallbackToDestructiveMigration()` on this hop
 * would wipe `outbox_items`/`saved_printers` too. Every schema change in this
 * version bump must be listed here — Room uses only this migration for the
 * 10->11 hop once it's registered, not a partial fallback.
 */
private val MIGRATION_10_11 = object : Migration(10, 11) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE products ADD COLUMN printer_location_id TEXT")
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS printer_locations (
                id TEXT PRIMARY KEY NOT NULL,
                ref TEXT NOT NULL,
                name TEXT NOT NULL,
                copy_count INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS print_templates (
                id TEXT PRIMARY KEY NOT NULL,
                template_type TEXT NOT NULL,
                printer_location_id TEXT,
                name TEXT NOT NULL,
                elements_json TEXT NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS company_profile_cache (
                id INTEGER PRIMARY KEY NOT NULL,
                logo_url TEXT,
                brand_name TEXT NOT NULL,
                store_name TEXT NOT NULL,
                address TEXT NOT NULL,
                phone TEXT,
                abn TEXT
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS saved_printer_locations (
                printer_id TEXT NOT NULL,
                printer_location_id TEXT NOT NULL,
                PRIMARY KEY(printer_id, printer_location_id),
                FOREIGN KEY(printer_id) REFERENCES saved_printers(id) ON DELETE CASCADE
            )
            """.trimIndent()
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS index_saved_printer_locations_printer_id ON saved_printer_locations(printer_id)"
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS index_saved_printer_locations_printer_location_id ON saved_printer_locations(printer_location_id)"
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
            .addMigrations(MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_8_9, MIGRATION_10_11)
            // last resort only for outbox_items/invoice_cache — the 5->6 hop (products.is_sold_out)
            // falls through here deliberately, same as every other products/categories-only column
            // add, and the 7->8 hop (new product_modifier_cache table) is the same call again —
            // both re-derivable tables it touches refill themselves on the next sync/tap. The 8->9
            // hop (saved_printers) is a real migration above, NOT covered by this fallback — see
            // MIGRATION_8_9's own doc for why. The 9->10 hop (invoice_cache.is_refunded) falls
            // through here again, same reasoning as 5->6/7->8. The 10->11 hop (printing tables +
            // saved_printer_locations) is a real migration above too — see MIGRATION_10_11's own doc.
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideProductDao(db: AppDatabase): ProductDao = db.productDao()

    @Provides
    fun provideCategoryDao(db: AppDatabase): CategoryDao = db.categoryDao()

    @Provides
    fun provideOutboxDao(db: AppDatabase): OutboxDao = db.outboxDao()

    @Provides
    fun provideInvoiceCacheDao(db: AppDatabase): InvoiceCacheDao = db.invoiceCacheDao()

    @Provides
    fun provideProductModifierCacheDao(db: AppDatabase): ProductModifierCacheDao = db.productModifierCacheDao()

    @Provides
    fun provideSavedPrinterDao(db: AppDatabase): SavedPrinterDao = db.savedPrinterDao()

    @Provides
    fun providePrinterLocationDao(db: AppDatabase): PrinterLocationDao = db.printerLocationDao()

    @Provides
    fun providePrintTemplateDao(db: AppDatabase): PrintTemplateDao = db.printTemplateDao()

    @Provides
    fun provideCompanyProfileDao(db: AppDatabase): CompanyProfileDao = db.companyProfileDao()

    @Provides
    fun provideSavedPrinterLocationDao(db: AppDatabase): SavedPrinterLocationDao = db.savedPrinterLocationDao()
}
