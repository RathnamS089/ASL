# Verification record

Environment: macOS arm64, Apple Swift 6.3.3, Command Line Tools selected at `/Library/Developer/CommandLineTools`. Full Xcode and XCTest were unavailable.

| Check | Actual result |
| --- | --- |
| Core package compilation (`swift build`) | Passed |
| Standalone core executable | 11 checks passed |
| Swift frontend syntax parsing: app and test sources | Passed |
| `plutil -lint`: project.pbxproj and Info.plist | Passed |
| Project object references and source-file paths | Passed |
| Shared scheme XML and asset JSON parsing | Passed |
| Core XCTest suite (`swift test`) | Attempted; blocked by `no such module 'XCTest'` |
| iOS simulator app build (`xcodebuild … build`) | Attempted; blocked because full Xcode is not installed/selected |
| Hosted view-model tests, UI rendering, simulator/device acceptance | Not run |

The core package compiled successfully; **the iOS application has not been compiled or run in this environment**. Syntax and plist checks do not establish SwiftUI type correctness or simulator behavior.

The first SwiftPM attempt could not write the default Clang module cache. Redirecting caches to `/tmp` resolved that issue; the subsequent unit-test attempt compiled the core and stopped at the missing XCTest module.

Commands used successfully for the core build and standalone checks:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/visualiser-module-cache \
  SWIFTPM_MODULECACHE_OVERRIDE=/tmp/visualiser-module-cache \
  swift build --package-path VisualiserCore \
  --scratch-path /tmp/visualiser-build \
  --cache-path /tmp/visualiser-package-cache --disable-sandbox

swiftc -module-cache-path /tmp/visualiser-module-cache \
  -parse-as-library VisualiserCore/Sources/VisualiserCore/*.swift \
  Scripts/VerifyCore.swift -o /tmp/visualiser-core-checks
/tmp/visualiser-core-checks
```

The 11 standalone checks cover deterministic labeled mock output, cancellation, missing video validation, snake_case JSON round trip, empty-response validation, backend URL validation, pause, resume/completion, replay, reset and reduced-motion reveal.

The repository also contains 12 core XCTest tests (including API request/response tests with an injected HTTP client) and 5 hosted view-model tests. Run them with Xcode’s Test action before relying on an iOS build. Follow the manual acceptance pass in `README.md` for PhotosPicker, AVPlayer, Dynamic Type and VoiceOver.
