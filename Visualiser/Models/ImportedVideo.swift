import AVFoundation
import CoreTransferable
import UniformTypeIdentifiers
import VisualiserCore

struct ImportedVideo: Identifiable, Sendable {
    let id = UUID()
    let url: URL
    let filename: String
    let duration: Double

    var durationLabel: String {
        let seconds = Int(duration.rounded())
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }

    func removeTemporaryFile() { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }
}

struct TransferredMovie: Transferable, Sendable {
    let url: URL
    let filename: String

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .movie) { received in
            let folder = FileManager.default.temporaryDirectory
                .appendingPathComponent("VisualiserImports", isDirectory: true)
                .appendingPathComponent(UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let destination = folder.appendingPathComponent(received.file.lastPathComponent)
            do {
                try FileManager.default.copyItem(at: received.file, to: destination)
                return TransferredMovie(url: destination, filename: received.file.lastPathComponent)
            } catch {
                try? FileManager.default.removeItem(at: folder)
                throw error
            }
        }
    }

    func validated() async throws -> ImportedVideo {
        do {
            let asset = AVURLAsset(url: url)
            let playable = try await asset.load(.isPlayable)
            let duration = try await asset.load(.duration).seconds
            let tracks = try await asset.loadTracks(withMediaType: .video)
            guard playable, !tracks.isEmpty, duration.isFinite, duration > 0 else {
                throw ServiceError.unsupportedVideo
            }
            try Task.checkCancellation()
            return ImportedVideo(url: url, filename: filename, duration: duration)
        } catch {
            try? FileManager.default.removeItem(at: url.deletingLastPathComponent())
            throw error
        }
    }
}
