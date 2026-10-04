# The separately loaded test APK needs these shared APIs after application R8.
# This rule file belongs only to migrationQa, never release/legacyBeta.
-keep class androidx.tracing.** { *; }
-keep class androidx.room.** { *; }
-keep class androidx.datastore.** { *; }
-keep class kotlin.** { *; }
-keep class kotlinx.coroutines.** { *; }
-keep class com.liberivixer.youtubeharvester.data.** { *; }
-keep class com.liberivixer.youtubeharvester.model.** { *; }
-keep class com.liberivixer.youtubeharvester.ui.LocaleController { *; }
-keep class com.liberivixer.youtubeharvester.download.HarvestSessionStore { *; }
