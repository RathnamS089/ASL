import SwiftUI

struct RootView: View {
    @EnvironmentObject private var flow: TranslationViewModel
    @EnvironmentObject private var settings: SettingsViewModel
    @State private var showingSettings = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 32) {
                    header
                    switch flow.screen {
                    case .home: HomeView()
                    case .videoImport: VideoImportView()
                    case .processing: ProcessingView()
                    case .result:
                        if let result = flow.result {
                            ResultView(result: result).id(result.id)
                        }
                    }
                }
                .frame(maxWidth: 700)
                .padding(.horizontal, 24).padding(.top, 16).padding(.bottom, 36)
                .frame(maxWidth: .infinity)
            }
            .background(Studio.background.ignoresSafeArea())
            .foregroundStyle(Studio.paper)
            .toolbar(.hidden, for: .navigationBar)
            .sheet(isPresented: $showingSettings) { SettingsView() }
        }
    }

    private var header: some View {
        HStack {
            if flow.screen == .home {
                Text("VISUALISER").font(.system(.headline, design: .monospaced, weight: .bold)).tracking(3)
                    .accessibilityAddTraits(.isHeader)
            } else {
                Button {
                    flow.goHome()
                } label: {
                    Label("Home", systemImage: "arrow.left").font(.subheadline.weight(.medium))
                        .frame(minHeight: 44)
                }.foregroundStyle(Studio.paper)
            }
            Spacer(minLength: 16)
            if flow.screen != .processing {
                Button { showingSettings = true } label: {
                    Image(systemName: "slider.horizontal.3").font(.title3).frame(width: 44, height: 44)
                        .background(Studio.surface, in: Circle())
                }.foregroundStyle(Studio.paper).accessibilityLabel("Settings")
            }
        }
    }
}
