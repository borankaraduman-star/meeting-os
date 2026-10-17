import XCTest
import AVFoundation
@testable import MeetingOS

/// The first-time path of the two prompt-only grants, through the REAL `LivePermissionProvider` with its six TCC
/// calls replaced by a scripted fake (`PermissionSystemCalls`), a temp UserDefaults suite and a private
/// NotificationCenter. No prompt, no System Settings, no TCC: the fake records what the provider would have called.
/// The judge's gap: a never-asked Mac read `denied`, so "Enable" opened Settings and the prompt — the only thing that
/// lists Meeting OS in the pane — was never reached. These tests pin the click → real prompt path.
@MainActor
final class PermissionFirstAskTests: XCTestCase {
    private var suites:[String]=[]
    private let mac15=OperatingSystemVersion(majorVersion:15,minorVersion:0,patchVersion:0)

    override func tearDown() {
        for s in suites { UserDefaults(suiteName:s)?.removePersistentDomain(forName:s) }
        suites=[]
        super.tearDown()
    }
    private func defaults()->UserDefaults {
        let name="PermissionFirstAskTests-\(UUID().uuidString)"; suites.append(name)
        return UserDefaults(suiteName:name)!
    }

    /// Scripted system: what each read answers, and a count of every prompt call.
    private final class FakeSystem {
        var mic:AVAuthorizationStatus = .authorized
        var screen=false, trusted=false
        var micAnswer=true
        var micRequests=0, screenRequests=0, axRequests=0, screenReads=0, axReads=0
        var calls:PermissionSystemCalls {
            PermissionSystemCalls(
                microphoneStatus:{ [unowned self] in mic },
                requestMicrophone:{ [unowned self] done in micRequests+=1; mic = micAnswer ? .authorized : .denied; done(micAnswer) },
                screenPreflight:{ [unowned self] in screenReads+=1; return screen },
                screenRequest:{ [unowned self] in screenRequests+=1; return screen },
                accessibilityTrusted:{ [unowned self] in axReads+=1; return trusted },
                accessibilityRequest:{ [unowned self] in axRequests+=1; return trusted })
        }
    }

    private struct Rig {
        let system:FakeSystem, provider:LivePermissionProvider, model:PermissionFlowModel
        let center:NotificationCenter, defaults:UserDefaults, opened:Box
    }
    private final class Box { var urls:[String]=[] }

    private func rig(_ system:FakeSystem=FakeSystem(),defaults d:UserDefaults?=nil,mode:String="zoom")->Rig {
        let center=NotificationCenter(), d=d ?? defaults(), opened=Box()
        let provider=LivePermissionProvider(osVersion:mac15,center:center,defaults:d,system:system.calls,
                                            open:{ opened.urls.append($0.absoluteString); return true })
        let model=PermissionFlowModel(provider:provider,micMode:mode,defaults:d,center:center,ticker:{ _,_ in {} })
        model.appear()
        return Rig(system:system,provider:provider,model:model,center:center,defaults:d,opened:opened)
    }

    /// What the card's primary button sends — the same `PermissionActionButton` closure in the onboarding sheet and
    /// in Ayarlar → Sistem (`PermissionSettingsBlock` forwards it to `permissions.handle`).
    private func tapCardPrimary(_ r:Rig,_ k:PermissionKind) {
        let primary=PermissionPresentation.content(k,r.model.state).actions.first { $0.isPrimary }!
        r.model.handle(.actionTapped(primary.action,primary.kind))
    }
    private func card(_ r:Rig,_ k:PermissionKind)->PermissionCardModel { r.model.cards.first { $0.kind==k }! }
    /// The provider answers on the main queue, then the model hops once more: drain both.
    private func drain() {
        let exp=expectation(description:"main hops")
        DispatchQueue.main.async { DispatchQueue.main.async { DispatchQueue.main.async { exp.fulfill() } } }
        wait(for:[exp],timeout:2)
    }

    // MARK: Accessibility

    func testNeverAskedAccessibilityOffersRealPromptNotSettings() {
        let r=rig()
        XCTAssertEqual(r.provider.status(.accessibility),.notDetermined,"never asked is not a no")
        XCTAssertEqual(r.system.axRequests,0,"reading never prompts")
        let c=card(r,.accessibility)
        XCTAssertEqual(c.statusLabel,"Henüz sorulmadı"); XCTAssertEqual(c.primary,.request); XCTAssertEqual(c.primaryLabel,"İzin iste")
        XCTAssertNotEqual(c.statusLabel,"İzin verildi")

        tapCardPrimary(r,.accessibility)
        XCTAssertEqual(r.system.axRequests,1,"the click runs AXIsProcessTrustedWithOptions(prompt) — what lists the app in the pane")
        XCTAssertTrue(r.defaults.bool(forKey:PermissionPromptLedger.key(.accessibility)))
        drain()
        XCTAssertEqual(r.opened.urls.first,PermissionSettingsLink.modernPrefix+"Privacy_Accessibility","then the pane, so the wait has a place")
        XCTAssertEqual(r.model.state.phase,.waitingForSettings); XCTAssertEqual(r.model.state.pending,.accessibility)
        XCTAssertEqual(card(r,.accessibility).statusLabel,"Sistem Ayarları’nda bekleniyor…")
        XCTAssertEqual(card(r,.accessibility).primary,.recheck)

        // The user flicks the switch and comes back.
        r.system.trusted=true
        r.center.post(name:NSApplication.didBecomeActiveNotification,object:nil)
        XCTAssertEqual(card(r,.accessibility).statusLabel,"İzin verildi"); XCTAssertEqual(card(r,.accessibility).primary,.none)
        XCTAssertEqual(r.system.axRequests,1,"one prompt, one click")
    }

    func testAccessibilityRequestWithUnopenablePaneRecoversInsteadOfWaiting() {
        let d=defaults(), center=NotificationCenter(), system=FakeSystem()
        let provider=LivePermissionProvider(osVersion:mac15,center:center,defaults:d,system:system.calls,open:{ _ in false })
        let model=PermissionFlowModel(provider:provider,micMode:"zoom",defaults:d,center:center,ticker:{ _,_ in {} })
        model.appear()
        model.tapPrimary(.accessibility); drain()
        XCTAssertNotEqual(model.state.phase,.waitingForSettings,"a pane that did not open is not a wait")
        XCTAssertEqual(model.state.notice,.settingsUnavailable(.accessibility)); withExtendedLifetime(system) {}
    }

    func testAskedButStillOffAccessibilityGoesToSettingsWithoutPromptingAgain() {
        let d=defaults()
        let first=rig(defaults:d)
        tapCardPrimary(first,.accessibility); drain()
        // Next launch: same defaults, still not trusted.
        let r=rig(defaults:d)
        XCTAssertEqual(r.provider.status(.accessibility),.denied)
        XCTAssertEqual(card(r,.accessibility).primary,.openSettings)
        tapCardPrimary(r,.accessibility)
        XCTAssertEqual(r.system.axRequests,0,"asked once already: Settings is the only place it can change")
        XCTAssertEqual(r.opened.urls.first,PermissionSettingsLink.modernPrefix+"Privacy_Accessibility")
    }

    func testAccessibilityStaysOptionalAndNeverBlocksCompletion() {
        let s=FakeSystem(); s.screen=true
        let r=rig(s,mode:"manual")
        XCTAssertEqual(card(r,.accessibility).need,.optional)
        XCTAssertEqual(card(r,.accessibility).secondary,.skip,"isteğe bağlı: real skip, no decoy")
        XCTAssertTrue(r.model.allRequiredGranted,"mic + system audio granted; Accessibility is not required")
    }

    // MARK: System audio

    func testNeverAskedSystemAudioCallsScreenCaptureRequest() {
        let r=rig()
        XCTAssertEqual(r.provider.status(.systemAudio),.notDetermined)
        XCTAssertEqual(r.system.screenRequests,0,"preflight only on read")
        XCTAssertEqual(card(r,.systemAudio).primary,.request)
        XCTAssertFalse(r.model.allRequiredGranted,"notDetermined is not granted")

        tapCardPrimary(r,.systemAudio)
        XCTAssertEqual(r.system.screenRequests,1,"the click reaches CGRequestScreenCaptureAccess")
        XCTAssertTrue(r.opened.urls.isEmpty,"macOS’s own prompt carries the Settings button; the app does not race it")
        drain()
        XCTAssertEqual(r.model.state.phase,.waitingForSettings)
        XCTAssertEqual(card(r,.systemAudio).secondary,.openSettings,"if no prompt showed, the user still has a way to the pane")
        XCTAssertEqual(r.provider.status(.systemAudio),.denied,"asked and still off: a real no from now on")

        r.system.screen=true
        r.center.post(name:NSApplication.didBecomeActiveNotification,object:nil)
        XCTAssertEqual(card(r,.systemAudio).statusLabel,"İzin verildi")
        XCTAssertEqual(r.system.screenRequests,1)
    }

    func testSystemAudioReturnWithoutProofIsDeniedButRelaunchIsOffered() {
        let r=rig()
        tapCardPrimary(r,.systemAudio); drain()
        tapCardPrimary(r,.systemAudio)   // waiting → "Yeniden kontrol et"
        r.model.tapSecondary(.systemAudio)   // "Sistem Ayarları’nı aç"
        XCTAssertFalse(r.opened.urls.isEmpty)
        r.center.post(name:NSApplication.didBecomeActiveNotification,object:nil)
        XCTAssertEqual(r.provider.status(.systemAudio),.denied,"a bare false after a Settings visit is not proof of a grant")
        XCTAssertNotEqual(card(r,.systemAudio).statusLabel,"İzin verildi")
    }

    func testGrantedReadsAuthorizedWhetherOrNotAsked() {
        let s=FakeSystem(); s.screen=true; s.trusted=true
        let r=rig(s)
        XCTAssertEqual(r.provider.status(.systemAudio),.authorized)
        XCTAssertEqual(r.provider.status(.accessibility),.authorized)
        XCTAssertEqual(s.screenRequests+s.axRequests,0)
    }

    // MARK: Microphone and the setup list

    func testMicrophoneAsksOnlyWhileNotDetermined() {
        let s=FakeSystem(); s.mic = .notDetermined; s.micAnswer=false
        let r=rig(s)
        XCTAssertEqual(card(r,.microphone).primary,.request)
        tapCardPrimary(r,.microphone); drain()
        XCTAssertEqual(s.micRequests,1)
        XCTAssertEqual(card(r,.microphone).statusLabel,"Kapalı"); XCTAssertEqual(card(r,.microphone).primary,.openSettings)
        tapCardPrimary(r,.microphone)
        XCTAssertEqual(s.micRequests,1,"macOS asks once; then System Settings")
    }

    func testSetupListFixReachesThePromptsToo() {
        let r=rig()
        let exp=expectation(description:"fix")
        SetupStatus.fixPermission(.accessibility,provider:r.provider) {
            SetupStatus.fixPermission(.systemAudio,provider:r.provider) { exp.fulfill() }
        }
        wait(for:[exp],timeout:2)
        XCTAssertEqual(r.system.axRequests,1); XCTAssertEqual(r.system.screenRequests,1)
    }

    func testLedgerTable() {
        XCTAssertEqual(PermissionPromptLedger.status(granted:true,asked:false),.authorized)
        XCTAssertEqual(PermissionPromptLedger.status(granted:true,asked:true),.authorized)
        XCTAssertEqual(PermissionPromptLedger.status(granted:false,asked:false),.notDetermined)
        XCTAssertEqual(PermissionPromptLedger.status(granted:false,asked:true),.denied)
    }
}
