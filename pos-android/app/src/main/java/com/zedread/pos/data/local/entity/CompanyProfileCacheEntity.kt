package com.zedread.pos.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Room entity caching the site's resolved company-profile fields (logo,
 * brand/store name, address, phone, ABN) — a single row, [id] fixed at 0,
 * upserted whole on every GET /pos/print-config sync. Android has no other
 * company-profile fetch; this is what [com.zedread.pos.printing.TemplateDocketRenderer]
 * reads for every template's LOGO/BRAND_NAME/STORE_NAME/ADDRESS/STORE_PHONE/ABN fields.
 */
@Entity(tableName = "company_profile_cache")
data class CompanyProfileCacheEntity(
    @PrimaryKey val id: Int = 0,
    @ColumnInfo(name = "logo_url") val logoUrl: String?,
    @ColumnInfo(name = "brand_name") val brandName: String,
    @ColumnInfo(name = "store_name") val storeName: String,
    val address: String,
    val phone: String?,
    val abn: String?,
)
