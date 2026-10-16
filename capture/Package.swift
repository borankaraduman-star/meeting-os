// swift-tools-version: 5.9
import PackageDescription
// CaptureAudio holds the helper's pure buffer logic so it can be tested without ScreenCaptureKit; the executable
// links it statically, so build-capture.sh still copies one binary.
let package = Package(name: "MeetingCapture", platforms: [.macOS("15.0")],
    products: [.executable(name: "MeetingCapture", targets: ["MeetingCapture"])],
    targets: [.target(name: "CaptureAudio"),
              .executableTarget(name: "MeetingCapture", dependencies: ["CaptureAudio"]),
              .testTarget(name: "CaptureAudioTests", dependencies: ["CaptureAudio"])])
