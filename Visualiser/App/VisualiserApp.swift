import SwiftUI

@main
struct VisualiserApp: App {
    @StateObject private var settings = SettingsViewModel()
    @StateObject private var flow = TranslationViewModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(settings)
                .environmentObject(flow)
                .preferredColorScheme(.dark)
                .tint(Studio.lime)
        }
    }
}
