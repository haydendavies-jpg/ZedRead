package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.zedread.pos.data.local.entity.ProductModifierCacheEntity

/** Room DAO for the per-product modifier-definition cache — see [ProductModifierCacheEntity]'s doc. */
@Dao
interface ProductModifierCacheDao {

    @Query("SELECT * FROM product_modifier_cache WHERE productId = :productId")
    suspend fun get(productId: String): ProductModifierCacheEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: ProductModifierCacheEntity)

    /** Wipe the cache (called on logout). */
    @Query("DELETE FROM product_modifier_cache")
    suspend fun clearAll()
}
