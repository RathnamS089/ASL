import SwiftUI
import UIKit
import VisualiserCore

struct ResultView: View {
    let result: TranslationResponse
    @EnvironmentObject private var flow: TranslationViewModel
    @EnvironmentObject private var settings: SettingsViewModel
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var playback: PlaybackViewModel
    @State private var copied = false
    @ScaledMetric(relativeTo: .largeTitle) private var wordSize = 46
    private var reducedMotion: Bool { systemReduceMotion || settings.reducedMotion }

    init(result: TranslationResponse) {
        self.result = result
        _playback = StateObject(wrappedValue: PlaybackViewModel(sentence: result.sentence))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            HStack {
                Eyebrow(text: "03 / In your words")
                Spacer()
                ModeBadge(mock: result.isMock)
            }
            Text("A story, set in motion.").font(.title3).foregroundStyle(Studio.secondary)
                .accessibilityAddTraits(.isHeader)
            WordFlowLayout(spacing: 12) {
                ForEach(Array(playback.words.enumerated()), id: \.offset) { index, word in
                    Text(word)
                        .font(.system(size: wordSize, weight: .medium, design: .serif))
                        .foregroundStyle(index % 3 == 1 ? Studio.violet : Studio.paper)
                        .opacity(index < playback.state.visibleWords ? 1 : 0)
                        .scaleEffect(index < playback.state.visibleWords || reducedMotion ? 1 : 0.88, anchor: .bottomLeading)
                        .offset(y: index < playback.state.visibleWords || reducedMotion ? 0 : 18)
                }
            }
            .frame(minHeight: 210, alignment: .topLeading).padding(.vertical, 24)
            .accessibilityElement(children: .ignore).accessibilityLabel("Translation: \(result.sentence)")

            Text(playback.state.isPlaying ? "Playing" : playback.state.isFinished ? "All words revealed" : playback.state.visibleWords == 0 ? "Ready to play" : "Paused")
                .font(.system(.caption, design: .monospaced)).foregroundStyle(Studio.secondary)

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) { transportControls }
                VStack(spacing: 10) { transportControls }
            }
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Animation speed").font(.subheadline)
                    Spacer()
                    Text(settings.speed.formatted(.number.precision(.fractionLength(1))) + "×")
                        .font(.system(.subheadline, design: .monospaced)).foregroundStyle(Studio.lime)
                }
                Slider(value: $settings.speed, in: 0.5...2, step: 0.25)
                    .accessibilityLabel("Animation speed")
                    .accessibilityValue("\(settings.speed.formatted()) times")
            }
            Toggle("Reduced motion", isOn: $settings.reducedMotion).font(.subheadline)
            if reducedMotion {
                Text(systemReduceMotion ? "System Reduce Motion is on. Playback reveals all words without movement." : "Playback reveals all words without movement.")
                    .font(.footnote).foregroundStyle(Studio.secondary)
            }
            Button {
                UIPasteboard.general.string = result.sentence
                copied = true
                UIAccessibility.post(notification: .announcement, argument: "Translation copied")
            } label: {
                Label(copied ? "Copied to clipboard" : "Copy translated text", systemImage: copied ? "checkmark" : "doc.on.doc")
            }.buttonStyle(StudioButtonStyle(primary: false))
            Divider()
            DisclosureGroup(result.isMock ? "Recognized signs · sample data" : "Recognized signs") {
                VStack(alignment: .leading, spacing: 16) {
                    if result.signs.isEmpty {
                        Text("No individual signs were returned.").foregroundStyle(Studio.secondary)
                    }
                    ForEach(Array(result.signs.enumerated()), id: \.offset) { _, sign in
                        HStack(alignment: .firstTextBaseline) {
                            Text(sign.label).font(.system(.subheadline, design: .monospaced))
                            Spacer()
                            Text("\(sign.startSeconds.formatted(.number.precision(.fractionLength(1))))–\(sign.endSeconds.formatted(.number.precision(.fractionLength(1))))s")
                                .font(.caption).foregroundStyle(Studio.secondary)
                        }.accessibilityElement(children: .combine)
                    }
                }.padding(.top, 16)
            }.font(.subheadline).foregroundStyle(Studio.paper)
            if result.isMock {
                Text("Sample sentence and sign timings. These were not recognized from your video.")
                    .font(.footnote).foregroundStyle(Studio.secondary)
            }
            Button("Back to home") { flow.goHome() }.buttonStyle(StudioButtonStyle(primary: false))
        }
        .onAppear {
            if voiceOver || reducedMotion { playback.showWithoutMotion() }
            else { playback.play(speed: settings.speed, reducedMotion: false) }
        }
        .onDisappear { playback.pause() }
        .onChange(of: reducedMotion) { _, value in if value { playback.showWithoutMotion() } }
        .onChange(of: voiceOver) { _, value in if value { playback.showWithoutMotion() } }
        .onChange(of: settings.speed) { _, _ in
            if playback.state.isPlaying { playback.play(speed: settings.speed, reducedMotion: reducedMotion) }
        }
        .onChange(of: scenePhase) { _, phase in if phase != .active { playback.pause() } }
    }

    @ViewBuilder private var transportControls: some View {
        Button {
            if playback.state.isPlaying { playback.pause() }
            else { playback.play(speed: settings.speed, reducedMotion: reducedMotion) }
        } label: {
            Label(playback.state.isPlaying ? "Pause" : "Play", systemImage: playback.state.isPlaying ? "pause.fill" : "play.fill")
        }.buttonStyle(StudioButtonStyle())
        Button { playback.replay(speed: settings.speed, reducedMotion: reducedMotion) } label: {
            Label("Replay", systemImage: "arrow.counterclockwise")
        }.buttonStyle(StudioButtonStyle(primary: false))
        Button { playback.reset() } label: {
            Label("Reset", systemImage: "stop")
        }.buttonStyle(StudioButtonStyle(primary: false))
    }
}
