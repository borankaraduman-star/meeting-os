// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "MeetingOS", platforms: [.macOS("15.0")], products: [.executable(name:"MeetingOS",targets:["MeetingOS"])], targets:[.executableTarget(name:"MeetingOS")])
