package com.zedread.pos.data.repository

import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.PosPrintTemplateElementDto
import com.zedread.pos.data.local.TokenStore
import com.zedread.pos.data.local.dao.CompanyProfileDao
import com.zedread.pos.data.local.dao.PrintTemplateDao
import com.zedread.pos.data.local.dao.PrinterLocationDao
import com.zedread.pos.data.local.entity.CompanyProfileCacheEntity
import com.zedread.pos.data.local.entity.PrintTemplateEntity
import com.zedread.pos.data.local.entity.PrinterLocationEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages printer-location/print-template/company-profile data: fetch on
 * sync + Room cache, same `refresh()`-then-replace shape as
 * [CatalogRepository]. Deliberately no live per-print network call — "add
 * all backend printing requirements into sync and store locally, do not poll
 * these from server only update on a sync" (the printing feature's own
 * requirement, same convention [CatalogRepository]/[SettingsRepository]
 * already follow).
 */
@Singleton
class PrintConfigRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
    private val printerLocationDao: PrinterLocationDao,
    private val printTemplateDao: PrintTemplateDao,
    private val companyProfileDao: CompanyProfileDao,
    private val moshi: Moshi,
) {
    private val elementsListAdapter =
        moshi.adapter<List<PosPrintTemplateElementDto>>(
            Types.newParameterizedType(List::class.java, PosPrintTemplateElementDto::class.java)
        )

    fun observePrinterLocations(): Flow<List<PrinterLocationEntity>> = printerLocationDao.observeAll()

    /**
     * Fetch fresh print config from the network and replace the Room cache.
     * Throws on network error — caller decides whether to show stale cache
     * (same convention as [CatalogRepository.refresh]).
     */
    suspend fun refresh() {
        val token = tokenStore.accessToken.firstOrNull()
            ?: error("No access token — cannot fetch print config")
        val siteId = tokenStore.siteId.firstOrNull()
            ?: error("No site ID — cannot fetch print config")
        val bearer = "Bearer $token"

        val config = api.getPrintConfig(bearer, siteId)

        val locations = config.printerLocations.map { dto ->
            PrinterLocationEntity(id = dto.id, ref = dto.ref, name = dto.name, copyCount = dto.copyCount)
        }
        val templates = config.templates.map { dto ->
            PrintTemplateEntity(
                id = dto.id,
                templateType = dto.templateType,
                printerLocationId = dto.printerLocationId,
                name = dto.name,
                elementsJson = elementsListAdapter.toJson(dto.elements),
            )
        }

        printerLocationDao.replaceAll(locations)
        printTemplateDao.replaceAll(templates)
        companyProfileDao.upsert(
            CompanyProfileCacheEntity(
                logoUrl = config.companyProfile.logoUrl,
                brandName = config.companyProfile.brandName,
                storeName = config.companyProfile.storeName,
                address = config.companyProfile.address,
                phone = config.companyProfile.phone,
                abn = config.companyProfile.abn,
            )
        )
    }

    /** Decode one cached template's elements JSON — used by TemplateDocketRenderer. */
    fun decodeElements(elementsJson: String): List<PosPrintTemplateElementDto> =
        elementsListAdapter.fromJson(elementsJson) ?: emptyList()

    suspend fun getTemplateByType(templateType: String): PrintTemplateEntity? = printTemplateDao.getByType(templateType)

    suspend fun getDocketForLocation(printerLocationId: String): PrintTemplateEntity? =
        printTemplateDao.getDocketForLocation(printerLocationId)

    suspend fun getCompanyProfile(): CompanyProfileCacheEntity? = companyProfileDao.get()

    /** Wipe the cache (called on logout). */
    suspend fun clearCache() {
        printerLocationDao.clearAll()
        printTemplateDao.clearAll()
        companyProfileDao.clear()
    }
}
