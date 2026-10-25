import SwiftUI
import VisualiserCore

struct SettingsView: View {
    @EnvironmentObject private var settings: SettingsViewModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Translation service", selection: $settings.mode) {
                        Text("Mock / Demo").tag(ServiceMode.mock)
                        Text("Real API").tag(ServiceMode.real)
                    }
                    .pickerStyle(.segmented)
                    .accessibilityLabel("Translation service mode")
                    Text(settings.mode == .mock
                         ? "Demo mode uses deterministic sample text. Videos stay on your device."
                         : "Real mode uploads selected videos to your backend. A compatible server must be running.")
                        .font(.footnote).foregroundStyle(Studio.secondary)
                } header: { Text("Service") }

                Section {
                    TextField("https://your-backend.example", text: $settings.backendURL)
                        .keyboardType(.URL).textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityLabel("Backend URL")
                    if settings.mode == .real {
                        if settings.configuration != nil {
                            Button { settings.testConnection() } label: {
                                HStack {
                                    Text(settings.isTesting ? "Testing connection…" : "Test API connection")
                                    Spacer()
                                    if settings.isTesting { ProgressView() }
                                }
                            }.disabled(settings.isTesting)
                        } else {
                            Text("Enter an HTTPS URL, or an HTTP localhost / .local address for development.")
                                .font(.footnote).foregroundStyle(Studio.secondary)
                        }
                        if let message = settings.connectionMessage {
                            Text(message).font(.footnote).accessibilityLabel(message)
                        }
                    }
                } header: { Text("Future backend") } footer: {
                    Text("Connection testing calls GET /health. No backend is included in this app.")
                }

                Section {
                    Toggle("Reduced motion", isOn: $settings.reducedMotion)
                    if systemReduceMotion {
                        Text("System Reduce Motion is enabled and takes priority.")
                            .font(.footnote).foregroundStyle(Studio.secondary)
                    }
                    VStack(alignment: .leading) {
                        Text("Animation speed · \(settings.speed.formatted(.number.precision(.fractionLength(1))))×")
                        Slider(value: $settings.speed, in: 0.5...2, step: 0.25)
                            .accessibilityLabel("Default animation speed")
                            .accessibilityValue("\(settings.speed.formatted()) times")
                    }
                } header: { Text("Expression") } footer: {
                    Text("Reduced motion reveals the sentence without scale, fade or slide effects.")
                }
                Section {
                    Text("VISUALISER").font(.system(.headline, design: .monospaced)).tracking(3)
                    Text("Frontend prototype · Version 1.0\nSign-language recognition is not included.")
                        .font(.footnote).foregroundStyle(Studio.secondary)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Studio.background)
            .foregroundStyle(Studio.paper)
            .navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .onDisappear { settings.clearConnection() }
        }
    }
}
