import SwiftUI

enum Studio {
    static let background = Color(red: 0.047, green: 0.051, blue: 0.047)
    static let surface = Color(red: 0.085, green: 0.09, blue: 0.082)
    static let paper = Color(red: 0.95, green: 0.94, blue: 0.89)
    static let secondary = Color(red: 0.66, green: 0.68, blue: 0.63)
    static let lime = Color(red: 0.80, green: 0.96, blue: 0.39)
    static let violet = Color(red: 0.74, green: 0.67, blue: 0.98)
}

struct StudioButtonStyle: ButtonStyle {
    var primary = true
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.body, design: .rounded, weight: .semibold))
            .frame(maxWidth: .infinity, minHeight: 28)
            .padding(16)
            .foregroundStyle(primary ? Studio.background : Studio.paper)
            .background(primary ? Studio.lime : Studio.surface, in: RoundedRectangle(cornerRadius: 18))
            .opacity(!enabled ? 0.4 : configuration.isPressed ? 0.75 : 1)
    }
}

struct Eyebrow: View {
    let text: String
    var body: some View {
        Text(text.uppercased()).font(.system(.caption, design: .monospaced, weight: .medium))
            .tracking(2).foregroundStyle(Studio.secondary)
    }
}

struct ModeBadge: View {
    var mock: Bool
    var body: some View {
        Label(mock ? "DEMO MODE" : "API MODE", systemImage: mock ? "circle.lefthalf.filled" : "network")
            .font(.system(.caption2, design: .monospaced, weight: .semibold))
            .tracking(1).foregroundStyle(mock ? Studio.lime : Studio.violet)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .overlay(Capsule().strokeBorder((mock ? Studio.lime : Studio.violet).opacity(0.35)))
            .accessibilityLabel(mock ? "Demo mode. Uses sample translations." : "Real API mode.")
    }
}

struct InlineMessage: View {
    let text: String
    var body: some View {
        Label(text, systemImage: "info.circle")
            .font(.subheadline).foregroundStyle(Studio.paper)
            .padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Studio.surface, in: RoundedRectangle(cornerRadius: 12))
            .accessibilityElement(children: .combine)
    }
}

/// Wraps words by their measured Dynamic Type sizes instead of shrinking text.
struct WordFlowLayout: Layout {
    var spacing: CGFloat = 10
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrangement(width: proposal.width ?? 320, subviews: subviews).size
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let layout = arrangement(width: bounds.width, subviews: subviews)
        for (index, position) in layout.positions.enumerated() {
            subviews[index].place(
                at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: bounds.width, height: nil)
            )
        }
    }
    private func arrangement(width: CGFloat, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(ProposedViewSize(width: width, height: nil))
            if x > 0, x + size.width > width { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            positions.append(CGPoint(x: x, y: y))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return (CGSize(width: width, height: y + rowHeight), positions)
    }
}
