import SwiftUI
import VisualiserCore

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var backendURL: String { didSet { defaults.set(backendURL, forKey: "backendURL"); clearConnection() } }
    @Published var mode: ServiceMode { didSet { defaults.set(mode.rawValue, forKey: "serviceMode"); clearConnection() } }
    @Published var reducedMotion: Bool { didSet { defaults.set(reducedMotion, forKey: "reducedMotion") } }
    @Published var speed: Double { didSet { defaults.set(speed, forKey: "speed") } }
    @Published private(set) var connectionMessage: String?
    @Published private(set) var isTesting = false
    private let defaults: UserDefaults
    private var connectionTask: Task<Void, Never>?

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        backendURL = defaults.string(forKey: "backendURL") ?? ""
        mode = ServiceMode(rawValue: defaults.string(forKey: "serviceMode") ?? "") ?? .mock
        reducedMotion = defaults.bool(forKey: "reducedMotion")
        let storedSpeed = defaults.double(forKey: "speed")
        speed = storedSpeed == 0 ? 1 : min(2, max(0.5, storedSpeed))
    }

    var configuration: APIConfiguration? { try? APIConfiguration(baseURL: backendURL) }

    func service() throws -> any TranslationService {
        if mode == .mock { return MockTranslationService() }
        return APITranslationService(configuration: try APIConfiguration(baseURL: backendURL))
    }

    func testConnection() {
        guard mode == .real, let configuration, !isTesting else { return }
        isTesting = true
        connectionMessage = nil
        connectionTask = Task {
            do {
                try await APITranslationService(configuration: configuration).testConnection()
                try Task.checkCancellation()
                connectionMessage = "Connected. The health endpoint responded successfully."
            } catch {
                guard !Task.isCancelled else { return }
                connectionMessage = "Connection failed. \(error.localizedDescription)"
            }
            isTesting = false
        }
    }

    func clearConnection() {
        connectionTask?.cancel()
        connectionTask = nil
        connectionMessage = nil
        isTesting = false
    }
}
