import XCTest
import AVFoundation
@testable import MeetingOS

/// No AVCaptureDevice read, no CGPreflight, no AX call, no real URL opened: the live provider is built with an
/// injected OS and opener, and only its pure mappings and fallback chain are exercised.
final class PermissionServiceTests: XCTestCase {
    private func os(_ major:Int,_ minor:Int=0)->OperatingSystemVersion { OperatingSystemVersion(majorVersion:major,minorVersion:minor,patchVersion:0) }
    private let modern="x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?"
    private let legacy="x-apple.systempreferences:com.apple.preference.security?"

    func testMicrophoneStatusMapping() {
        XCTAssertEqual(LivePermissionProvider.microphoneStatus(.authorized),.authorized)
        XCTAssertEqual(LivePermissionProvider.microphoneStatus(.denied),.denied)
        XCTAssertEqual(LivePermissionProvider.microphoneStatus(.notDetermined),.notDetermined)
        XCTAssertEqual(LivePermissionProvider.microphoneStatus(.restricted),.restricted)
    }

    func testSettingsURLPerMacOS() {
        for kind in PermissionKind.allCases {
            let urls15=PermissionSettingsLink.candidates(kind,os:os(15)).map(\.absoluteString)
            XCTAssertEqual(urls15,[modern+kind.paneAnchor,legacy+kind.paneAnchor],"macOS 15")
            XCTAssertEqual(PermissionSettingsLink.candidates(kind,os:os(14,6)).map(\.absoluteString),urls15,"macOS 14")
        }
        XCTAssertEqual(PermissionSettingsLink.candidates(.microphone,os:os(13)).first?.absoluteString,modern+"Privacy_Microphone","macOS 13")
        XCTAssertEqual(PermissionSettingsLink.candidates(.microphone,os:os(12,7)).map(\.absoluteString),[legacy+"Privacy_Microphone"],"macOS 12: legacy only")
        XCTAssertTrue(PermissionSettingsLink.candidates(.systemAudio,os:os(12,7)).isEmpty,"no system audio before 13")
        let live13=LivePermissionProvider(osVersion:os(13),open:{ _ in true })
        XCTAssertEqual(live13.settingsURL(.accessibility)?.absoluteString,modern+"Privacy_Accessibility")
        XCTAssertNil(LivePermissionProvider(osVersion:os(12),open:{ _ in true }).settingsURL(.systemAudio))
    }

    func testOldOSReportsUnsupportedWithoutAnySystemRead() {
        let live=LivePermissionProvider(osVersion:os(12),open:{ _ in true })
        XCTAssertEqual(live.status(.systemAudio),.unsupported,"guarded before the CG call")
    }

    func testOpenFallsBackToGeneralPrivacyPane() {
        var tried:[String]=[]
        let live=LivePermissionProvider(osVersion:os(15),open:{ url in tried.append(url.absoluteString); return url.absoluteString == PermissionSettingsLink.privacyPane13 })
        XCTAssertTrue(live.openSettings(.microphone))
        XCTAssertEqual(tried,[modern+"Privacy_Microphone",legacy+"Privacy_Microphone",PermissionSettingsLink.privacyPane13])
    }

    func testLegacyPaneOpensWhenModernFails() {
        var tried:[String]=[]
        let live=LivePermissionProvider(osVersion:os(14),open:{ url in tried.append(url.absoluteString); return url.absoluteString.hasPrefix(self.legacy) })
        XCTAssertTrue(live.openSettings(.accessibility))
        XCTAssertEqual(tried.count,2)
    }

    func testOpenReturnsFalseWhenNothingOpens() {
        var count=0
        let live=LivePermissionProvider(osVersion:os(15),open:{ _ in count+=1; return false })
        XCTAssertFalse(live.openSettings(.systemAudio))
        XCTAssertEqual(count,3,"pane, legacy pane, general pane — then give up")
    }

    func testOlderOSFallbackIsLegacyPrivacyPane() {
        var tried:[String]=[]
        let live=LivePermissionProvider(osVersion:os(13),open:{ tried.append($0.absoluteString); return false })
        _=live.openSettings(.microphone)
        XCTAssertEqual(tried.last,PermissionSettingsLink.privacyPane13)
        tried=[]
        _=LivePermissionProvider(osVersion:os(12),open:{ tried.append($0.absoluteString); return false }).openSettings(.microphone)
        XCTAssertEqual(tried.last,PermissionSettingsLink.privacyPaneLegacy)
    }

    // MARK: needsRelaunch evidence

    func testScreenMemoryNeedsFullStoryForRelaunch() {
        var m=ScreenGrantMemory()
        XCTAssertEqual(m.resolve(preflight:false),.denied,"a bare false is a no")
        m.noteRequest()
        XCTAssertEqual(m.resolve(preflight:false),.denied)
        m.noteBecameActive()
        XCTAssertEqual(m.resolve(preflight:false),.denied,"becoming active without a Settings visit proves nothing")
        m.noteSettingsOpened()
        XCTAssertEqual(m.resolve(preflight:false),.denied,"still in Settings")
        m.noteBecameActive()
        XCTAssertEqual(m.resolve(preflight:false),.denied,"the visit story alone is not proof of a grant")
        XCTAssertEqual(m.resolve(preflight:false,grantEvidence:true),.needsRelaunch,"visit story plus independent proof")
        XCTAssertEqual(m.resolve(preflight:true),.authorized)
        m.noteSettingsOpened()
        XCTAssertEqual(m.resolve(preflight:false),.denied,"a new visit resets the return")
    }

    func testScreenMemoryWithoutRequestIsDenied() {
        var m=ScreenGrantMemory()
        m.noteSettingsOpened(); m.noteBecameActive()
        XCTAssertEqual(m.resolve(preflight:false,grantEvidence:true),.denied,"never asked: nothing to be stale")
    }

    // MARK: Fake provider

    func testFakeRecordsCallsAndProgramsOutcomes() {
        let fake=FakePermissionProvider(os:os(15),[.microphone:.notDetermined,.systemAudio:.denied])
        fake.requestOutcome[.microphone] = .authorized
        var answer:PermissionStatus?
        fake.request(.microphone) { answer=$0 }
        XCTAssertEqual(answer,.authorized); XCTAssertEqual(fake.requested,[.microphone])
        XCTAssertEqual(fake.status(.accessibility),.unknown,"unscripted = unknown, not granted")
        XCTAssertTrue(fake.openSettings(.systemAudio))
        XCTAssertEqual(fake.openedURLs.first?.absoluteString,modern+"Privacy_ScreenCapture")
        fake.openableURLs=[]
        XCTAssertFalse(fake.openSettings(.microphone)); XCTAssertEqual(fake.openedKinds,[.systemAudio,.microphone])
        XCTAssertEqual(fake.attemptedURLs.count,1+3)
    }

    func testSnapshotFromFakeMarksOldOSUnsupported() {
        let fake=FakePermissionProvider(os:os(12),[.microphone:.authorized,.systemAudio:.authorized,.accessibility:.denied])
        let snap=fake.snapshot(micMode:"zoom")
        XCTAssertEqual(snap.status(.systemAudio),.unsupported)
        XCTAssertEqual(snap.status(.microphone),.authorized)
    }
}
