package com.zedread.pos.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import com.zedread.pos.data.local.dao.CategoryDao
import com.zedread.pos.data.local.dao.InvoiceCacheDao
import com.zedread.pos.data.local.dao.OutboxDao
import com.zedread.pos.data.local.dao.ProductDao
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.InvoiceCacheEntity
import com.zedread.pos.data.local.entity.OutboxItemEntity
import com.zedread.pos.data.local.entity.ProductEntity

/**
 * Room database. `products`/`categories` are cache-only (destructive
 * migration is safe there — see DatabaseModule). `outbox_items` is NOT
 * cache — it's the durable queue of writes the device hasn't confirmed the
 * server received yet, so it goes through [DatabaseModule]'s explicit
 * `MIGRATION_2_3` instead, preserving any pending rows across an app
 * update. `invoice_cache` is a re-derivable read cache like products, but
 * shares the same migration since both tables were added together.
 */
@Database(
    entities = [ProductEntity::class, CategoryEntity::class, OutboxItemEntity::class, InvoiceCacheEntity::class],
    // + products.is_sold_out (long-press sold-out popup) — no explicit
    // Migration needed, relies on fallbackToDestructiveMigration same as
    // every other products/categories-only hop (see DatabaseModule).
    version = 6,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun productDao(): ProductDao
    abstract fun categoryDao(): CategoryDao
    abstract fun outboxDao(): OutboxDao
    abstract fun invoiceCacheDao(): InvoiceCacheDao
}
