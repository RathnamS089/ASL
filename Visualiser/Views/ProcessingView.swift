import SwiftUI

struct ProcessingView: View {
    @EnvironmentObject private var flow: TranslationViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 32) {
            Eyebrow(text: "02 / In the making")
            ModeBadge(mock: flow.processingIsMock)
            Text(flow.processingIsMock ? "A little room\nfor expression." : "Waiting for\nyour words.")
                .font(.system(.largeTitle, design: .serif, weight: .medium))
                .accessibilityAddTraits(.isHeader)
            HStack(spacing: 16) {
                ProgressView().tint(Studio.lime)
                Text(flow.processingIsMock ? "Preparing a sample translation…" : "Waiting for the backend…")
                    .font(.body)
            }.padding(.vertical, 24).accessibilityElement(children: .combine)
            if flow.processingIsMock {
                VStack(alignment: .leading, spacing: 22) {
                    Eyebrow(text: "Illustrative workflow only")
                    stage("01", "Video input")
                    stage("02", "Sign recognition")
                    stage("03", "Sentence composition")
                    stage("04", "Typography playback")
                }
                Text("These labels describe the planned workflow. No sign recognition is running, and no ML progress is being measured.")
                    .font(.footnote).foregroundStyle(Studio.secondary)
            } else {
                Text("The server has not returned a result yet. No processing percentage is available.")
                    .foregroundStyle(Studio.secondary)
            }
            Button("Cancel") { flow.cancelTranslation() }.buttonStyle(StudioButtonStyle(primary: false))
        }
    }

    private func stage(_ number: String, _ title: String) -> some View {
        HStack(spacing: 20) {
            Text(number).font(.system(.caption, design: .monospaced)).foregroundStyle(Studio.violet)
            Text(title).foregroundStyle(Studio.secondary)
        }.accessibilityElement(children: .combine)
    }
}
