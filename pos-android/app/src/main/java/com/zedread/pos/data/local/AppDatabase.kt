package com.zedread.pos.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import com.zedread.pos.data.local.dao.CategoryDao
import com.zedread.pos.data.local.dao.ProductDao
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.ProductEntity

/** Room database — caches catalog data for offline display. */
@Database(
    entities = [ProductEntity::class, CategoryEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun productDao(): ProductDao
    abstract fun categoryDao(): CategoryDao
}
