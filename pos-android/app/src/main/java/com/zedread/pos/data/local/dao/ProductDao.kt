package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.zedread.pos.data.local.entity.ProductEntity
import kotlinx.coroutines.flow.Flow

/** Room DAO for cached product catalog. */
@Dao
interface ProductDao {

    /** Observe all cached active products ordered for display. */
    @Query("SELECT * FROM products WHERE is_active = 1 ORDER BY display_order ASC")
    fun observeAll(): Flow<List<ProductEntity>>

    /** Observe active products filtered by category. */
    @Query("SELECT * FROM products WHERE is_active = 1 AND category_id = :categoryId ORDER BY display_order ASC")
    fun observeByCategory(categoryId: String): Flow<List<ProductEntity>>

    /** Replace the entire cache after a successful network fetch. */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun replaceAll(products: List<ProductEntity>)

    /** Patch one cached row's sold-out flag in place — the long-press popup's toggle, applied optimistically after the API call succeeds. */
    @Query("UPDATE products SET is_sold_out = :isSoldOut WHERE id = :productId")
    suspend fun setSoldOut(productId: String, isSoldOut: Boolean)

    /** Wipe the cache (called on logout). */
    @Query("DELETE FROM products")
    suspend fun clearAll()
}
