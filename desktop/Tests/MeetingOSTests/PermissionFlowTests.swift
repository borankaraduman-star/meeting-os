import XCTest
@testable import MeetingOS

/// The model against a fake provider and a hand-fired ticker. Temp UserDefaults suites, a private
/// NotificationCenter: no TCC, no prompt, no System Settings, no timer.
@MainActor
final class PermissionFlowTests: XCTestCase {
    private var suites:[String]=[]
    private let mac15=OperatingSystemVersion(majorVersion:15,minorVersion:0,patchVersion:0)

    override func tearDown() {
        for s in suites { UserDefaults(suiteName:s)?.removePersistentDomain(forName:s) }
        suites=[]
        super.tearDown()
    }

    private func defaults()->UserDefaults {
        let name="PermissionFlowTests-\(UUID().uuidString)"; suites.append(name)
        return UserDefaults(suiteName:name)!
    }

    private final class Ticks { var fires:[@MainActor ()->Void]=[]; var cancelled=0; var started=0
        func ticker()->PermissionTicker { { [self] _,fire in started+=1; fires.append(fire); return { [self] in cancelled+=1; fires.removeAll() } } }
        @MainActor func fire() { fires.last?() }
    }

    private struct Rig {
        let fake:FakePermissionProvider, model:PermissionFlowModel, ticks:Ticks, center:NotificationCenter, defaults:UserDefaults
    }
    private func rig(_ statuses:[PermissionKind:PermissionStatus],mode:String="zoom",recording:Bool=false,relaunch:@escaping ()->Void={})->Rig {
        let fake=FakePermissionProvider(os:mac15,statuses), ticks=Ticks(), center=NotificationCenter(), d=defaults()
        let model=PermissionFlowModel(provider:fake,micMode:mode,defaults:d,center:center,ticker:ticks.ticker(),isRecording:{ recording },relaunch:relaunch)
        model.appear()
        return Rig(fake:fake,model:model,ticks:ticks,center:center,defaults:d)
    }
    private func card(_ r:Rig,_ k:PermissionKind)->PermissionCardModel { r.model.cards.first { $0.kind==k }! }
    private func becomeActive(_ r:Rig) { r.center.post(name:NSApplication.didBecomeActiveNotification,object:nil) }

    func testNotDeterminedToAuthorized() {
        let r=rig([.microphone:.notDetermined,.systemAudio:.authorized,.accessibility:.denied])
        XCTAssertEqual(card(r,.microphone).primary,.request); XCTAssertEqual(card(r,.microphone).primaryLabel,"İzin iste")
        r.fake.requestOutcome[.microphone] = .authorized
        r.model.tapPrimary(.microphone)
        let exp=expectation(description:"main hop")
        DispatchQueue.main.async { exp.fulfill() }; wait(for:[exp],timeout:2)
        XCTAssertEqual(r.fake.requested,[.microphone])
        XCTAssertEqual(card(r,.microphone).statusLabel,"İzin verildi"); XCTAssertEqual(card(r,.microphone).primary,.none)
        XCTAssertTrue(r.model.allRequiredGranted); XCTAssertEqual(r.model.finishLabel,"Bitti")
    }

    func testDeniedToSettingsReturnAuthorized() {
        let r=rig([.microphone:.authorized,.systemAudio:.denied,.accessibility:.denied])
        let c=card(r,.systemAudio)
        XCTAssertEqual(c.primary,.openSettings); XCTAssertEqual(c.primaryLabel,"Sistem Ayarları’nı aç")
        XCTAssertTrue(c.footnote.contains("Ekran ve Sistem Sesi Kaydı"))
        r.model.tapPrimary(.systemAudio)
        XCTAssertEqual(r.fake.openedKinds,[.systemAudio])
        XCTAssertTrue(card(r,.systemAudio).isBusy); XCTAssertTrue(r.model.isPolling)
        XCTAssertTrue(card(r,.systemAudio).footnote.contains("döndüğünüzde"))
        r.fake.statuses[.systemAudio] = .authorized
        becomeActive(r)
        XCTAssertEqual(card(r,.systemAudio).statusLabel,"İzin verildi")
        XCTAssertFalse(r.model.isPolling,"granted: the poll stops"); XCTAssertEqual(r.ticks.cancelled,1)
        XCTAssertTrue(r.model.allRequiredGranted)
    }

    func testReturnWithStillDeniedOffersRelaunchNotAGrant() {
        let r=rig([.microphone:.authorized,.systemAudio:.denied,.accessibility:.denied])
        r.model.tapPrimary(.systemAudio); becomeActive(r)
        XCTAssertNotEqual(card(r,.systemAudio).statusLabel,"İzin verildi")
        XCTAssertTrue(r.model.state.relaunchSuggested.contains(.systemAudio))
        XCTAssertEqual(card(r,.systemAudio).secondary,.relaunch)
    }

    func testRestrictedHasNoAction() {
        let r=rig([.microphone:.restricted,.systemAudio:.authorized,.accessibility:.denied])
        let c=card(r,.microphone)
        XCTAssertEqual(c.primary,.none); XCTAssertEqual(c.secondary,.none)
        XCTAssertEqual(c.statusLabel,"Yönetici kısıtlamış"); XCTAssertTrue(c.footnote.contains("yönetici"))
        XCTAssertNotEqual(r.model.state.focus,.microphone,"a focus with no action would strand the user")
        r.model.tapPrimary(.microphone)
        XCTAssertTrue(r.fake.requested.isEmpty); XCTAssertTrue(r.fake.openedKinds.isEmpty)
    }

    func testUnknownOffersRecheck() {
        let r=rig([.microphone:.unknown,.systemAudio:.authorized,.accessibility:.denied])
        XCTAssertEqual(card(r,.microphone).primaryLabel,"Yeniden kontrol et")
        let reads=r.fake.statusReads.count
        r.fake.statuses[.microphone] = .authorized
        r.model.tapPrimary(.microphone)
        XCTAssertGreaterThan(r.fake.statusReads.count,reads)
        XCTAssertEqual(card(r,.microphone).statusLabel,"İzin verildi")
    }

    func testNeedsRelaunchUsesInjectedRelaunchAndRefusesWhileRecording() {
        var relaunched=0
        let r=rig([.microphone:.authorized,.systemAudio:.needsRelaunch,.accessibility:.denied],relaunch:{ relaunched+=1 })
        XCTAssertEqual(card(r,.systemAudio).primary,.relaunch)
        r.model.tapPrimary(.systemAudio)
        XCTAssertEqual(relaunched,1); XCTAssertFalse(r.model.relaunchRefused)
        var again=0
        let busy=rig([.microphone:.authorized,.systemAudio:.needsRelaunch,.accessibility:.denied],recording:true,relaunch:{ again+=1 })
        busy.model.tapPrimary(.systemAudio)
        XCTAssertEqual(again,0); XCTAssertTrue(busy.model.relaunchRefused)
    }

    func testAccessibilityCardWordingFollowsMicModeAndNeverLooksGranted() {
        let zoom=rig([.microphone:.authorized,.systemAudio:.authorized,.accessibility:.denied],mode:"zoom")
        let c=card(zoom,.accessibility)
        XCTAssertEqual(c.need,.conditional); XCTAssertEqual(c.needLabel,"“Zoom’u izle” modunda gerekli")
        XCTAssertTrue(c.reason.contains("Zoom’u izle")); XCTAssertNotEqual(c.statusLabel,"İzin verildi"); XCTAssertEqual(c.primary,.openSettings)
        zoom.model.setMicMode("manual")
        let o=card(zoom,.accessibility)
        XCTAssertEqual(o.need,.optional); XCTAssertEqual(o.needLabel,"İsteğe bağlı"); XCTAssertTrue(o.reason.contains("isteğe bağlıdır"))
        XCTAssertNotEqual(o.statusLabel,"İzin verildi")
        XCTAssertTrue(zoom.model.allRequiredGranted,"accessibility never blocks")
    }

    func testSkippingAccessibilityStaysTruthful() {
        let r=rig([.microphone:.authorized,.systemAudio:.authorized,.accessibility:.denied])
        XCTAssertEqual(card(r,.accessibility).secondary,.skip)
        r.model.tapSecondary(.accessibility)
        let c=card(r,.accessibility)
        XCTAssertTrue(c.statusLabel.hasSuffix("geçildi")); XCTAssertNotEqual(c.statusLabel,"İzin verildi"); XCTAssertEqual(c.tone,.neutral)
        XCTAssertEqual(r.fake.requested,[]); XCTAssertNil(r.model.state.focus)
    }

    func testCompletionPersistsWithVersionAndReopenShowsAgain() {
        let r=rig([.microphone:.authorized,.systemAudio:.denied,.accessibility:.denied])
        XCTAssertEqual(r.model.storedVersion,0); XCTAssertTrue(r.model.shouldPresent)
        XCTAssertEqual(r.model.finishLabel,"Şimdilik geç")
        r.model.finish()
        XCTAssertEqual(r.defaults.integer(forKey:PermissionPolicy.completedVersionKey),PermissionPolicy.onboardingVersion)
        XCTAssertTrue(r.model.isCompletionStored); XCTAssertFalse(r.model.shouldPresent); XCTAssertEqual(r.model.state.phase,.finished)
        XCTAssertEqual(card(r,.systemAudio).statusLabel,"Kapalı","finishing early does not pretend")
        r.model.reopen()
        XCTAssertEqual(r.model.state.phase,.active); XCTAssertFalse(r.model.state.completed)
        XCTAssertTrue(r.model.isCompletionStored,"reopening is a look, not an undo")
        XCTAssertEqual(r.model.state.focus,.systemAudio)
        // A fresh model on the same defaults sees the stored completion.
        let again=PermissionFlowModel(provider:r.fake,defaults:r.defaults,center:r.center,ticker:r.ticks.ticker())
        XCTAssertTrue(again.isCompletionStored)
    }

    func testAllGrantedFinishLabelAndNoPresentation() {
        let r=rig([.microphone:.authorized,.systemAudio:.authorized,.accessibility:.authorized])
        XCTAssertEqual(r.model.finishLabel,"Bitti"); XCTAssertFalse(r.model.shouldPresent)
        XCTAssertEqual(card(r,.accessibility).primary,.none)
    }

    func testPollingIsBoundedAndLeaksNothing() {
        let r=rig([.microphone:.authorized,.systemAudio:.denied,.accessibility:.authorized])
        r.model.tapPrimary(.systemAudio)
        XCTAssertEqual(r.ticks.started,1)
        for _ in 0..<(PermissionPolicy.pollLimit-1) { r.ticks.fire() }
        XCTAssertTrue(r.model.isPolling,"one read left")
        r.ticks.fire()
        XCTAssertFalse(r.model.isPolling); XCTAssertEqual(r.ticks.cancelled,1); XCTAssertTrue(r.ticks.fires.isEmpty)
        XCTAssertEqual(r.model.state.notice,.noChangeSeen(.systemAudio))
        XCTAssertTrue(card(r,.systemAudio).footnote.contains("Değişiklik görülmedi"))
        XCTAssertEqual(card(r,.systemAudio).secondary,.recheck)
        XCTAssertEqual(r.ticks.started,1,"no second timer")
    }

    func testPollNoticesGrantWithoutBecomingActive() {
        let r=rig([.microphone:.authorized,.systemAudio:.denied,.accessibility:.authorized])
        r.model.tapPrimary(.systemAudio)
        r.fake.onStatusRead={ k,_ in if k == .systemAudio { r.fake.statuses[.systemAudio] = .authorized } }
        r.ticks.fire()
        XCTAssertEqual(card(r,.systemAudio).statusLabel,"İzin verildi"); XCTAssertFalse(r.model.isPolling)
    }

    func testSettingsThatWillNotOpenFallBackToManualPath() {
        let r=rig([.microphone:.denied,.systemAudio:.authorized,.accessibility:.authorized])
        r.fake.openableURLs=[]
        r.model.tapPrimary(.microphone)
        XCTAssertFalse(r.model.isPolling); XCTAssertEqual(r.model.state.notice,.settingsUnavailable(.microphone))
        XCTAssertTrue(card(r,.microphone).footnote.contains("Sistem Ayarları açılamadı"))
        XCTAssertTrue(card(r,.microphone).footnote.contains("Gizlilik ve Güvenlik → Mikrofon"))
    }

    func testStopCancelsPollAndDeinitRemovesObserver() {
        let r=rig([.microphone:.authorized,.systemAudio:.denied,.accessibility:.authorized])
        r.model.tapPrimary(.systemAudio); r.model.stop()
        XCTAssertFalse(r.model.isPolling); XCTAssertEqual(r.ticks.cancelled,1)
        weak var weakModel:PermissionFlowModel?
        do {
            let m=PermissionFlowModel(provider:r.fake,defaults:r.defaults,center:r.center,ticker:r.ticks.ticker())
            weakModel=m
        }
        XCTAssertNil(weakModel,"the observer closure holds the model weakly")
    }
}
