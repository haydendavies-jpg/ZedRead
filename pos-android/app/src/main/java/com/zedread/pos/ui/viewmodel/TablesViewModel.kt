package com.zedread.pos.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zedread.pos.data.api.PosDiningTableStatusDto
import com.zedread.pos.data.api.PosTableMapDetailDto
import com.zedread.pos.data.repository.TableMapRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Owns the Tables / Floor Map screen (Android POS Phase 4) — live floor
 * status, table selection, and the merge-flow state machine. Mirrors
 * README-tables-floormap.md's "State Management" section, adapted from the
 * mockup's local seed data to real polling against `GET /pos/table-map`.
 *
 * `GET /pos/table-map?site_id=` returns *every* published map for the site
 * in one call, so switching the active floor tab ([selectFloor]) is a purely
 * local re-slice of already-fetched data — it never triggers a new network
 * call, only [refresh]'s poll loop does.
 *
 * **Zone grouping simplification**: the mockup's seed data groups each table
 * under a named zone ("Indoor · T3") via a client-side `zone` property that
 * has no backend equivalent — `table_map_shapes` carries no table-to-zone
 * relationship, only sibling x/y-positioned shapes on the same map. The
 * label prefix used here is the floor map's own `name` instead
 * (e.g. "Ground Floor · T3") — see [tableDisplayLabel].
 *
 * **Total badge / selection-bar "Total" chip**: the mockup's seed data
 * invents a `total` field per table; `PosDiningTableStatus` carries no
 * invoice total (this contract deliberately doesn't join to Invoice), so
 * that badge/chip is omitted rather than fabricated — a real gap, not a
 * silent simplification.
 */
@HiltViewModel
class TablesViewModel @Inject constructor(
    private val repo: TableMapRepository,
) : ViewModel() {

    private val _floors = MutableStateFlow<List<PosTableMapDetailDto>>(emptyList())
    val floors: StateFlow<List<PosTableMapDetailDto>> = _floors.asStateFlow()

    private val _activeFloorId = MutableStateFlow<String?>(null)
    val activeFloorId: StateFlow<String?> = _activeFloorId.asStateFlow()

    private val _selectedShapeId = MutableStateFlow<String?>(null)
    val selectedShapeId: StateFlow<String?> = _selectedShapeId.asStateFlow()

    private val _mergeAnchorShapeId = MutableStateFlow<String?>(null)
    val mergeAnchorShapeId: StateFlow<String?> = _mergeAnchorShapeId.asStateFlow()

    private val _toast = MutableStateFlow<String?>(null)
    val toast: StateFlow<String?> = _toast.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** Shape id currently prompting the "seat this table" covers dialog, or null. */
    private val _seatDialogShapeId = MutableStateFlow<String?>(null)
    val seatDialogShapeId: StateFlow<String?> = _seatDialogShapeId.asStateFlow()

    private val _isActionInFlight = MutableStateFlow(false)
    val isActionInFlight: StateFlow<Boolean> = _isActionInFlight.asStateFlow()

    /** The floor currently on screen, or null before the first successful fetch. */
    fun activeFloor(): PosTableMapDetailDto? = _floors.value.firstOrNull { it.id == _activeFloorId.value }

    /** Resolve a shape by id within the *currently active floor only* — selection never crosses floors. */
    fun findShape(shapeId: String?): PosDiningTableStatusDto? =
        shapeId?.let { id -> activeFloor()?.shapes?.firstOrNull { it.id == id } }

    /** "<Floor name> · <table label>" — see the class doc's zone-grouping note. */
    fun tableDisplayLabel(shape: PosDiningTableStatusDto): String =
        "${activeFloor()?.name ?: ""} · ${shape.label}"

    /**
     * Re-fetch every published floor map for the site. Called on an initial
     * load and by the screen's poll loop while it's visible (interval is the
     * screen's concern, not the ViewModel's — see TablesScreen's doc).
     * Silent on failure after the very first successful load, so a
     * transient network hiccup mid-shift doesn't blank an already-rendered
     * floor map out from under the operator.
     */
    fun refresh() {
        viewModelScope.launch {
            _isLoading.value = _floors.value.isEmpty()
            runCatching { repo.getTableMap() }
                .onSuccess { result ->
                    _floors.value = result
                    if (_activeFloorId.value == null || result.none { it.id == _activeFloorId.value }) {
                        _activeFloorId.value = result.minByOrNull { it.sortOrder }?.id
                    }
                    _error.value = null
                }
                .onFailure { e -> if (_floors.value.isEmpty()) _error.value = e.message ?: "Failed to load table map" }
            _isLoading.value = false
        }
    }

    /** Floor tab switch — clears selection/merge-arming per the README's "Floor switch" behavior. */
    fun selectFloor(floorId: String) {
        _activeFloorId.value = floorId
        _selectedShapeId.value = null
        _mergeAnchorShapeId.value = null
    }

    /**
     * Tap a table tile. While a merge is armed ([mergeAnchorShapeId] set),
     * tapping any *other* tile completes the merge instead of changing the
     * selection — tapping the armed tile itself is a no-op (Cancel merge on
     * the selection bar's own button is the only way to disarm).
     */
    fun tapTile(shapeId: String) {
        val anchor = _mergeAnchorShapeId.value
        if (anchor != null) {
            if (shapeId != anchor) performMerge(anchor, shapeId)
            return
        }
        _selectedShapeId.value = shapeId
    }

    /** Close (✕) — clears selection and any armed merge. */
    fun clearSelection() {
        _selectedShapeId.value = null
        _mergeAnchorShapeId.value = null
    }

    fun clearToast() { _toast.value = null }

    /**
     * Selection bar's Merge / Cancel merge toggle. Only meaningful for a
     * seated/ordered/bill table — an open table has no session to merge, so
     * the selection bar hides this button for one (see TablesScreen).
     */
    fun toggleMergeArm() {
        val selected = _selectedShapeId.value ?: return
        if (_mergeAnchorShapeId.value == selected) {
            _mergeAnchorShapeId.value = null
            return
        }
        _mergeAnchorShapeId.value = selected
        val label = findShape(selected)?.let { tableDisplayLabel(it) } ?: "table"
        _toast.value = "Tap another table to merge with $label"
    }

    private fun performMerge(anchorShapeId: String, targetShapeId: String) {
        val anchor = findShape(anchorShapeId)
        val target = findShape(targetShapeId)
        val anchorSession = anchor?.sessionId
        val targetSession = target?.sessionId
        if (anchorSession == null || targetSession == null) {
            _toast.value = "Both tables must be seated to merge"
            _mergeAnchorShapeId.value = null
            return
        }
        _isActionInFlight.value = true
        viewModelScope.launch {
            runCatching { repo.mergeSessions(anchorSession, targetSession) }
                .onSuccess {
                    _toast.value = "Merged ${anchor.label} + ${target.label}"
                    _mergeAnchorShapeId.value = null
                    refresh()
                }
                .onFailure { e ->
                    _toast.value = e.message ?: "Merge failed"
                    _mergeAnchorShapeId.value = null
                }
            _isActionInFlight.value = false
        }
    }

    /** Opens the covers-entry dialog for an open (unseated) table — see class/screen docs for the "Open order" resolution. */
    fun startSeating(shapeId: String) { _seatDialogShapeId.value = shapeId }

    fun cancelSeating() { _seatDialogShapeId.value = null }

    /** Confirm the covers dialog — seats the table, then refreshes so its tile/selection bar reflect the new session. */
    fun confirmSeating(covers: Int) {
        val shapeId = _seatDialogShapeId.value ?: return
        val shape = findShape(shapeId) ?: return
        val diningTableId = shape.diningTableId ?: return
        _seatDialogShapeId.value = null
        _isActionInFlight.value = true
        viewModelScope.launch {
            runCatching { repo.seatTable(diningTableId, covers) }
                .onSuccess { refresh() }
                .onFailure { e -> _toast.value = e.message ?: "Failed to seat table" }
            _isActionInFlight.value = false
        }
    }

    /** Selection bar's status-advance action for a seated table ("mark ordered"). */
    fun markOrdered(sessionId: String) = runSessionAction { repo.markOrdered(sessionId) }

    /** Selection bar's status-advance action for an ordered table ("needs bill"). */
    fun markBill(sessionId: String) = runSessionAction { repo.markBill(sessionId) }

    /** Clear a table back to 'open' — closes its session. */
    fun clearTable(sessionId: String) {
        _isActionInFlight.value = true
        viewModelScope.launch {
            runCatching { repo.clearSession(sessionId) }
                .onSuccess {
                    clearSelection()
                    refresh()
                }
                .onFailure { e -> _toast.value = e.message ?: "Failed to clear table" }
            _isActionInFlight.value = false
        }
    }

    private fun runSessionAction(action: suspend () -> Unit) {
        _isActionInFlight.value = true
        viewModelScope.launch {
            runCatching { action() }
                .onSuccess { refresh() }
                .onFailure { e -> _toast.value = e.message ?: "Action failed" }
            _isActionInFlight.value = false
        }
    }
}
