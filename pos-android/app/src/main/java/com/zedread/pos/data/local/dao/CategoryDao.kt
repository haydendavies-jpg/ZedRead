package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.zedread.pos.data.local.entity.CategoryEntity
import kotlinx.coroutines.flow.Flow

/** Room DAO for cached product categories. */
@Dao
interface CategoryDao {

    /** Observe all cached categories ordered for display. */
    @Query("SELECT * FROM categories ORDER BY display_order ASC")
    fun observeAll(): Flow<List<CategoryEntity>>

    /** Replace the entire cache after a successful network fetch. */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun replaceAll(categories: List<CategoryEntity>)

    /** Wipe the cache (called on logout). */
    @Query("DELETE FROM categories")
    suspend fun clearAll()
}
