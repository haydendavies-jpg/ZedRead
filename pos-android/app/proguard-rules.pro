# Keep Moshi-generated adapters.
-keep class com.zedread.pos.data.api.**JsonAdapter { *; }
-keep @com.squareup.moshi.JsonClass class * { *; }

# Retrofit keeps its own annotations; keep our service interface.
-keep interface com.zedread.pos.data.api.PosApiService { *; }

# Hilt generated code.
-dontwarn dagger.hilt.**
