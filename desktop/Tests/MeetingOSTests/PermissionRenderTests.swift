import XCTest
import SwiftUI
import AppKit
@testable import MeetingOS

/// Renders synthetic states through `ImageRenderer`. PNGs are written only when MEETING_OS_RENDER_DIR is set;
/// otherwise each render is only checked to be non-empty. No provider, no real permission is touched.
@MainActor
final class PermissionRenderTests:XCTestCase {
    private func state(_ statuses:[PermissionKind:PermissionStatus],micMode:String="zoom",_ edit:(inout PermissionFlowState)->Void={ _ in })->PermissionFlowState {
        var s=PermissionFlowState(snapshot:PermissionSnapshot(statuses:statuses,micMode:micMode)); s.phase = .active
        edit(&s); s.focus=PermissionFlow.nextFocus(s); return s
    }
    private func render<V:View>(_ name:String,_ view:V) throws {
        let framed=view.frame(width:560).background(Color(nsColor:.windowBackgroundColor)).environment(\.colorScheme,.light)
        let r=ImageRenderer(content:framed); r.scale=2
        let image=try XCTUnwrap(r.nsImage,name)
        XCTAssertGreaterThan(image.size.width,100,name); XCTAssertGreaterThan(image.size.height,100,name)
        let rep=try XCTUnwrap(NSBitmapImageRep(data:try XCTUnwrap(image.tiffRepresentation)),name)
        var colours=Set<UInt32>()
        for x in stride(from:0,to:rep.pixelsWide,by:7) { for y in stride(from:0,to:rep.pixelsHigh,by:7) {
            if let c=rep.colorAt(x:x,y:y)?.usingColorSpace(.sRGB) { colours.insert(UInt32(c.redComponent*31)<<10|UInt32(c.greenComponent*31)<<5|UInt32(c.blueComponent*31)) }
        } }
        XCTAssertGreaterThan(colours.count,3,"\(name) rendered blank")
        guard let dir=ProcessInfo.processInfo.environment["MEETING_OS_RENDER_DIR"],!dir.isEmpty else { return }
        try FileManager.default.createDirectory(atPath:dir,withIntermediateDirectories:true)
        let png=try XCTUnwrap(rep.representation(using:.png,properties:[:]))
        try png.write(to:URL(fileURLWithPath:dir).appendingPathComponent(name+".png"))
    }
    private func onboarding(_ s:PermissionFlowState)->some View { PermissionOnboardingView(state:s,send:{ _ in }) }

    func testAllNotDetermined() throws {
        try render("1-hepsi-sorulmadi",onboarding(state([.microphone:.notDetermined,.systemAudio:.notDetermined,.accessibility:.notDetermined])))
    }
    func testMicrophoneDenied() throws {
        try render("2-mikrofon-kapali",onboarding(state([.microphone:.denied,.systemAudio:.notDetermined,.accessibility:.notDetermined])))
    }
    func testMicrophoneDeniedWaitingInSettings() throws {
        try render("2b-ayarlar-bekleniyor",onboarding(state([.microphone:.denied,.systemAudio:.notDetermined,.accessibility:.notDetermined]) { $0.phase = .waitingForSettings; $0.pending = .microphone; $0.pollsLeft=50 }))
    }
    func testSystemAudioNeedsRelaunch() throws {
        try render("3-sistem-sesi-yeniden-acilis",onboarding(state([.microphone:.authorized,.systemAudio:.needsRelaunch,.accessibility:.notDetermined])))
    }
    func testAccessibilityRestricted() throws {
        try render("4-erisilebilirlik-kisitli",PermissionCardView(content:PermissionPresentation.content(.accessibility,state([.microphone:.authorized,.systemAudio:.authorized,.accessibility:.restricted])),send:{ _ in }).padding())
    }
    func testDone() throws {
        try render("5-tamam",onboarding(state([.microphone:.authorized,.systemAudio:.authorized,.accessibility:.denied]) { $0.skipped=[.accessibility] }))
    }
    func testSettingsSection() throws {
        try render("6-ayarlar-bolumu",PermissionSettingsSection(state:state([.microphone:.authorized,.systemAudio:.needsRelaunch,.accessibility:.restricted]),send:{ _ in }).padding())
    }
}
