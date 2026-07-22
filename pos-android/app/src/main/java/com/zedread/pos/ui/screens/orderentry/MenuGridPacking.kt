package com.zedread.pos.ui.screens.orderentry

import com.zedread.pos.data.api.PosMenuButtonDto

/** The portal grid editor's fixed column count (MenuBuilderPage.tsx's `gridTemplateColumns: repeat(6, ...)`). */
const val MENU_GRID_COLUMNS = 6

/** One button resolved to its actual (col, row) cell in a tab's 6-column grid. */
data class PlacedMenuButton(val button: PosMenuButtonDto, val col: Int, val row: Int)

/**
 * Resolve every button in a tab to a concrete (col, row) cell, mirroring the
 * portal grid editor's own `grid-auto-flow: dense` CSS placement: a button
 * with an explicit grid_col/grid_row (dragged to a cell in the editor) is
 * pinned there; everything else dense-packs into the first free cell that
 * fits its width x height, scanning rows top-to-bottom and columns
 * left-to-right — so a later, smaller button can still fill an earlier gap
 * left by a pinned or wider button, same as the CSS engine does. This is a
 * read-only render for the POS (no drag/resize), so a plain greedy scan is
 * sufficient — the portal's own interactive resize/drag logic isn't needed.
 */
fun packMenuButtons(buttons: List<PosMenuButtonDto>): List<PlacedMenuButton> {
    val occupied = mutableListOf<BooleanArray>()

    fun ensureRow(row: Int) {
        while (occupied.size <= row) occupied.add(BooleanArray(MENU_GRID_COLUMNS))
    }

    fun fits(col: Int, row: Int, width: Int, height: Int): Boolean {
        if (col + width > MENU_GRID_COLUMNS) return false
        ensureRow(row + height - 1)
        for (r in row until row + height) {
            for (c in col until col + width) {
                if (occupied[r][c]) return false
            }
        }
        return true
    }

    fun occupy(col: Int, row: Int, width: Int, height: Int) {
        ensureRow(row + height - 1)
        for (r in row until row + height) {
            for (c in col until col + width) occupied[r][c] = true
        }
    }

    val placed = mutableListOf<PlacedMenuButton>()
    val (pinned, unpinned) = buttons.partition { it.gridCol != null && it.gridRow != null }

    for (button in pinned.sortedBy { it.displayOrder }) {
        val width = button.width.coerceIn(1, MENU_GRID_COLUMNS)
        val col = button.gridCol!!.coerceIn(0, MENU_GRID_COLUMNS - width)
        val row = button.gridRow!!.coerceAtLeast(0)
        occupy(col, row, width, button.height)
        placed += PlacedMenuButton(button, col, row)
    }

    for (button in unpinned.sortedBy { it.displayOrder }) {
        val width = button.width.coerceIn(1, MENU_GRID_COLUMNS)
        var placedRow = -1
        var placedCol = -1
        var row = 0
        while (placedCol < 0) {
            for (col in 0..(MENU_GRID_COLUMNS - width)) {
                if (fits(col, row, width, button.height)) {
                    placedCol = col
                    placedRow = row
                    break
                }
            }
            row++
        }
        occupy(placedCol, placedRow, width, button.height)
        placed += PlacedMenuButton(button, placedCol, placedRow)
    }

    return placed
}

/** Total row count spanned by a packed tab — used to size the grid's scrollable container. */
fun totalRows(placed: List<PlacedMenuButton>): Int =
    placed.maxOfOrNull { it.row + it.button.height } ?: 0
