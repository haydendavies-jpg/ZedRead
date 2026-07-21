package com.zedread.pos.data.repository

import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.ProductModifierGroupDto
import com.zedread.pos.data.local.TokenStore
import com.zedread.pos.data.local.dao.CategoryDao
import com.zedread.pos.data.local.dao.ProductDao
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.ProductEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.firstOrNull
import javax.inject.Inject
import javax.inject.Singleton

/** Manages catalog data: network fetch + Room cache with offline fallback. */
@Singleton
class CatalogRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
    private val productDao: ProductDao,
    private val categoryDao: CategoryDao,
) {
    /** Observe cached products — emits immediately from Room, then updates after [refresh]. */
    fun observeProducts(categoryId: String? = null): Flow<List<ProductEntity>> =
        if (categoryId != null) productDao.observeByCategory(categoryId)
        else productDao.observeAll()

    /** Observe cached categories. */
    fun observeCategories(): Flow<List<CategoryEntity>> = categoryDao.observeAll()

    /**
     * Fetch fresh catalog from the network and replace the Room cache.
     * Throws on network error — caller decides whether to show stale cache.
     */
    suspend fun refresh() {
        val token = tokenStore.accessToken.firstOrNull()
            ?: error("No access token — cannot fetch catalog")
        val siteId = tokenStore.siteId.firstOrNull()
            ?: error("No site ID — cannot fetch catalog")
        val bearer = "Bearer $token"

        val products = api.getProducts(bearer, siteId).map { dto ->
            ProductEntity(
                id = dto.id,
                categoryId = dto.categoryId,
                name = dto.name,
                description = dto.description,
                basePriceCents = dto.basePriceCents,
                photoUrl = dto.photoUrl,
                displayOrder = dto.displayOrder,
                isActive = dto.isActive,
                categoryColor = dto.categoryColor,
                modifierNames = dto.modifierNames,
            )
        }
        val categories = api.getCategories(bearer, siteId).map { dto ->
            CategoryEntity(
                id = dto.id,
                name = dto.name,
                displayOrder = dto.displayOrder,
                defaultColor = dto.defaultColor,
            )
        }

        productDao.replaceAll(products)
        categoryDao.replaceAll(categories)
    }

    /** Wipe cached catalog on logout. */
    suspend fun clearCache() {
        productDao.clearAll()
        categoryDao.clearAll()
    }

    /**
     * Fetch a product's attached modifier groups, fully nested with options —
     * powers the Register screen's modifier customise sheet. Not cached in
     * Room like the rest of the catalog; the sheet is opened rarely enough
     * (only for products with modifiers) that a fresh network read each time
     * is simpler than adding another cache table.
     */
    suspend fun getProductModifiers(productId: String): List<ProductModifierGroupDto> {
        val token = tokenStore.accessToken.firstOrNull()
            ?: error("No access token — cannot fetch modifiers")
        return api.getProductModifiersDetailed("Bearer $token", productId)
    }
}
