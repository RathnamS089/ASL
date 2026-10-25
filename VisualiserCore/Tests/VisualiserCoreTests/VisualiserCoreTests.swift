import XCTest
@testable import VisualiserCore

final class VisualiserCoreTests: XCTestCase {
    func testMockIsDeterministicAndExplicitlyMarked() async throws {
        let service = MockTranslationService(delay: .zero)
        let first = try await service.translate(.sample)
        let second = try await service.translate(.sample)
        XCTAssertEqual(first, second)
        XCTAssertTrue(first.isMock)
        XCTAssertFalse(first.sentence.isEmpty)
        XCTAssertFalse(first.signs.isEmpty)
    }

    func testMockCancellationDoesNotReturnSuccess() async {
        let task = Task { try await MockTranslationService(delay: .seconds(30)).translate(.sample) }
        task.cancel()
        do {
            _ = try await task.value
            XCTFail("Cancelled work should not produce a translation")
        } catch {
            XCTAssertTrue(error is CancellationError)
        }
    }

    func testMissingVideoFails() async {
        do {
            _ = try await MockTranslationService(delay: .zero)
                .translate(.video(URL(fileURLWithPath: "/missing/\(UUID()).mp4")))
            XCTFail("Expected missing video")
        } catch { XCTAssertEqual(error as? ServiceError, .missingVideo) }
    }

    func testResponseSnakeCaseRoundTrip() throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(TranslationResponse.demo)
        let json = try XCTUnwrap(String(data: data, encoding: .utf8))
        XCTAssertTrue(json.contains("is_mock"))
        XCTAssertTrue(json.contains("start_seconds"))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        XCTAssertEqual(try decoder.decode(TranslationResponse.self, from: data), .demo)
    }

    func testEmptyTranslationAndInvalidTimingsFailValidation() {
        let empty = TranslationResponse(id: "1", sentence: " \n", signs: [], isMock: false)
        XCTAssertThrowsError(try empty.validated()) { XCTAssertEqual($0 as? ServiceError, .emptyTranslation) }
        let badTiming = TranslationResponse(id: "2", sentence: "Hello", signs: [
            .init(label: "HELLO", startSeconds: 2, endSeconds: 1)
        ], isMock: false)
        XCTAssertThrowsError(try badTiming.validated()) { XCTAssertEqual($0 as? ServiceError, .invalidResponse) }
    }

    func testURLValidation() throws {
        for valid in ["https://example.com", "https://example.com/api", "http://localhost:8080", "http://mac.local:8080"] {
            XCTAssertNoThrow(try APIConfiguration(baseURL: valid), valid)
        }
        for invalid in ["", "example.com", "http://example.com", "ftp://example.com", "https://user:secret@example.com", "https://example.com?a=1", "https://example.com/#fragment"] {
            XCTAssertThrowsError(try APIConfiguration(baseURL: invalid), invalid)
        }
    }

    func testPlaybackPauseResumeReplayAndReset() {
        var state = PlaybackState(wordCount: 2)
        state.advance()
        XCTAssertEqual(state.visibleWords, 0)
        state.play()
        state.advance()
        state.pause()
        state.advance()
        XCTAssertEqual(state.visibleWords, 1)
        state.play()
        state.advance()
        XCTAssertTrue(state.isFinished)
        XCTAssertFalse(state.isPlaying)
        state.play()
        XCTAssertEqual(state.visibleWords, 0)
        XCTAssertTrue(state.isPlaying)
        state.reset()
        XCTAssertEqual(state.visibleWords, 0)
        XCTAssertFalse(state.isPlaying)
    }

    func testReducedMotionAndEmptyPlayback() {
        var state = PlaybackState(wordCount: 7)
        state.revealAll()
        XCTAssertEqual(state.visibleWords, 7)
        XCTAssertFalse(state.isPlaying)
        var empty = PlaybackState(wordCount: 0)
        empty.play()
        XCTAssertFalse(empty.isPlaying)
    }

    func testHealthRequestUsesConfiguredBasePath() async throws {
        let client = StubHTTPClient()
        let service = APITranslationService(configuration: try APIConfiguration(baseURL: "https://example.com/api"), client: client)
        try await service.testConnection()
        let recorded = await client.lastRequest()
        let request = try XCTUnwrap(recorded)
        XCTAssertEqual(request.url?.absoluteString, "https://example.com/api/health")
        XCTAssertEqual(request.httpMethod, "GET")
    }

    func testUploadRequestAndResponse() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID()).mov")
        try Data("fixture".utf8).write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        let client = StubHTTPClient()
        let service = APITranslationService(configuration: try APIConfiguration(baseURL: "https://example.com"), client: client)
        let result = try await service.translate(.video(file))
        XCTAssertEqual(result.sentence, "Hello.")
        XCTAssertFalse(result.isMock)
        let recorded = await client.lastRequest()
        let request = try XCTUnwrap(recorded)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.path, "/v1/translations")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "video/quicktime")
        let uploaded = await client.lastUpload()
        XCTAssertEqual(uploaded, file)
    }

    func testServerFailureIsSurfaced() async throws {
        let service = APITranslationService(configuration: try APIConfiguration(baseURL: "https://example.com"),
                                            client: StubHTTPClient(status: 503))
        do {
            try await service.testConnection()
            XCTFail("Expected status error")
        } catch { XCTAssertEqual(error as? ServiceError, .httpStatus(503)) }
    }

    func testMalformedAndEmptyAPIResponsesFail() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID()).mp4")
        try Data().write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        for (payload, expected) in [
            ("not json", ServiceError.invalidResponse),
            (#"{"id":"1","sentence":"","signs":[],"is_mock":false}"#, ServiceError.emptyTranslation)
        ] {
            let service = APITranslationService(configuration: try APIConfiguration(baseURL: "https://example.com"),
                                                client: StubHTTPClient(payload: payload))
            do {
                _ = try await service.translate(.video(file))
                XCTFail("Expected invalid response")
            } catch { XCTAssertEqual(error as? ServiceError, expected) }
        }
    }
}

private actor StubHTTPClient: HTTPClient {
    let status: Int
    let payload: String
    private var request: URLRequest?
    private var uploadedFile: URL?

    init(status: Int = 200, payload: String = #"{"id":"test","sentence":"Hello.","signs":[],"is_mock":false}"#) {
        self.status = status
        self.payload = payload
    }

    func lastRequest() -> URLRequest? { request }
    func lastUpload() -> URL? { uploadedFile }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        self.request = request
        guard let url = request.url,
              let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)
        else { throw ServiceError.invalidResponse }
        return (Data(payload.utf8), response)
    }

    func upload(for request: URLRequest, fromFile file: URL) async throws -> (Data, HTTPURLResponse) {
        uploadedFile = file
        return try await data(for: request)
    }
}
