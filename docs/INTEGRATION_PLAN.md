# Integration plan

Each milestone ends with a demo and has explicit exit criteria. No owner starts the next milestone's integration until the current one's exit criteria are met. Work inside a workstream can run ahead, against mocks.

## Working rules

- **Small reviewable changes.** One concern per pull request, ideally under about 400 changed lines. Contract changes go in their own PR and need both reviewers (see [TEAM_ASSIGNMENTS.md](TEAM_ASSIGNMENTS.md#review-pairing)).
- **Contracts first.** `contracts/examples/*.json` is the single source of test data across teams. Go tests decode the examples, web tests use them as fetch mocks, Python tests compare their mock output to them, and the iOS check decodes the translation response. `python3 contracts/check_examples.py` must pass on every PR.
- **Mocks stay.** Each layer keeps a mock mode (`MOCK_TRANSLATION`, `ML_MOCK`, the web in-browser mock) after the real implementation lands, for demos and for isolating faults.
- **No invented numbers.** Accuracy, latency and resource figures appear in docs only with the dataset, device, commit and command that produced them.
- **No large downloads in CI or scripts.** Datasets and weights are fetched by hand after the licence review.
- **Version control.** This folder is not yet a git repository (D10). Initialise it and push to a shared remote before M2, so the rules above can be enforced.

## Milestones

| # | Milestone | Lead | Others | Exit criteria (demo) |
| --- | --- | --- | --- | --- |
| 1 | Target sign language and contracts agreed | all | — | D1, D2, D5, D6 and D8 decided. API_CONTRACT.md and ML_CONTRACT.md approved by both sides. The examples check passes. Owners named in TEAM_ASSIGNMENTS.md. |
| 2 | Responsive camera UI with mock results | Web | — | Mac `localhost`: every UI state reachable. Recorder produces a clip of 10 s or less. The result renders the example with kinetic typography, and reduced motion works. Vitest passes. |
| 3 | Web → mock Go over the LAN | Web, Go | — | A phone on the Wi-Fi opens `https://<LAN-IP>:5173`, records and submits, and Go (with `MOCK_TRANSLATION=1`) returns the example. Go's httptest suite covers every 4xx code. Firewall and HTTPS steps verified on one iPhone and one Android phone. |
| 4 | Go → mock Python | Go, Lang/inf | — | `ML_MOCK=1` service on loopback with the token check. Go maps every ML error and timeout correctly, including the no-signs case → `422 no_signs_detected`. End-to-end over the LAN shows `is_mock: true`. |
| 5 | Real sign recognition | Recognition | Lang/inf | The `Recognizer` runs on the M4 Mac over real clips from the phones. The template generator produces sentences. Invariant tests pass. First accuracy number on the held-out split, separated by signer, with method recorded. |
| 6 | Constrained language generation | Lang/inf | Recognition | `Generator` with the validator and template fallback. Benchmarks of the candidates on the M4 Mac (load time, memory, latency, quality on a fixed gloss set). Qwen3.5-2B done. Rejection rate reported. |
| 7 | Auth and history (only if D3 = keep) | Go | Web | Supabase sign-in in the web app. Go verifies JWTs. The history table has row-level security, and tests prove one user cannot read another's rows. The service-role key is absent from the web bundle (checked with grep over `web/dist`). No clips stored. |
| 8 | Physical phone testing | Web | all | Device matrix below completed. Permission and error states as in DEVELOPMENT_SETUP.md. |
| 9 | Quality, latency, resources, failure cases | Lang/inf, Recognition | Go | Report: accuracy and confusion, per-signer results, end-to-end latency percentiles from Go `timings_ms` over at least 50 runs, CPU, GPU and memory on the M4 Mac, runtime and device used, and catalogued failure cases (lighting, framing, left-handed signers, fast signing, out-of-vocabulary signs). Decide whether async jobs are needed. |

Only after M9 is stable: design the live-translation contract (WebSocket or streaming) as a separate document.

## Device matrix (M8)

| Device / OS | Browser | Secure-context method | Permission prompt | Record format | Submit → result | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| iPhone, iOS (current) | Safari | mkcert | | | | |
| iPhone | Chrome (WebKit) | mkcert | | | | |
| Android (one Pixel or Samsung) | Chrome | mkcert | | | | |
| Android | Firefox | mkcert | | | | |
| M4 Mac | Safari / Chrome, `localhost` | localhost | | | | |

## Risk register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Dataset licences forbid our use, or no data exists for the chosen language | blocks M5 | Licence review in M1 and a deliberately small vocabulary |
| Continuous signing is much harder than isolated signs | quality | MVP of one sign or a few clearly separated signs per clip (D8). Say so in the UI. |
| Recognition libraries lack macOS arm64 builds | blocks M5 | Check every dependency early (M1/M2) on the M4 Mac |
| Campus Wi-Fi client isolation | blocks M3/M8 demos | Use a phone hotspot or a travel router |
| iOS CA trust steps are skipped | camera fails silently | The UI detects an insecure context. The step-by-step guide is in DEVELOPMENT_SETUP.md. |
| Mac overloaded by concurrent users, or 16 GB memory exhausted | timeouts | Concurrency 1 with a bounded queue → `503 busy` + `Retry-After` |
| Generator hallucinates content | wrong meaning shown | The constraint validator and template fallback, with `generation.source` exposed in the UI's debug view |
| Video privacy | trust or legal | No clip retention by default, and no third-party tunnels |

## Unresolved decisions

| ID | Decision | Proposed default | Decide by |
| --- | --- | --- | --- |
| D1 | Target sign language and MVP vocabulary size | none: team choice (for example ASL, ISL or BSL) driven by available licensed data and access to fluent signers for testing | M1 |
| D2 | Is translation usable anonymously, or only after sign-in? | Anonymous in M2–M6, behind a rate limit | M1 |
| D3 | Keep accounts and history at all? | Keep as optional M7. Skip if time is short. | M6 |
| D4 | Clip retention | None. Store text results only. | M1 |
| D5 | Existing iOS app: update it to multipart, keep Go's raw-body path, or freeze it | Keep the raw-body compatibility path in Go (small), and give the app an owner | M1 |
| D6 | Clip limits | 0.5–10 s, 20 MiB | M1, revisit at M8 |
| D7 | HTTPS method for phones | mkcert | M3 |
| D8 | One sign per clip, or several signs per clip in the MVP? | Several clearly separated signs, if recognition can segment them; otherwise one | M1, revisit at M5 |
| D9 | Generator: template only, or a small local language model | Qwen3.5-2B via MLX (thinking off) looks justified by the M4 benchmark; confirm after one more candidate | M6 |
| D10 | Version control and hosting for the repository | Done locally (`main`); still needs a private shared remote | before M2 |
| D11 | Move the iOS app into `ios/` | Leave it at the root for now | after M3 |
| D12 | Production hosting | Out of MVP scope | after M9 |
| D13 | Model host | **Decided: Apple M4 Mac, 16 GB** (the Snapdragon laptop is dropped) | done |
