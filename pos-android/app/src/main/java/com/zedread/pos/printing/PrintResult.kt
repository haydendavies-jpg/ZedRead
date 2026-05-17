package com.zedread.pos.printing

/** Result type returned by all print service implementations. */
sealed class PrintResult {
    object Success : PrintResult()
    data class Failure(val reason: String) : PrintResult()
}
