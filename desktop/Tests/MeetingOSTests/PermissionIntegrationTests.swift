import XCTest
@testable import MeetingOS

/// The seams between the onboarding and the app: when it shows, what Ayarlar keeps, what a failed recording start
/// says, how the setup list and "Düzelt" defer to the provider, and the app's single flow model reacting to the app
/// becoming active. Fake provider, private NotificationCenter and temp UserDefaults suites — no TCC, no prompt,
/// no System Settings, no relaunch.
@MainActor
final class PermissionIntegrationTests: XCTestCase {
    private let mac15=OperatingSystemVersion(majorVersion:15,minorVersion:0,patchVersion:0)
    private var suites:[String]=[]
    override func tearDown() {
        for s in suites { UserDefaults(suiteName:s)?.removePersistentDomain(forName:s) }
        suites=[]
        super.tearDown()
    }
    private func defaults()->UserDefaults {
        let name="PermissionIntegrationTests-\(UUID().uuidString)"; suites.append(name)
        return UserDefaults(suiteName:name)!
    }
    private func snap(_ mic:PermissionStatus,_ sys:PermissionStatus,_ ax:PermissionStatus = .denied,mode:String="zoom")->PermissionSnapshot {
        PermissionSnapshot(statuses:[.microphone:mic,.systemAudio:sys,.accessibility:ax],micMode:mode,os:mac15)
    }
    private func mainHop() { let e=expectation(description:"main"); DispatchQueue.main.async { e.fulfill() }; wait(for:[e],timeout:2) }

    // MARK: shouldPresentOnboarding

    func testOnboardingShowsOnlyWhenIncompleteAndMissingAndNotRecording() {
        let missing=snap(.notDetermined,.denied), ready=snap(.authorized,.authorized)
        XCTAssertTrue(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:false,snapshot:missing))
        XCTAssertFalse(PermissionIntegration.shouldPresentOnboarding(recording:true,complete:false,snapshot:missing),"never over a recording")
        XCTAssertFalse(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:true,snapshot:missing),"“Şimdilik geç” is final")
        XCTAssertFalse(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:false,snapshot:ready),"a Mac that records gets no tour")
        // One required grant is enough to show it; Accessibility alone never is.
        XCTAssertTrue(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:false,snapshot:snap(.authorized,.denied)))
        XCTAssertFalse(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:false,snapshot:snap(.authorized,.authorized,.denied)))
    }

    func testCompletionStoredByFinishDecidesThePresentation() {
        let fake=FakePermissionProvider(os:mac15,[.microphone:.denied,.systemAudio:.denied,.accessibility:.denied])
        let model=PermissionFlowModel(provider:fake,defaults:defaults(),center:NotificationCenter(),ticker:{ _,_ in {} })
        XCTAssertTrue(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:model.isCompletionStored,snapshot:model.state.snapshot))
        model.finish()   // "Şimdilik geç" with grants still missing
        XCTAssertTrue(model.isCompletionStored)
        XCTAssertFalse(model.allRequiredGranted,"skipping does not pretend the grants are on")
        XCTAssertFalse(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:model.isCompletionStored,snapshot:model.state.snapshot))
    }

    // MARK: Ayarlar list

    func testSettingsListKeepsEveryRowButTheThreeTheSectionOwns() {
        let checks=["mic","screen","calendar","accessibility","reminders","notify","key"].map { SetupCheck(id:$0,title:$0,state:.ok,hint:"") }
        XCTAssertEqual(PermissionIntegration.visibleChecks(checks).map(\.id),["calendar","reminders","notify","key"])
    }

    // MARK: Recording start

    func testHelperReportedRefusalNamesTheKindMicrophoneFirst() {
        XCTAssertEqual(PermissionIntegration.deniedKind(["permission":["microphone":"denied","screen_audio":"granted"]]),.microphone)
        XCTAssertEqual(PermissionIntegration.deniedKind(["permission":["microphone":"granted","screen_audio":"denied"]]),.systemAudio)
        XCTAssertEqual(PermissionIntegration.deniedKind(["permission":["microphone":"denied","screen_audio":"denied"]]),.microphone)
        XCTAssertNil(PermissionIntegration.deniedKind(["permission":["microphone":"requested"]]),"a prompt that is open is not a refusal")
        XCTAssertNil(PermissionIntegration.deniedKind([:]))
    }

    func testOnlyARefusedMicrophoneIsNamedBeforeTheHelperStarts() {
        XCTAssertEqual(PermissionIntegration.knownRefusal(snap(.denied,.authorized)),.microphone)
        XCTAssertNil(PermissionIntegration.knownRefusal(snap(.notDetermined,.denied)),"macOS has not been asked; the helper asks")
        XCTAssertNil(PermissionIntegration.knownRefusal(snap(.authorized,.denied)),"screen reads off on a Mac that was never asked: not evidence")
    }

    func testGuidanceNamesThePaneAndGoesAwayWhenTheGrantReads() {
        let g=PermissionIntegration.guidance(.systemAudio,snapshot:snap(.authorized,.denied))
        XCTAssertEqual(g?.kind,.systemAudio)
        XCTAssertTrue(g!.message.contains("Ekran ve Sistem Sesi Kaydı"))
        XCTAssertEqual(g?.buttonLabel,"Sistem sesi iznini aç")
        XCTAssertEqual(PermissionIntegration.guidance(.microphone,snapshot:snap(.denied,.authorized))?.buttonLabel,"Mikrofon iznini aç")
        XCTAssertNil(PermissionIntegration.guidance(.microphone,snapshot:snap(.authorized,.authorized)),"granted since: no banner")
        XCTAssertNil(PermissionIntegration.guidance(nil,snapshot:snap(.denied,.denied)))
        XCTAssertNil(PermissionIntegration.guidance(.accessibility,snapshot:snap(.authorized,.authorized,.denied)),"never blocks a recording")
    }

    func testWelcomeSummaryIsHonest() {
        XCTAssertTrue(PermissionIntegration.welcomeSummary(snap(.authorized,.authorized)).ready)
        let missing=PermissionIntegration.welcomeSummary(snap(.denied,.denied))
        XCTAssertFalse(missing.ready); XCTAssertEqual(missing.title,"Kayıt için izin gerekli")
        XCTAssertTrue(missing.detail.contains("Mikrofon")); XCTAssertTrue(missing.detail.contains("Sistem sesi"))
        XCTAssertFalse(PermissionIntegration.welcomeSummary(snap(.authorized,.needsRelaunch)).ready,"needs-relaunch is not green")
    }

    // MARK: Reopen

    func testRelaunchScriptWaitsForThePidAndQuotesThePath() {
        let script=AppRelaunch.script(pid:4242,appPath:"/Users/o'neil/Applications/Meeting OS.app")
        XCTAssertTrue(script.contains("kill -0 4242"))
        XCTAssertTrue(script.contains("-lt 600"),"bounded: a quit that never completes leaves no shell behind")
        XCTAssertTrue(script.hasSuffix("/usr/bin/open -n '/Users/o'\\''neil/Applications/Meeting OS.app'"))
    }

    // MARK: Setup list delegates to the provider

    func testSetupChecksComeFromTheSnapshot() {
        let c=SetupStatus.permissionChecks(calendarWanted:false,snapshot:snap(.notDetermined,.needsRelaunch,.denied))
        let byID=Dictionary(uniqueKeysWithValues:c.map { ($0.id,$0) })
        XCTAssertEqual(byID["mic"]?.state,.unknown)
        XCTAssertEqual(byID["screen"]?.state,.missing,"needsRelaunch is not ok")
        XCTAssertTrue(byID["screen"]!.hint.contains("yeniden açınca"))
        XCTAssertEqual(byID["accessibility"]?.state,.optional)
        let ok=SetupStatus.permissionChecks(calendarWanted:false,snapshot:snap(.authorized,.authorized,.authorized))
        XCTAssertEqual(ok.filter { ["mic","screen","accessibility"].contains($0.id) }.map(\.state),[.ok,.ok,.ok])
        let restricted=SetupStatus.permissionChecks(calendarWanted:false,snapshot:snap(.restricted,.authorized)).first { $0.id == "mic" }
        XCTAssertEqual(restricted?.state,.missing); XCTAssertTrue(restricted!.hint.contains("Yönetici"))
        // The path in the hint follows the OS wording.
        XCTAssertTrue(SetupStatus.screenCheck(snap(.authorized,.denied)).hint.contains("Ekran ve Sistem Sesi Kaydı"))
    }

    func testFixDefersToTheProvider() {
        func run(_ statuses:[PermissionKind:PermissionStatus],_ id:String,outcome:[PermissionKind:PermissionStatus]=[:])->FakePermissionProvider {
            let fake=FakePermissionProvider(os:mac15,statuses); fake.requestOutcome=outcome
            let done=expectation(description:"done-\(id)")
            SetupStatus.fix(id,calendarWanted:false,provider:fake) { done.fulfill() }
            wait(for:[done],timeout:2)
            return fake
        }
        let ask=run([.microphone:.notDetermined],"mic")
        XCTAssertEqual(ask.requested,[.microphone]); XCTAssertTrue(ask.openedKinds.isEmpty,"never asked: prompt, not Settings")
        let refused=run([.microphone:.denied],"mic")
        XCTAssertTrue(refused.requested.isEmpty); XCTAssertEqual(refused.openedKinds,[.microphone],"refused: only Settings can change it")
        let screen=run([.systemAudio:.denied],"screen")
        XCTAssertEqual(screen.requested,[.systemAudio]); XCTAssertEqual(screen.openedKinds,[.systemAudio])
        let granted=run([.systemAudio:.denied],"screen",outcome:[.systemAudio:.authorized])
        XCTAssertTrue(granted.openedKinds.isEmpty,"granted by the prompt: nothing to open")
        let ax=run([.accessibility:.denied],"accessibility")
        XCTAssertEqual(ax.requested,[.accessibility]); XCTAssertTrue(ax.openedKinds.isEmpty,"the live request opens its own pane")
    }

    // MARK: One flow model, re-checked on activation

    func testBecomingActiveRereadsTheSingleModelAndChangesTheVerdict() {
        let fake=FakePermissionProvider(os:mac15,[.microphone:.authorized,.systemAudio:.denied,.accessibility:.denied])
        let center=NotificationCenter()
        let model=PermissionFlowModel(provider:fake,defaults:defaults(),center:center,ticker:{ _,_ in {} })
        XCTAssertTrue(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:false,snapshot:model.state.snapshot))
        fake.statuses[.systemAudio] = .authorized   // the user flicked the switch in System Settings
        center.post(name:NSApplication.didBecomeActiveNotification,object:nil); mainHop()
        XCTAssertTrue(model.allRequiredGranted)
        XCTAssertFalse(PermissionIntegration.shouldPresentOnboarding(recording:false,complete:false,snapshot:model.state.snapshot))
        XCTAssertNil(PermissionIntegration.guidance(.systemAudio,snapshot:model.state.snapshot),"the banner goes away on its own")
    }

    func testAttachedRecordingStateRefusesTheRelaunch() {
        let fake=FakePermissionProvider(os:mac15,[.microphone:.authorized,.systemAudio:.needsRelaunch,.accessibility:.denied])
        let model=PermissionFlowModel(provider:fake,defaults:defaults(),center:NotificationCenter(),ticker:{ _,_ in {} })
        var recording=true, relaunched=0
        model.attach(isRecording:{ recording },relaunch:{ relaunched+=1 })
        model.appear()
        model.tapPrimary(.systemAudio)   // primary action of needsRelaunch
        XCTAssertEqual(relaunched,0); XCTAssertTrue(model.relaunchRefused,"the sheet says why")
        recording=false
        model.tapPrimary(.systemAudio)
        XCTAssertEqual(relaunched,1); XCTAssertFalse(model.relaunchRefused)
    }

    func testRefreshReturnsTheSnapshotTheSetupListIsBuiltFrom() {
        let fake=FakePermissionProvider(os:mac15,[.microphone:.authorized,.systemAudio:.authorized,.accessibility:.denied])
        let model=PermissionFlowModel(provider:fake,defaults:defaults(),center:NotificationCenter(),ticker:{ _,_ in {} })
        fake.statuses[.microphone] = .denied
        let snapshot=model.refresh()
        XCTAssertEqual(snapshot.status(.microphone),.denied); XCTAssertEqual(model.state.snapshot,snapshot)
        XCTAssertEqual(SetupStatus.permissionChecks(calendarWanted:false,snapshot:snapshot).first { $0.id == "mic" }?.state,.missing)
    }

    func testMicModeChangeMovesAccessibilityBetweenConditionalAndOptional() {
        let fake=FakePermissionProvider(os:mac15,[.microphone:.authorized,.systemAudio:.authorized,.accessibility:.denied])
        let model=PermissionFlowModel(provider:fake,micMode:"zoom",defaults:defaults(),center:NotificationCenter(),ticker:{ _,_ in {} })
        XCTAssertEqual(model.state.snapshot.need(.accessibility),.conditional)
        model.setMicMode("manual")
        XCTAssertEqual(model.state.snapshot.need(.accessibility),.optional)
    }
}
