# Android Build Storage

- Keep only the latest successfully built and verified tester version of APKs
  directly in `android/`, one APK per supported ABI. Keep all current ABIs, not
  just the APK with the newest timestamp. Verify replacement copies and their
  checksums before deleting older versions; a failed build must not remove the
  last working set. Do not apply this pruning to published release archives.
- Check `du -sh app/build` after substantial builds. Review cleanup when it
  exceeds 2 GiB; this is a review threshold, not a hard build limit. After all
  verification has finished, remove regenerable intermediates when useful.
  Preserve current APKs needed for testing, test/lint reports, mapping files,
  checksums, and diagnostics. Never clean while a build or test is running.
- Periodically inspect the Gradle user home's size during build maintenance.
  Prefer pruning the local task-output build cache when it grows excessively
  (review above 2 GiB). Check for Gradle processes across the host first: this
  cache is shared with other projects. Keep lock files and cache metadata.
- Do not indiscriminately delete Gradle dependency caches (`modules-2`), wrapper
  distributions, active-version caches, Android SDK/NDK, bundled runtime source
  archives, signing keys, or local configuration. Offline builds depend on them.
  Old version-specific caches require a separate check that they are unused.
- Cleanup can slow the next build because generated work must be repeated.
  Report disk space recovered and what was preserved. These are maintenance
  rules for build work, not a background scheduled job.
