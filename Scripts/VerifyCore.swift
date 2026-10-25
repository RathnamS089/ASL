// Standalone checks for environments without XCTest. Compile alongside the core sources.
import Foundation

@main
struct VerifyCore {
    static func main() async throws {
        var passed = 0
        func check(_ condition: Bool, _ name: String) throws {
            guard condition else { throw CheckFailure(name: name) }
            passed += 1
            print("PASS: \(name)")
        }

        let mock = MockTranslationService(delay: .zero)
        let first = try await mock.translate(.sample)
        let second = try await mock.translate(.sample)
        try check(first == second && first.isMock && !first.sentence.isEmpty, "deterministic labeled mock")

        let cancelled = Task { try await MockTranslationService(delay: .seconds(30)).translate(.sample) }
        cancelled.cancel()
        do {
            _ = try await cancelled.value
            throw CheckFailure(name: "cancellation returned success")
        } catch is CancellationError {
            try check(true, "mock cancellation")
        }

        do {
            _ = try await mock.translate(.video(URL(fileURLWithPath: "/missing/\(UUID()).mp4")))
            throw CheckFailure(name: "missing video accepted")
        } catch ServiceError.missingVideo {
            try check(true, "missing video validation")
        }

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let decoded = try decoder.decode(TranslationResponse.self, from: encoder.encode(first))
        try check(decoded == first, "snake_case response round trip")

        do {
            _ = try TranslationResponse(id: "empty", sentence: " ", signs: [], isMock: false).validated()
            throw CheckFailure(name: "empty response accepted")
        } catch ServiceError.emptyTranslation {
            try check(true, "empty response validation")
        }

        do {
            _ = try APIConfiguration(baseURL: "http://example.com")
            throw CheckFailure(name: "nonlocal insecure URL accepted")
        } catch ServiceError.invalidURL {
            _ = try APIConfiguration(baseURL: "http://localhost:8080")
            _ = try APIConfiguration(baseURL: "https://example.com/api")
            try check(true, "backend URL validation")
        }

        var playback = PlaybackState(wordCount: 2)
        playback.play()
        playback.advance()
        playback.pause()
        playback.advance()
        try check(playback.visibleWords == 1 && !playback.isPlaying, "pause preserves position")
        playback.play()
        playback.advance()
        try check(playback.isFinished && !playback.isPlaying, "resume reaches completion")
        playback.play()
        try check(playback.visibleWords == 0 && playback.isPlaying, "play after completion replays")
        playback.reset()
        try check(playback.visibleWords == 0 && !playback.isPlaying, "reset")
        playback.revealAll()
        try check(playback.isFinished && !playback.isPlaying, "reduced motion reveals all")
        print("\(passed) standalone core checks passed.")
    }

    struct CheckFailure: Error {
        let name: String
    }
}
