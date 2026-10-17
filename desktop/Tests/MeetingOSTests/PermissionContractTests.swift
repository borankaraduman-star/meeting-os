import XCTest
@testable import MeetingOS

/// Synthetic transitions and a fake provider only: no TCC read, no prompt, no System Settings, no UserDefaults.
/// Every macOS branch is an injected `OperatingSystemVersion`.
final class PermissionContractTests: XCTestCase {
    private let mac15=OperatingSystemVersion(majorVersion:15,minorVersion:0,patchVersion:0)
    private let mac14=OperatingSystemVersion(majorVersion:14,minorVersion:6,patchVersion:0)
    private let mac12=OperatingSystemVersion(majorVersion:12,minorVersion:7,patchVersion:0)

    private func snap(_ mic:PermissionStatus,_ screen:PermissionStatus,_ ax:PermissionStatus,mode:String="zoom")->PermissionSnapshot {
        PermissionSnapshot(statuses:[.microphone:mic,.systemAudio:screen,.accessibility:ax],micMode:mode,os:mac15)
    }
    private func start(_ snapshot:PermissionSnapshot)->PermissionFlowState {
        var s=PermissionFlow.reduce(PermissionFlowState(),.appear)
        XCTAssertEqual(s.effects,[.refresh])
        s=PermissionFlow.reduce(s,.refreshed(snapshot))
        return s
    }

    /// The microphone: macOS asks in-app, the answer comes back through the completion, the flow moves on.
    func testNotDeterminedRequestAuthorized() {
        var s=start(snap(.notDetermined,.notDetermined,.denied))
        XCTAssertEqual(s.phase,.active); XCTAssertEqual(s.focus,.microphone)
        XCTAssertEqual(PermissionFlow.primaryAction(.microphone,in:s),.request)
        s=PermissionFlow.reduce(s,.primaryTapped(.microphone))
        XCTAssertEqual(s.phase,.requesting); XCTAssertEqual(s.effects,[.request(.microphone)])
        XCTAssertEqual(PermissionFlow.primaryAction(.microphone,in:s),.none,"one macOS question at a time")
        XCTAssertTrue(PermissionCardModel.make(.microphone,state:s).isBusy)
        // A second tap while macOS is asking does nothing.
        XCTAssertEqual(PermissionFlow.reduce(s,.primaryTapped(.systemAudio)).effects,[])
        s=PermissionFlow.reduce(s,.requestFinished(.microphone,.authorized))
        XCTAssertEqual(s.phase,.active); XCTAssertNil(s.pending)
        XCTAssertEqual(s.snapshot.status(.microphone),.authorized)
        XCTAssertEqual(s.focus,.systemAudio)
        XCTAssertEqual(s.effects,[.refresh])
        let card=PermissionCardModel.make(.microphone,state:s)
        XCTAssertEqual(card.statusLabel,"İzin verildi"); XCTAssertEqual(card.tone,.success); XCTAssertEqual(card.primary,.none)
    }

    /// A refused microphone can only be changed in System Settings: open it, poll, come back, see it on.
    func testDeniedOpenSettingsReturnedAuthorized() {
        var s=start(snap(.denied,.authorized,.authorized))
        XCTAssertEqual(PermissionFlow.primaryAction(.microphone,in:s),.openSettings)
        XCTAssertEqual(PermissionCardModel.make(.microphone,state:s).tone,.error)
        s=PermissionFlow.reduce(s,.primaryTapped(.microphone))
        XCTAssertEqual(s.phase,.waitingForSettings); XCTAssertEqual(s.effects,[.openSettings(.microphone)])
        XCTAssertTrue(s.isPolling); XCTAssertEqual(s.pollsLeft,PermissionPolicy.pollLimit)
        XCTAssertEqual(PermissionFlow.primaryAction(.microphone,in:s),.recheck)
        XCTAssertEqual(PermissionFlow.secondaryAction(.microphone,in:s),.openSettings)
        s=PermissionFlow.reduce(s,.pollTick)
        XCTAssertEqual(s.effects,[.refresh]); XCTAssertEqual(s.pollsLeft,PermissionPolicy.pollLimit-1)
        s=PermissionFlow.reduce(s,.refreshed(snap(.denied,.authorized,.authorized)))
        XCTAssertEqual(s.phase,.waitingForSettings,"still polling: the user is still in System Settings")
        s=PermissionFlow.reduce(s,.returnedFromSettings)
        XCTAssertEqual(s.effects,[.refresh]); XCTAssertTrue(s.returnedFromSettings)
        s=PermissionFlow.reduce(s,.refreshed(snap(.authorized,.authorized,.authorized)))
        XCTAssertEqual(s.phase,.active); XCTAssertNil(s.pending); XCTAssertFalse(s.isPolling)
        XCTAssertNil(s.focus); XCTAssertTrue(s.allRequiredGranted)
        XCTAssertEqual(PermissionFlow.reduce(s,.pollTick).effects,[],"no timer survives a granted switch")
    }

    /// Screen/AX prompts return at once and point at System Settings: the flow waits there, and after coming back
    /// with the screen grant still off it offers a relaunch — without ever painting the badge green.
    func testSystemAudioRequestWaitsAndSuggestsRelaunch() {
        var s=start(snap(.authorized,.notDetermined,.authorized))
        s=PermissionFlow.reduce(s,.primaryTapped(.systemAudio))
        XCTAssertEqual(s.effects,[.request(.systemAudio)])
        s=PermissionFlow.reduce(s,.requestFinished(.systemAudio,.denied))
        XCTAssertEqual(s.phase,.waitingForSettings); XCTAssertEqual(s.pending,.systemAudio)
        s=PermissionFlow.reduce(s,.returnedFromSettings)
        s=PermissionFlow.reduce(s,.refreshed(snap(.authorized,.denied,.authorized)))
        XCTAssertTrue(s.relaunchSuggested.contains(.systemAudio))
        XCTAssertEqual(PermissionFlow.secondaryAction(.systemAudio,in:s),.relaunch)
        let card=PermissionCardModel.make(.systemAudio,state:s)
        XCTAssertNotEqual(card.tone,.success); XCTAssertFalse(card.statusLabel.contains("verildi"))
        XCTAssertTrue(card.footnote.contains("Ekran ve Sistem Sesi Kaydı"))
        XCTAssertEqual(PermissionFlow.reduce(s,.actionTapped(.relaunch,.systemAudio)).effects,[.relaunch])
        // Granted after all: the hint goes with it.
        s=PermissionFlow.reduce(s,.refreshed(snap(.authorized,.authorized,.authorized)))
        XCTAssertTrue(s.relaunchSuggested.isEmpty); XCTAssertEqual(s.phase,.active)
    }

    func testPollLimitEndsWaitingWithNotice() {
        var s=start(snap(.authorized,.authorized,.denied))
        s=PermissionFlow.reduce(s,.actionTapped(.openSettings,.accessibility))
        for _ in 0..<PermissionPolicy.pollLimit {
            s=PermissionFlow.reduce(s,.pollTick)
            s=PermissionFlow.reduce(s,.refreshed(snap(.authorized,.authorized,.denied)))
        }
        XCTAssertEqual(s.phase,.active); XCTAssertFalse(s.isPolling)
        XCTAssertEqual(s.notice,.noChangeSeen(.accessibility))
        XCTAssertEqual(PermissionFlow.reduce(s,.pollTick).effects,[])
        XCTAssertTrue(PermissionCardModel.make(.accessibility,state:s).footnote.contains("Değişiklik görülmedi"))
    }

    func testMicrophoneRefusedInPromptPointsToSettings() {
        var s=start(snap(.notDetermined,.authorized,.authorized))
        s=PermissionFlow.reduce(s,.primaryTapped(.microphone))
        s=PermissionFlow.reduce(s,.requestFinished(.microphone,.denied))
        XCTAssertEqual(s.phase,.active); XCTAssertEqual(s.focus,.microphone)
        XCTAssertEqual(s.notice,.requestDenied(.microphone))
        XCTAssertEqual(PermissionFlow.primaryAction(.microphone,in:s),.openSettings)
    }

    /// Accessibility outside "Zoom’u izle" is optional and says so; skipping it never makes it look granted.
    func testSkipOptionalAccessibility() {
        var s=start(snap(.authorized,.authorized,.denied,mode:"manual"))
        XCTAssertEqual(s.snapshot.need(.accessibility),.optional)
        XCTAssertEqual(s.focus,.accessibility)
        XCTAssertEqual(PermissionFlow.secondaryAction(.accessibility,in:s),.skip)
        s=PermissionFlow.reduce(s,.skip(.accessibility))
        XCTAssertNil(s.focus); XCTAssertTrue(s.skipped.contains(.accessibility))
        let card=PermissionCardModel.make(.accessibility,state:s)
        XCTAssertEqual(card.statusLabel,"Kapalı · geçildi"); XCTAssertNotEqual(card.tone,.success)
        XCTAssertEqual(card.needLabel,"İsteğe bağlı")
        XCTAssertTrue(card.reason.contains("isteğe bağlıdır"))
        XCTAssertEqual(card.primary,.openSettings,"a real button, still there after skipping")
    }

    func testSkipWhileWaitingStopsPolling() {
        var s=start(snap(.authorized,.authorized,.denied))
        s=PermissionFlow.reduce(s,.primaryTapped(.accessibility))
        XCTAssertTrue(s.isPolling)
        s=PermissionFlow.reduce(s,.actionTapped(.skip,.accessibility))
        XCTAssertFalse(s.isPolling); XCTAssertEqual(s.phase,.active); XCTAssertNil(s.focus)
    }

    func testFinishAndReopen() {
        var s=start(snap(.authorized,.denied,.denied))
        s=PermissionFlow.reduce(s,.skip(.accessibility))
        s=PermissionFlow.reduce(s,.primaryTapped(.systemAudio))
        s=PermissionFlow.reduce(s,.finish)
        XCTAssertEqual(s.phase,.finished); XCTAssertTrue(s.completed); XCTAssertFalse(s.isPolling)
        XCTAssertEqual(s.effects,[.persistCompletion])
        XCTAssertFalse(s.allRequiredGranted,"finishing never pretends a missing grant exists")
        XCTAssertEqual(s.snapshot.missingRequired,[.systemAudio])
        XCTAssertEqual(PermissionFlow.reduce(s,.pollTick).effects,[])
        s=PermissionFlow.reduce(s,.reopen)
        XCTAssertEqual(s.phase,.active); XCTAssertFalse(s.completed)
        XCTAssertTrue(s.skipped.isEmpty); XCTAssertEqual(s.effects,[.refresh])
        XCTAssertEqual(s.focus,.systemAudio)
    }

    func testSettingsOpenFailureNamesThePath() {
        var s=start(snap(.denied,.authorized,.authorized))
        s=PermissionFlow.reduce(s,.primaryTapped(.microphone))
        s=PermissionFlow.reduce(s,.settingsOpenFailed(.microphone))
        XCTAssertEqual(s.phase,.active); XCTAssertFalse(s.isPolling)
        let card=PermissionCardModel.make(.microphone,state:s)
        XCTAssertTrue(card.footnote.contains("Sistem Ayarları açılamadı"))
        XCTAssertTrue(card.footnote.contains("Gizlilik ve Güvenlik → Mikrofon"))
    }

    func testRestrictedAndRelaunchStatuses() {
        let s=start(snap(.restricted,.needsRelaunch,.authorized))
        XCTAssertEqual(PermissionFlow.primaryAction(.microphone,in:s),.none)
        XCTAssertEqual(s.focus,.systemAudio,"an MDM lock never holds the focus")
        XCTAssertEqual(PermissionFlow.primaryAction(.systemAudio,in:s),.relaunch)
        XCTAssertEqual(PermissionFlow.reduce(s,.primaryTapped(.systemAudio)).effects,[.relaunch])
        XCTAssertEqual(PermissionCardModel.make(.microphone,state:s).tone,.error)
    }

    func testStaleRequestAnswerOnlyRecordsStatus() {
        var s=start(snap(.notDetermined,.denied,.denied))
        s=PermissionFlow.reduce(s,.requestFinished(.microphone,.authorized))
        XCTAssertEqual(s.phase,.active); XCTAssertEqual(s.snapshot.status(.microphone),.authorized)
    }

    func testNeedsFollowMicMode() {
        XCTAssertEqual(PermissionPolicy.need(.microphone,micMode:"manual"),.required)
        XCTAssertEqual(PermissionPolicy.need(.systemAudio,micMode:"always"),.required)
        XCTAssertEqual(PermissionPolicy.need(.accessibility,micMode:"zoom"),.conditional)
        XCTAssertEqual(PermissionPolicy.need(.accessibility,micMode:"always"),.optional)
        XCTAssertEqual(PermissionPolicy.need(.accessibility,micMode:"bogus"),.conditional,"unknown mode normalises to zoom")
        XCTAssertTrue(PermissionCardModel.reason(.accessibility,need:.conditional).contains("kaybolmaz"))
    }

    func testSettingsLinksPerMacOS() {
        XCTAssertEqual(PermissionSettingsLink.url(.systemAudio,os:mac15)?.absoluteString,
                       "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        XCTAssertEqual(PermissionSettingsLink.paneName(.systemAudio,os:mac15),"Ekran ve Sistem Sesi Kaydı")
        XCTAssertEqual(PermissionSettingsLink.paneName(.systemAudio,os:mac14),"Ekran Kaydı")
        XCTAssertEqual(PermissionSettingsLink.path(.accessibility,os:mac14),"Sistem Ayarları → Gizlilik ve Güvenlik → Erişilebilirlik")
        XCTAssertTrue(PermissionSettingsLink.path(.microphone,os:mac12).hasPrefix("Sistem Tercihleri"))
        XCTAssertEqual(PermissionSettingsLink.fallbackURL(os:mac15)?.absoluteString,PermissionSettingsLink.privacyPane13)
        XCTAssertEqual(PermissionSettingsLink.fallbackURL(os:mac12)?.absoluteString,PermissionSettingsLink.privacyPaneLegacy)
        XCTAssertNil(PermissionSettingsLink.url(.systemAudio,os:mac12),"no ScreenCaptureKit audio before macOS 13")
        XCTAssertTrue(PermissionFlow.supported(.systemAudio,os:mac14))
    }

    func testShouldPresent() {
        let missing=snap(.notDetermined,.denied,.denied), ready=snap(.authorized,.authorized,.denied)
        XCTAssertTrue(PermissionPolicy.shouldPresent(storedVersion:0,snapshot:missing))
        XCTAssertFalse(PermissionPolicy.shouldPresent(storedVersion:PermissionPolicy.onboardingVersion,snapshot:missing))
        XCTAssertFalse(PermissionPolicy.shouldPresent(storedVersion:0,snapshot:ready),"a Mac already recording gets no tour")
        XCTAssertEqual(PermissionPolicy.completedVersionKey,"permissionOnboardingCompletedVersion")
        XCTAssertGreaterThan(PermissionPolicy.pollInterval,0); XCTAssertGreaterThan(PermissionPolicy.pollLimit,0)
    }

    /// The whole loop against a fake provider, the way the native driver will run it: every effect executed,
    /// every answer fed back. The fake flips the screen grant on its third poll, as a user in System Settings would.
    func testDriverLoopWithFakeProvider() {
        // The same scripted fake as the service tests (FakePermissionProvider): one definition, not two. Mic is granted
        // by its request; the screen grant flips on the fourth read after Settings was opened.
        let fake=FakePermissionProvider(os:mac15,[.microphone:.notDetermined,.systemAudio:.denied,.accessibility:.denied])
        fake.requestOutcome[.microphone] = .authorized
        var screenReads=0
        fake.onStatusRead = { [unowned fake] kind,_ in
            guard kind == .systemAudio else { return }
            screenReads+=1
            if screenReads>=4 && !fake.openedKinds.isEmpty { fake.statuses[.systemAudio] = .authorized }
        }
        XCTAssertEqual(PermissionSettingsLink.url(.accessibility,os:mac15)?.absoluteString,"x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        var s=PermissionFlowState()
        func send(_ e:PermissionFlowEvent) {
            s=PermissionFlow.reduce(s,e)
            for effect in s.effects {
                switch effect {
                case .refresh: send(.refreshed(fake.snapshot(micMode:"zoom")))
                case .request(let k): fake.request(k) { send(.requestFinished(k,$0)) }
                case .openSettings(let k): if !fake.openSettings(k) { send(.settingsOpenFailed(k)) }
                case .relaunch, .persistCompletion: break
                }
            }
        }
        send(.appear)
        XCTAssertEqual(s.focus,.microphone)
        send(.primaryTapped(.microphone))
        XCTAssertEqual(fake.requested,[.microphone]); XCTAssertEqual(s.focus,.systemAudio)
        send(.primaryTapped(.systemAudio))
        XCTAssertEqual(fake.openedKinds,[.systemAudio]); XCTAssertTrue(s.isPolling)
        var ticks=0
        while s.isPolling && ticks<10 { send(.pollTick); ticks+=1 }
        XCTAssertEqual(s.snapshot.status(.systemAudio),.authorized); XCTAssertEqual(s.phase,.active)
        XCTAssertLessThan(ticks,10)
        XCTAssertEqual(s.focus,.accessibility)
        XCTAssertEqual(PermissionCardModel.make(.accessibility,state:s).needLabel,"“Zoom’u izle” modunda gerekli")
        send(.finish)
        XCTAssertEqual(s.phase,.finished); XCTAssertTrue(s.allRequiredGranted)
        XCTAssertEqual(PermissionCardModel.all(s).map(\.kind),PermissionKind.allCases)
    }
}
