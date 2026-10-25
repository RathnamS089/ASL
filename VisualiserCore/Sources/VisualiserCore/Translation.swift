import Foundation

public struct RecognizedSign: Codable, Equatable, Sendable {
    public let label: String
    public let startSeconds: Double
    public let endSeconds: Double

    public init(label: String, startSeconds: Double, endSeconds: Double) {
        self.label = label
        self.startSeconds = startSeconds
        self.endSeconds = endSeconds
    }
}

public struct TranslationResponse: Codable, Equatable, Sendable {
    public let id: String
    public let sentence: String
    public let signs: [RecognizedSign]
    public let isMock: Bool

    public init(id: String, sentence: String, signs: [RecognizedSign], isMock: Bool) {
        self.id = id
        self.sentence = sentence
        self.signs = signs
        self.isMock = isMock
    }

    public func validated() throws -> Self {
        guard !sentence.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ServiceError.emptyTranslation
        }
        guard signs.allSatisfy({
            !$0.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
            $0.startSeconds.isFinite && $0.endSeconds.isFinite &&
            $0.startSeconds >= 0 && $0.endSeconds >= $0.startSeconds
        }) else { throw ServiceError.invalidResponse }
        return self
    }

    public static let demo = TranslationResponse(
        id: "visualiser-demo-01",
        sentence: "Every voice deserves to be seen.",
        signs: [
            .init(label: "EVERY", startSeconds: 0, endSeconds: 0.8),
            .init(label: "VOICE", startSeconds: 0.8, endSeconds: 1.6),
            .init(label: "DESERVE", startSeconds: 1.6, endSeconds: 2.5),
            .init(label: "SEE", startSeconds: 2.5, endSeconds: 3.5)
        ],
        isMock: true
    )
}

public enum TranslationInput: Sendable {
    case sample
    case video(URL)
}

public enum ServiceMode: String, CaseIterable, Sendable {
    case mock, real
}

public enum ServiceError: LocalizedError, Equatable {
    case invalidURL, missingVideo, unsupportedVideo, invalidResponse, emptyTranslation
    case httpStatus(Int)

    public var errorDescription: String? {
        switch self {
        case .invalidURL: return "Enter a valid HTTPS backend URL. Local development servers may use HTTP."
        case .missingVideo: return "Choose a video before submitting."
        case .unsupportedVideo: return "This file can’t be played as a video. Try an MP4 or MOV file."
        case .invalidResponse: return "The server returned an unexpected response."
        case .emptyTranslation: return "No translated text was returned. Try another video."
        case .httpStatus(let status): return "The server returned HTTP \(status). Check the backend and try again."
        }
    }
}

public protocol TranslationService: Sendable {
    func translate(_ input: TranslationInput) async throws -> TranslationResponse
    func testConnection() async throws
}

public struct MockTranslationService: TranslationService {
    private let delay: Duration

    public init(delay: Duration = .seconds(3)) { self.delay = delay }

    public func translate(_ input: TranslationInput) async throws -> TranslationResponse {
        if case .video(let url) = input, !FileManager.default.fileExists(atPath: url.path) {
            throw ServiceError.missingVideo
        }
        try await Task.sleep(for: delay)
        try Task.checkCancellation()
        return .demo
    }

    public func testConnection() async throws { try Task.checkCancellation() }
}
