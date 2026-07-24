package com.zedread.pos.data.repository

import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import com.zedread.pos.data.api.PosApiService
import com.zedread.pos.data.api.ProductModifierGroupDto
import com.zedread.pos.data.api.ProductUpdateRequest
import com.zedread.pos.data.local.TokenStore
import com.zedread.pos.data.local.dao.CategoryDao
import com.zedread.pos.data.local.dao.ProductDao
import com.zedread.pos.data.local.dao.ProductModifierCacheDao
import com.zedread.pos.data.local.entity.CategoryEntity
import com.zedread.pos.data.local.entity.ProductEntity
import com.zedread.pos.data.local.entity.ProductModifierCacheEntity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import javax.inject.Inject
import javax.inject.Singleton

/** Caps how many modifier-detail fetches [CatalogRepository] runs at once during a prefetch — enough to warm the cache quickly without hammering the backend on a large catalog. */
private const val MODIFIER_PREFETCH_CONCURRENCY = 6

/** Manages catalog data: network fetch + Room cache with offline fallback. */
@Singleton
class CatalogRepository @Inject constructor(
    private val api: PosApiService,
    private val tokenStore: TokenStore,
    private val productDao: ProductDao,
    private val categoryDao: CategoryDao,
    private val modifierCacheDao: ProductModifierCacheDao,
    private val moshi: Moshi,
) {
    // Best-effort background refresh for the modifier cache — fire-and-forget,
    // outlives any single screen's viewModelScope since this repository is a
    // Singleton. A failed refresh here just leaves the existing cached copy in
    // place for next time; getProductModifiers already returned its own
    // result to the caller before this runs.
    private val backgroundScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val modifierListAdapter =
        moshi.adapter<List<ProductModifierGroupDto>>(
            Types.newParameterizedType(List::class.java, ProductModifierGroupDto::class.java)
        )

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
                ref = dto.ref,
                categoryId = dto.categoryId,
                name = dto.name,
                description = dto.description,
                basePriceCents = dto.basePriceCents,
                priceExCents = dto.priceExCents,
                isTaxable = dto.isTaxable,
                photoUrl = dto.photoUrl,
                displayOrder = dto.displayOrder,
                isActive = dto.isActive,
                isSoldOut = dto.isSoldOut,
                categoryColor = dto.categoryColor,
                modifierNames = dto.modifierNames,
                printerLocationId = dto.printerLocationId,
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

        // Warm the modifier cache for every product that has modifiers, so the
        // customise sheet is a cache hit (see getProductModifiers) from the
        // first tap of a shift, not just the second tap of a given product —
        // user-testing feedback that a visible load on opening the sheet was
        // still common in practice. Fire-and-forget: refresh() itself must not
        // block on this, and a failed prefetch for one product just leaves it
        // to fall back to the ordinary cache-miss network fetch on first tap.
        val productIdsWithModifiers = products.filter { !it.modifierNames.isNullOrBlank() }.map { it.id }
        if (productIdsWithModifiers.isNotEmpty()) {
            backgroundScope.launch { prefetchModifierCaches(productIdsWithModifiers) }
        }
    }

    /** Concurrently warms [ProductModifierCacheEntity] for each id — see [refresh]'s call site. */
    private suspend fun prefetchModifierCaches(productIds: List<String>) {
        val semaphore = Semaphore(MODIFIER_PREFETCH_CONCURRENCY)
        coroutineScope {
            productIds.forEach { id ->
                launch { semaphore.withPermit { runCatching { refreshModifierCache(id) } } }
            }
        }
    }

    /** Wipe cached catalog on logout. */
    suspend fun clearCache() {
        productDao.clearAll()
        categoryDao.clearAll()
        modifierCacheDao.clearAll()
    }

    /**
     * Push the long-press popup's sold-out toggle to the backend, then patch
     * the local cache from the confirmed response — mirrors
     * SettingsRepository.saveAsDefault's "patch from the response, don't
     * refetch" convention. Throws on network error; the caller (SellViewModel)
     * leaves the cached/displayed state untouched when that happens, since a
     * failed write must not silently look like it took effect.
     */
    suspend fun setSoldOut(productId: String, isSoldOut: Boolean) {
        val token = tokenStore.accessToken.firstOrNull()
            ?: error("No access token — cannot update product")
        val updated = api.updateProduct("Bearer $token", productId, ProductUpdateRequest(isSoldOut = isSoldOut))
        productDao.setSoldOut(productId, updated.isSoldOut)
    }

    /**
     * Fetch a product's attached modifier groups, fully nested with options —
     * powers the Register screen's modifier customise sheet.
     *
     * Stale-while-revalidate: a cached copy (see [ProductModifierCacheEntity])
     * returns immediately with no network wait, while a background refresh
     * silently updates the cache for next time — user-testing feedback that
     * every tap on a modified product visibly loaded, even on a repeat tap of
     * the same item. [refresh] also proactively warms this cache for every
     * product with modifiers, so in practice this is a cache hit from the
     * first tap of a shift onward; only a product added/modified since the
     * last catalog sync still pays a first-tap network wait. A failed
     * background refresh is swallowed — the cashier already has the
     * (still-valid) cached copy on screen.
     */
    suspend fun getProductModifiers(productId: String): List<ProductModifierGroupDto> {
        val cached = peekCachedProductModifiers(productId)
        if (cached != null) {
            backgroundScope.launch { runCatching { refreshModifierCache(productId) } }
            return cached
        }
        return refreshModifierCache(productId)
    }

    /**
     * Cache-only read, no network — lets the caller decide whether to show a
     * loading state before calling [getProductModifiers] (skip it on a cache
     * hit, since that call then returns near-instantly too).
     */
    suspend fun peekCachedProductModifiers(productId: String): List<ProductModifierGroupDto>? =
        modifierCacheDao.get(productId)?.let { modifierListAdapter.fromJson(it.json) }

    /** Network fetch + cache write for one product's modifier groups — the shared body behind both cache-hit and cache-miss paths above. */
    private suspend fun refreshModifierCache(productId: String): List<ProductModifierGroupDto> {
        val token = tokenStore.accessToken.firstOrNull()
            ?: error("No access token — cannot fetch modifiers")
        val groups = api.getProductModifiersDetailed("Bearer $token", productId)
        modifierCacheDao.upsert(ProductModifierCacheEntity(productId, modifierListAdapter.toJson(groups)))
        return groups
    }
}
