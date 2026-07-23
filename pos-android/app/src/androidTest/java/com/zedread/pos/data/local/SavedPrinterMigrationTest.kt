package com.zedread.pos.data.local

import android.content.Context
import android.database.sqlite.SQLiteConstraintException
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.sqlite.db.SupportSQLiteOpenHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.zedread.pos.di.MIGRATION_8_9
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Verifies MIGRATION_8_9 (schema v8 -> v9, adding `saved_printers`) in
 * isolation. It only CREATEs a new table/index with no dependency on the
 * pre-existing v1-v8 tables, so this opens a throwaway in-memory database and
 * runs the migration directly rather than going through Room's
 * `MigrationTestHelper` — this project doesn't export historical Room
 * schemas (`AppDatabase`'s `exportSchema = false`), which
 * `MigrationTestHelper` needs to replay a real v8 -> v9 upgrade. This test
 * instead asserts the migration's own SQL produces the expected table shape.
 */
@RunWith(AndroidJUnit4::class)
class SavedPrinterMigrationTest {

    @Test
    fun migration_8_9_creates_saved_printers_table_with_unique_mac_index() {
        val context: Context = InstrumentationRegistry.getInstrumentation().targetContext
        val factory = FrameworkSQLiteOpenHelperFactory()
        val configuration = SupportSQLiteOpenHelper.Configuration.builder(context)
            .name(null) // in-memory database
            .callback(
                object : SupportSQLiteOpenHelper.Callback(1) {
                    override fun onCreate(db: SupportSQLiteDatabase) = Unit
                    override fun onUpgrade(db: SupportSQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit
                },
            )
            .build()
        val db = factory.create(configuration).writableDatabase

        MIGRATION_8_9.migrate(db)

        db.execSQL(
            "INSERT INTO saved_printers " +
                "(id, name, driver_id, connection_type, mac_address, last_known_ip, port, is_enabled, created_at_millis) " +
                "VALUES ('p1', 'Test', 'epson_epos2', 'NETWORK', 'AA:BB:CC:DD:EE:FF', '1.1.1.1', 9100, 1, 0)",
        )
        db.query("SELECT name FROM saved_printers WHERE id = 'p1'").use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertEquals("Test", cursor.getString(0))
        }

        // The unique index on mac_address must reject a second row sharing an already-saved MAC.
        var duplicateRejected = false
        try {
            db.execSQL(
                "INSERT INTO saved_printers " +
                    "(id, name, driver_id, connection_type, mac_address, last_known_ip, port, is_enabled, created_at_millis) " +
                    "VALUES ('p2', 'Test 2', 'epson_epos2', 'NETWORK', 'AA:BB:CC:DD:EE:FF', '1.1.1.2', 9100, 1, 0)",
            )
        } catch (e: SQLiteConstraintException) {
            duplicateRejected = true
        }
        assertTrue("Duplicate mac_address should violate the unique index", duplicateRejected)

        db.close()
    }
}
