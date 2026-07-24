package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.zedread.pos.data.local.entity.CompanyProfileCacheEntity

/** Room DAO for the single cached company-profile row (see PrintConfigRepository.refresh). */
@Dao
interface CompanyProfileDao {

    @Query("SELECT * FROM company_profile_cache WHERE id = 0 LIMIT 1")
    suspend fun get(): CompanyProfileCacheEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(profile: CompanyProfileCacheEntity)

    @Query("DELETE FROM company_profile_cache")
    suspend fun clear()
}
