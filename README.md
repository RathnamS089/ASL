# VISUALISER

Sign to your phone's camera, and VISUALISER writes the signs out as moving type. Everything runs on one Apple M4 Mac: a React web app, a Go API, a Python recognizer (MediaPipe hands and face landmarks with an MLX transformer trained on Google ISLR), and a fine-tuned Qwen3.5-2B that turns glosses into sentences. Phones connect privately over Tailscale.

**Start here:** [INSTRUCTIONS.md](INSTRUCTIONS.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/DEVELOPMENT_SETUP.md](docs/DEVELOPMENT_SETUP.md#quick-start-recommended-one-mac-phones-over-tailscale)

```bash
bin/run.sh
```

`run.sh` starts the generator, the ML service and the Go API, with Go serving the web app at http://127.0.0.1:8080. Then:

```bash
bin/expose.sh
```

That prints a private `https://….ts.net` address for your phone.

| Folder | What | Tests |
| --- | --- | --- |
| `web/` | React camera app with kinetic typography | `npm test` (16) |
| `backend-go/` | Go API: validation, queue, rate limit, ML client, static serving | `go test -race ./...` |
| `ml-service/` | Recognizer, generator, LoRA fine-tuning, ISLR training | `.venv/bin/python -m pytest` (51) |
| `contracts/` | Shared JSON examples | `python3 contracts/check_examples.py` |

---

## Earlier native iOS client

A native SwiftUI frontend for sign-language video-to-text, expressed through kinetic typography. The app uses a near-black canvas, warm white serif typography, violet word accents and lime actions. Supports iPhone and iPad with iOS 17 or later.

This repository was empty. There was no existing Swift project or deployment target; iOS 17 was chosen for the initial project. No backend, authentication, database or ML implementation is included.

## Run the app

1. Install full **Xcode 15 or later**, including an iOS simulator runtime.
2. Open `Visualiser.xcodeproj`.
3. Select the **Visualiser** scheme and an iPhone or iPad simulator.
4. Press **⌘R**.
5. Tap **Try the sample demo**. No server, account or video is required.

For a physical device, select your development team under Signing & Capabilities and change `com.example.visualiser` to your own unique bundle identifier. The simulator does not need a development team.

To try import, add a video to the simulator’s Photos library by dragging a MOV/MP4 onto the simulator, then choose **Import a video**. PhotosPicker loads the selected video into a temporary app-owned location, validates playback and duration with AVFoundation, and shows a native player. The displayed filename is the name supplied by the picker, which may differ from the original library filename. Replacement, removal and returning Home release the temporary file.

## Demo behavior

- Mock mode is enabled by default and is saved in device preferences.
- Every mock request returns **“Every voice deserves to be seen.”** after a cancellable three-second delay.
- The sentence and sign timings are fixed fixtures, unrelated to imported video content.
- The Home preview uses **“Hello, world.”**
- “Try the sample demo” always uses the mock, even with Real API selected.
- Processing labels illustrate the planned workflow; no percentages or completed ML stages are reported.
- No network request is made by the mock service.
- Result playback supports play, pause, replay, reset and 0.5×–2× speed. Reset hides the visible words until playback restarts.
- System Reduce Motion takes priority over the app preference. Reduced-motion playback shows the whole sentence immediately. VoiceOver reads the full sentence as one accessible element and avoids automatic word playback on entry.

The system Photos picker does not require broad photo-library authorization. The app therefore does not request it. A cancelled selection leaves the current video unchanged; failed transfers (including unavailable iCloud media) show recovery guidance and a sample-demo action. Restricted/unavailable library access also has an always-available Home/sample route. No camera or microphone access is requested.

## Structure

```text
Visualiser.xcodeproj/       App + hosted unit-test target; shared Visualiser scheme
Visualiser/
  App/                     SwiftUI entry point, shared view-model ownership
  Models/                  Imported video and file-based Transferable
  ViewModels/              Navigation/translation, settings, playback orchestration
  Components/              Palette, buttons, badges, wrapping word layout
  Views/                   Home, import, processing, result, settings
  Resources/               Info.plist and accent asset
VisualiserCore/
  Sources/VisualiserCore/   Codable DTOs, service protocols, mock, URLSession adapter,
                           API configuration, pure playback state
  Tests/                   Core unit tests with an injected HTTP test double
VisualiserTests/           Main-actor view-model tests
Scripts/VerifyCore.swift   Standalone core checks when XCTest is unavailable
```

Views call main-actor view models; networking lives behind `TranslationService` and `HTTPClient`. File uploads use URLSession’s file API rather than loading the entire video into memory. Import and translation tasks are cancellable; request identities prevent stale results from replacing newer state.

## Future Go API integration

Real API mode is an **unverified adapter for a provisional contract**, not an included backend. Enter your URL in Settings; the connection-test action appears only with Real API selected and a valid URL. A successful health check does not establish translation endpoint compatibility.

- `GET {baseURL}/health`: any 2xx response indicates connectivity.
- `POST {baseURL}/v1/translations`: raw video request body (not multipart).
- Content type: `video/mp4`, `video/quicktime`, `video/x-m4v`, or `application/octet-stream` for other playable formats.
- Successful synchronous response: 2xx JSON, with snake_case fields:

```json
{
  "id": "translation-001",
  "sentence": "Hello, world.",
  "signs": [
    { "label": "HELLO", "start_seconds": 0.0, "end_seconds": 1.2 }
  ],
  "is_mock": false
}
```

Empty sentences, invalid timings, invalid JSON and non-2xx responses become recoverable errors. No confidence values are invented. No polling or streaming contract has been assumed.

HTTPS is required except for localhost, loopback and `.local` development addresses. For a device, use a reachable HTTPS server or your development Mac’s `.local` hostname; localhost on the device refers to the device itself. The app allows local networking in ATS and includes a local-network purpose string. OS network permissions and ATS may still require device-specific setup. No production URL or secret is embedded.

## Checks and tests

In Xcode, **⌘U** runs the core tests and hosted view-model tests. Or use an installed simulator:

```sh
xcodebuild -project Visualiser.xcodeproj -scheme Visualiser \
  -destination 'platform=iOS Simulator,name=<installed simulator name>' test
```

The core package can also be tested independently on a Mac with XCTest available:

```sh
swift test --package-path VisualiserCore
```

For an environment with only Swift Command Line Tools:

```sh
swiftc -parse-as-library \
  VisualiserCore/Sources/VisualiserCore/*.swift Scripts/VerifyCore.swift \
  -o /tmp/visualiser-core-checks
/tmp/visualiser-core-checks
```

Implementation-environment results are recorded in `VERIFICATION.md`. Syntax parsing is not an iOS build. Simulator rendering, photo-library behavior, VoiceOver and physical-device playback must still be exercised in Xcode.

## Manual acceptance pass

- Launch fresh → verify Demo badge → run sample → cancel → retry → result.
- Import MOV/MP4 → preview → replace → remove → verify submission disabled.
- Cancel the picker; cancel an in-flight import; try cloud media while offline.
- Generate a demo from an imported video; confirm the result says it is unrelated sample data.
- Pause mid-sentence → change speed → resume → replay → reset → play.
- Copy text; expand signs; enable app Reduce Motion and system Reduce Motion.
- Check large accessibility text sizes, VoiceOver, narrow landscape and iPad.
- Switch to Real API with no URL → verify validation; enter an unreachable URL → test failure.
- With a compatible test server, check a successful response, HTTP error, empty response and cancellation.

Implementation references: Apple’s [PhotosPicker documentation](https://developer.apple.com/documentation/photosui/photospicker), [file-based transfers](https://developer.apple.com/documentation/coretransferable/filerepresentation), and [Reduce Motion environment value](https://developer.apple.com/documentation/swiftui/environmentvalues/accessibilityreducemotion).
