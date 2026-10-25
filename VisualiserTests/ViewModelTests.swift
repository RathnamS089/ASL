import XCTest
@testable import Visualiser
import VisualiserCore

@MainActor
final class ViewModelTests: XCTestCase {
    func testSettingsDefaultToMockAndPersist() throws {
        let name = "VisualiserTests.\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let settings = SettingsViewModel(defaults: defaults)
        XCTAssertEqual(settings.mode, .mock)
        XCTAssertEqual(settings.speed, 1)
        XCTAssertFalse(settings.reducedMotion)
        settings.speed = 1.5
        settings.reducedMotion = true
        let restored = SettingsViewModel(defaults: defaults)
        XCTAssertEqual(restored.speed, 1.5)
        XCTAssertTrue(restored.reducedMotion)
    }

    func testMissingInputRemainsOnImportScreen() throws {
        let name = "VisualiserTests.\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let flow = TranslationViewModel()
        flow.showImport()
        flow.translate(settings: SettingsViewModel(defaults: defaults))
        XCTAssertEqual(flow.screen, .videoImport)
        XCTAssertNotNil(flow.errorMessage)
    }

    func testCancelSampleReturnsHomeWithoutResult() async throws {
        let name = "VisualiserTests.\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let flow = TranslationViewModel()
        flow.translate(settings: SettingsViewModel(defaults: defaults), sample: true)
        XCTAssertEqual(flow.screen, .processing)
        flow.cancelTranslation()
        await Task.yield()
        XCTAssertEqual(flow.screen, .home)
        XCTAssertNil(flow.result)
    }

    func testSampleUsesMockEvenWhenRealModeIsUnconfigured() throws {
        let name = "VisualiserTests.\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let settings = SettingsViewModel(defaults: defaults)
        settings.mode = .real
        let flow = TranslationViewModel()
        flow.translate(settings: settings, sample: true)
        XCTAssertEqual(flow.screen, .processing)
        XCTAssertTrue(flow.processingIsMock)
        flow.cancelTranslation()
    }

    func testReducedMotionPlaybackAndReset() {
        let playback = PlaybackViewModel(sentence: "Hello world")
        playback.play(speed: 1, reducedMotion: true)
        XCTAssertEqual(playback.state.visibleWords, 2)
        XCTAssertFalse(playback.state.isPlaying)
        playback.reset()
        XCTAssertEqual(playback.state.visibleWords, 0)
    }
}
