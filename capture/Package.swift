// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "MeetingCapture", platforms: [.macOS("15.0")], products: [.executable(name: "MeetingCapture", targets: ["MeetingCapture"])], targets: [.executableTarget(name: "MeetingCapture")])
