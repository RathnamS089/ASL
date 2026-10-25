// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "VisualiserCore",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [.library(name: "VisualiserCore", targets: ["VisualiserCore"])],
    targets: [
        .target(name: "VisualiserCore"),
        .testTarget(name: "VisualiserCoreTests", dependencies: ["VisualiserCore"])
    ]
)
