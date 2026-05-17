package com.zedread.pos

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

/** Application entry point. @HiltAndroidApp triggers Hilt code generation. */
@HiltAndroidApp
class PosApplication : Application()
