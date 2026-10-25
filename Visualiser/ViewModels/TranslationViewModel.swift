import SwiftUI
import PhotosUI
import VisualiserCore

@MainActor
final class TranslationViewModel: ObservableObject {
    enum Screen { case home, videoImport, processing, result }
    @Published private(set) var screen: Screen = .home
    @Published private(set) var video: ImportedVideo?
    @Published private(set) var result: TranslationResponse?
    @Published private(set) var isImporting = false
    @Published private(set) var processingIsMock = true
    @Published var errorMessage: String?
    private var importTask: Task<Void, Never>?
    private var translationTask: Task<Void, Never>?
    private var importID = UUID()
    private var requestID = UUID()
    private var processingOrigin: Screen = .home

    func showImport() { errorMessage = nil; screen = .videoImport }

    func loadVideo(_ item: PhotosPickerItem?) {
        guard let item else { return }
        cancelImport()
        let id = UUID()
        importID = id
        isImporting = true
        errorMessage = nil
        importTask = Task {
            do {
                guard let movie = try await item.loadTransferable(type: TransferredMovie.self) else {
                    throw ServiceError.unsupportedVideo
                }
                let imported = try await movie.validated()
                guard !Task.isCancelled, importID == id else {
                    imported.removeTemporaryFile()
                    return
                }
                video?.removeTemporaryFile()
                video = imported
            } catch {
                guard !Task.isCancelled, importID == id else { return }
                errorMessage = "Couldn’t open this video. \(error.localizedDescription) If it’s stored in iCloud, download it in Photos and try again. You can also try the sample demo."
            }
            if importID == id { isImporting = false }
        }
    }

    func cancelImport() {
        importID = UUID()
        importTask?.cancel()
        importTask = nil
        isImporting = false
    }

    func removeVideo() {
        cancelImport()
        video?.removeTemporaryFile()
        video = nil
        errorMessage = nil
    }

    func translate(settings: SettingsViewModel, sample: Bool = false) {
        guard !isImporting else { return }
        errorMessage = nil
        do {
            let input: TranslationInput
            let service: any TranslationService
            if sample {
                input = .sample
                service = MockTranslationService()
            } else {
                guard let video else { throw ServiceError.missingVideo }
                input = .video(video.url)
                service = try settings.service()
            }
            translationTask?.cancel()
            let id = UUID()
            requestID = id
            processingOrigin = screen
            processingIsMock = sample || settings.mode == .mock
            screen = .processing
            translationTask = Task {
                do {
                    let response = try await service.translate(input).validated()
                    guard !Task.isCancelled, requestID == id else { return }
                    result = response
                    screen = .result
                } catch {
                    guard !Task.isCancelled, requestID == id else { return }
                    screen = processingOrigin
                    errorMessage = error.localizedDescription
                }
            }
        } catch { errorMessage = error.localizedDescription }
    }

    func cancelTranslation() {
        requestID = UUID()
        translationTask?.cancel()
        translationTask = nil
        screen = processingOrigin
    }

    func goHome() {
        cancelTranslation()
        removeVideo()
        result = nil
        screen = .home
    }
}
