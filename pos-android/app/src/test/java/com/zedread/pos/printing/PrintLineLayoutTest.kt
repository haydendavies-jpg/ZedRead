package com.zedread.pos.printing

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Pure-function tests for the character-padding algorithm shared with the
 * portal's `printTemplateLayout.ts` (see that file's own doc) — no Room/
 * Android dependencies, so these run on the plain JVM.
 */
class PrintLineLayoutTest {

    @Test
    fun `alignText left pads on the right to fill width`() {
        assertEquals("Hi      ", alignText("Hi", 8, "left"))
    }

    @Test
    fun `alignText right pads on the left to fill width`() {
        assertEquals("      Hi", alignText("Hi", 8, "right"))
    }

    @Test
    fun `alignText center splits padding with extra space on the right`() {
        // width 9, text length 2 -> 7 spare -> 3 left, 4 right
        assertEquals("   Hi    ", alignText("Hi", 9, "center"))
    }

    @Test
    fun `alignText truncates text longer than width instead of wrapping`() {
        assertEquals("Hello", alignText("Hello World", 5, "left"))
    }

    @Test
    fun `alignText justify spreads a single word same as left`() {
        assertEquals("Hi      ", alignText("Hi", 8, "justify"))
    }

    @Test
    fun `alignText justify distributes space evenly between words filling the width exactly`() {
        // 3 one-letter words, width 11 -> 8 spare chars split across 2 gaps -> 4 spaces each
        assertEquals("a    b    c", alignText("a b c", 11, "justify"))
    }

    @Test
    fun `threeColumnLine spreads left middle and right across the full width`() {
        val line = threeColumnLine("Coffee", "x2", "$8.00", 32)
        assertEquals(32, line.length)
        assertEquals(true, line.startsWith("Coffee"))
        assertEquals(true, line.trimEnd().endsWith("$8.00"))
    }

    @Test
    fun `dividerLine fills the width with dashes`() {
        assertEquals("-".repeat(32), dividerLine(32))
    }

    @Test
    fun `formatCentsForPrint formats negative cents with a leading sign`() {
        assertEquals("-$1.50", formatCentsForPrint(-150))
    }

    @Test
    fun `formatCentsForPrint formats positive cents without a sign`() {
        assertEquals("$9.05", formatCentsForPrint(905))
    }

    @Test
    fun `renderedLinesToEscPosBytes produces non-empty bytes containing each line's text`() {
        val bytes = renderedLinesToEscPosBytes(listOf(RenderedLine("Hello", isBold = true)))
        val text = String(bytes, Charsets.UTF_8)
        assert(text.contains("Hello"))
    }
}
