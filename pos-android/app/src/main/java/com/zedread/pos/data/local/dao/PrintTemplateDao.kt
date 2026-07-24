package com.zedread.pos.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.zedread.pos.data.local.entity.PrintTemplateEntity

/** Room DAO for cached print templates (see PrintConfigRepository.refresh). */
@Dao
interface PrintTemplateDao {

    /** The one brand-wide singleton template of a given type ('invoice' | 'register_summary' | 'cash_in_slip'). */
    @Query("SELECT * FROM print_templates WHERE template_type = :templateType LIMIT 1")
    suspend fun getByType(templateType: String): PrintTemplateEntity?

    /** The 'docket' template for one printer location. */
    @Query("SELECT * FROM print_templates WHERE printer_location_id = :printerLocationId AND template_type = 'docket' LIMIT 1")
    suspend fun getDocketForLocation(printerLocationId: String): PrintTemplateEntity?

    /** Replace the entire cache after a successful network fetch. */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun replaceAll(templates: List<PrintTemplateEntity>)

    /** Wipe the cache (called on logout). */
    @Query("DELETE FROM print_templates")
    suspend fun clearAll()
}
