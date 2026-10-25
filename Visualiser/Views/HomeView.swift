import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var flow: TranslationViewModel
    @EnvironmentObject private var settings: SettingsViewModel
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    @StateObject private var preview = PlaybackViewModel(sentence: "Hello, world.")
    @ScaledMetric(relativeTo: .largeTitle) private var titleSize = 52
    private var reducedMotion: Bool { systemReduceMotion || settings.reducedMotion }

    var body: some View {
        VStack(alignment: .leading, spacing: 30) {
            ModeBadge(mock: settings.mode == .mock)
            VStack(alignment: .leading, spacing: 16) {
                Text("Turn signs\ninto stories.")
                    .font(.system(size: titleSize, weight: .semibold, design: .serif))
                    .tracking(-1.5).fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                Text("A new way to see what’s being said.")
                    .font(.body).foregroundStyle(Studio.secondary)
            }

            VStack(alignment: .leading, spacing: 30) {
                HStack {
                    Eyebrow(text: "Language in motion")
                    Spacer()
                    Image(systemName: "sparkle").foregroundStyle(Studio.violet).accessibilityHidden(true)
                }
                WordFlowLayout {
                    ForEach(Array(preview.words.enumerated()), id: \.offset) { index, word in
                        Text(word)
                            .font(.system(.largeTitle, design: .serif, weight: .medium).italic())
                            .foregroundStyle(index == 0 ? Studio.paper : Studio.violet)
                            .opacity(index < preview.state.visibleWords ? 1 : 0.12)
                            .offset(y: index < preview.state.visibleWords || reducedMotion ? 0 : 12)
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Typography preview: Hello, world.")
                HStack {
                    Text("Your words. A little more alive.").font(.caption).foregroundStyle(Studio.secondary)
                    Spacer()
                    Button {
                        if preview.state.isPlaying { preview.pause() }
                        else { preview.replay(speed: settings.speed, reducedMotion: reducedMotion) }
                    } label: {
                        Image(systemName: preview.state.isPlaying ? "pause.fill" : "arrow.counterclockwise")
                            .frame(width: 44, height: 44)
                    }.accessibilityLabel(preview.state.isPlaying ? "Pause preview" : "Replay preview")
                }
            }
            .padding(24).background(Studio.surface, in: RoundedRectangle(cornerRadius: 24))

            VStack(spacing: 12) {
                Button { flow.showImport() } label: {
                    HStack { Image(systemName: "arrow.up.doc"); Text("Import a video"); Spacer(); Image(systemName: "arrow.up.right") }
                }.buttonStyle(StudioButtonStyle())
                Button { flow.translate(settings: settings, sample: true) } label: {
                    Label("Try the sample demo", systemImage: "play")
                }.buttonStyle(StudioButtonStyle(primary: false))
            }
            if let error = flow.errorMessage { InlineMessage(text: error) }
            Text(settings.mode == .mock
                 ? "A frontend preview. All translations are sample text; videos stay on this device in demo mode."
                 : "Real mode sends imported videos to your configured backend. The sample demo always stays local.")
                .font(.footnote).foregroundStyle(Studio.secondary).fixedSize(horizontal: false, vertical: true)
            Divider().overlay(Studio.secondary.opacity(0.25))
            HStack {
                Eyebrow(text: "Signs → Words → Expression")
                Spacer(minLength: 0)
            }.accessibilityLabel("Signs become words, words become expression.")
        }
        .onAppear {
            if voiceOver || reducedMotion { preview.showWithoutMotion() }
            else { preview.play(speed: settings.speed, reducedMotion: false) }
        }
        .onDisappear { preview.pause() }
        .onChange(of: reducedMotion) { _, value in if value { preview.showWithoutMotion() } }
        .onChange(of: voiceOver) { _, value in if value { preview.showWithoutMotion() } }
    }
}
