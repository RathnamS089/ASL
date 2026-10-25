import SwiftUI
import VisualiserCore

@MainActor
final class PlaybackViewModel: ObservableObject {
    @Published private(set) var state: PlaybackState
    let words: [String]
    private var ticker: Task<Void, Never>?

    init(sentence: String) {
        words = sentence.split(whereSeparator: \.isWhitespace).map(String.init)
        state = PlaybackState(wordCount: words.count)
    }

    func play(speed: Double, reducedMotion: Bool) {
        ticker?.cancel()
        if reducedMotion { state.revealAll(); return }
        state.play()
        ticker = Task {
            while !Task.isCancelled, state.isPlaying {
                withAnimation(.spring(response: 0.55 / speed, dampingFraction: 0.82)) {
                    state.advance()
                }
                do { try await Task.sleep(for: .seconds(0.55 / speed)) }
                catch { return }
            }
        }
    }

    func pause() { ticker?.cancel(); ticker = nil; state.pause() }
    func reset() { pause(); state.reset() }
    func replay(speed: Double, reducedMotion: Bool) { reset(); play(speed: speed, reducedMotion: reducedMotion) }
    func showWithoutMotion() { pause(); state.revealAll() }
}
