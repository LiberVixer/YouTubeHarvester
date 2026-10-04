# yt-dlp response models are populated reflectively by Jackson.
-keep class com.yausername.youtubedl_android.mapper.** { *; }
-keepattributes Signature,InnerClasses,EnclosingMethod,*Annotation*
# Bundled runtime archives use ZIP/Deflate. Commons Compress also references
# optional XZ/Zstandard backends; these formats are not installed or accepted here.
-dontwarn com.github.luben.zstd.ZstdInputStream
-dontwarn org.tukaani.xz.MemoryLimitException
-dontwarn org.tukaani.xz.SingleXZInputStream
-dontwarn org.tukaani.xz.XZInputStream
