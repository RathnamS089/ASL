import Foundation

/// Independent of the display clock, so playback transitions can be tested.
public struct PlaybackState: Equatable, Sendable {
    public private(set) var visibleWords = 0
    public private(set) var isPlaying = false
    public let wordCount: Int

    public init(wordCount: Int) { self.wordCount = max(0, wordCount) }
    public var isFinished: Bool { visibleWords == wordCount }
    public mutating func play() {
        if isFinished { visibleWords = 0 }
        isPlaying = wordCount > 0
    }
    public mutating func pause() { isPlaying = false }
    public mutating func reset() { visibleWords = 0; isPlaying = false }
    public mutating func revealAll() { visibleWords = wordCount; isPlaying = false }
    public mutating func advance() {
        guard isPlaying else { return }
        visibleWords = min(visibleWords + 1, wordCount)
        if isFinished { isPlaying = false }
    }
}
