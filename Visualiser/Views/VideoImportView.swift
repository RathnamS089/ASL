import SwiftUI
import PhotosUI
import AVKit

struct VideoImportView: View {
    @EnvironmentObject private var flow: TranslationViewModel
    @EnvironmentObject private var settings: SettingsViewModel
    @State private var selection: PhotosPickerItem?

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Eyebrow(text: "01 / Your source")
            Text("Start with a sign.").font(.system(.largeTitle, design: .serif, weight: .medium))
                .accessibilityAddTraits(.isHeader)
            Text("Choose a video and give its words a place to move.")
                .foregroundStyle(Studio.secondary)
            ModeBadge(mock: settings.mode == .mock)

            if let video = flow.video {
                VideoPreview(url: video.url).id(video.id)
                VStack(alignment: .leading, spacing: 8) {
                    Text(video.filename).font(.headline).lineLimit(3)
                    Label(video.durationLabel, systemImage: "clock")
                        .font(.subheadline).foregroundStyle(Studio.secondary)
                        .accessibilityLabel("Video duration, \(Int(video.duration.rounded())) seconds")
                }
            } else if !flow.isImporting {
                VStack(spacing: 16) {
                    Image(systemName: "video.badge.plus").font(.system(size: 36, weight: .ultraLight))
                        .foregroundStyle(Studio.violet).accessibilityHidden(true)
                    Text("Your story starts here").font(.headline)
                    Text("Select a playable video from Photos.\nMP4 and MOV work best.")
                        .font(.subheadline).foregroundStyle(Studio.secondary).multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 48)
                .background(Studio.surface, in: RoundedRectangle(cornerRadius: 24))
            }

            if flow.isImporting {
                HStack(spacing: 16) {
                    ProgressView().accessibilityLabel("Loading selected video")
                    Text("Opening video…").font(.subheadline)
                    Spacer()
                    Button("Cancel") { flow.cancelImport(); selection = nil }.frame(minHeight: 44)
                }
            }
            PhotosPicker(selection: $selection, matching: .videos, preferredItemEncoding: .compatible) {
                Label(flow.video == nil ? "Choose video" : "Replace video", systemImage: "photo.on.rectangle")
            }
            .buttonStyle(StudioButtonStyle(primary: false))
            .disabled(flow.isImporting)

            if flow.video != nil {
                Button("Remove video", role: .destructive) { flow.removeVideo(); selection = nil }
                    .font(.subheadline).frame(maxWidth: .infinity, minHeight: 44)
            }
            if let error = flow.errorMessage {
                InlineMessage(text: error)
                Button("Try the sample demo") { flow.translate(settings: settings, sample: true) }
                    .frame(minHeight: 44)
            }
            Text("The system picker shares only the video you select. If Photos or a cloud video is unavailable, cancel and try the sample demo from Home.")
                .font(.footnote).foregroundStyle(Studio.secondary)
            Divider()
            Text(settings.mode == .mock
                 ? "Demo mode will return a sample sentence, unrelated to this video. No video is uploaded."
                 : "This video will be uploaded to \(settings.backendURL.isEmpty ? "your backend" : settings.backendURL).")
                .font(.footnote).foregroundStyle(Studio.secondary)
            Button {
                flow.translate(settings: settings)
            } label: {
                Label(settings.mode == .mock ? "Generate demo translation" : "Translate video", systemImage: "arrow.right")
            }
            .buttonStyle(StudioButtonStyle())
            .disabled(flow.video == nil || flow.isImporting)
        }
        .onChange(of: selection) { _, item in flow.loadVideo(item) }
    }
}

private struct VideoPreview: View {
    let url: URL
    @State private var player: AVPlayer?
    var body: some View {
        VideoPlayer(player: player)
            .frame(height: 260)
            .clipShape(RoundedRectangle(cornerRadius: 20))
            .accessibilityLabel("Selected video preview")
            .onAppear { player = AVPlayer(url: url) }
            .onDisappear { player?.pause(); player = nil }
    }
}
