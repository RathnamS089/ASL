import Foundation

public protocol HTTPClient: Sendable {
    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse)
    func upload(for request: URLRequest, fromFile file: URL) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionHTTPClient: HTTPClient {
    private let session: URLSession

    public init(session: URLSession = .shared) { self.session = session }

    public func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
        return (data, http)
    }

    public func upload(for request: URLRequest, fromFile file: URL) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.upload(for: request, fromFile: file)
        guard let http = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
        return (data, http)
    }
}

public struct APIConfiguration: Sendable {
    public let baseURL: URL

    public init(baseURL text: String) throws {
        guard let components = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = components.scheme?.lowercased(),
              let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil,
              let url = components.url,
              scheme == "https" || (scheme == "http" &&
                  (host == "localhost" || host == "127.0.0.1" || host == "[::1]" || host.hasSuffix(".local")))
        else { throw ServiceError.invalidURL }
        baseURL = url
    }
}

/// Provisional contract, to be agreed with the future Go service.
public struct APITranslationService: TranslationService {
    private let configuration: APIConfiguration
    private let client: any HTTPClient

    public init(configuration: APIConfiguration, client: any HTTPClient = URLSessionHTTPClient()) {
        self.configuration = configuration
        self.client = client
    }

    public func translate(_ input: TranslationInput) async throws -> TranslationResponse {
        guard case .video(let file) = input,
              FileManager.default.fileExists(atPath: file.path) else { throw ServiceError.missingVideo }
        var request = URLRequest(url: configuration.baseURL.appendingPathComponent("v1/translations"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        let mimeTypes = ["mov": "video/quicktime", "mp4": "video/mp4", "m4v": "video/x-m4v"]
        request.setValue(mimeTypes[file.pathExtension.lowercased()] ?? "application/octet-stream",
                         forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await client.upload(for: request, fromFile: file)
        try check(response)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do { return try decoder.decode(TranslationResponse.self, from: data).validated() }
        catch let error as ServiceError { throw error }
        catch { throw ServiceError.invalidResponse }
    }

    public func testConnection() async throws {
        var request = URLRequest(url: configuration.baseURL.appendingPathComponent("health"))
        request.timeoutInterval = 10
        let (_, response) = try await client.data(for: request)
        try check(response)
    }

    private func check(_ response: HTTPURLResponse) throws {
        guard (200..<300).contains(response.statusCode) else {
            throw ServiceError.httpStatus(response.statusCode)
        }
    }
}
