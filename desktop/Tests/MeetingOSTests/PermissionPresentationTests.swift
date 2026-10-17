import XCTest
@testable import MeetingOS

final class PermissionPresentationTests:XCTestCase {
    static let allStatuses:[PermissionStatus]=[.authorized,.denied,.notDetermined,.restricted,.unknown,.unsupported,.needsRelaunch]

    static func state(_ kind:PermissionKind,_ st:PermissionStatus,micMode:String="zoom")->PermissionFlowState {
        var snap=PermissionSnapshot(statuses:[.microphone:.authorized,.systemAudio:.authorized,.accessibility:.authorized],micMode:micMode)
        snap=snap.updating(kind,st)
        var s=PermissionFlowState(snapshot:snap); s.phase = .active; s.focus=PermissionFlow.nextFocus(s)
        return s
    }

    func testEveryStatusAndKindHasLabelToneAndOnlyRealActions() {
        for kind in PermissionKind.allCases { for st in Self.allStatuses {
            let c=PermissionPresentation.content(kind,Self.state(kind,st))
            let ctx="\(kind) \(st)"
            XCTAssertFalse(c.card.statusLabel.isEmpty,ctx)
            XCTAssertFalse(c.badgeSymbol.isEmpty,ctx)
            XCTAssertTrue(c.badgeAccessibilityLabel.contains(c.card.statusLabel),ctx)
            XCTAssertFalse(c.privacyNote.isEmpty,ctx)
            for a in c.actions {
                XCTAssertNotEqual(a.action,.none,"no-op action \(ctx)")
                XCTAssertFalse(a.label.trimmingCharacters(in:.whitespaces).isEmpty,"blank button \(ctx)")
            }
            XCTAssertEqual(Set(c.actions.map(\.action)).count,c.actions.count,"duplicate button \(ctx)")
            if st.isGranted || st.isFixedBySystem { XCTAssertTrue(c.actions.isEmpty,"inert status has a button: \(ctx)") }
        } }
    }

    func testPrimaryActionPerStatus() {
        let expected:[PermissionStatus:(PermissionAction,String)]=[
            .notDetermined:(.request,"İzin ver"),.denied:(.openSettings,"Sistem Ayarları’nı aç"),
            .unknown:(.recheck,"Yeniden kontrol et"),.needsRelaunch:(.relaunch,"Meeting OS’u yeniden aç")]
        for kind in PermissionKind.allCases { for (st,(action,label)) in expected {
            let c=PermissionPresentation.content(kind,Self.state(kind,st))
            XCTAssertEqual(c.actions.first?.action,action,"\(kind) \(st)")
            XCTAssertEqual(c.actions.first?.label,label,"\(kind) \(st)")
            XCTAssertTrue(c.actions.first?.isPrimary ?? false)
        } }
    }

    func testToneMatchesStatus() {
        XCTAssertEqual(PermissionPresentation.content(.microphone,Self.state(.microphone,.authorized)).card.tone,.success)
        XCTAssertEqual(PermissionPresentation.content(.microphone,Self.state(.microphone,.denied)).card.tone,.error)
        XCTAssertEqual(PermissionPresentation.content(.accessibility,Self.state(.accessibility,.denied)).card.tone,.warning)
        XCTAssertEqual(PermissionPresentation.content(.systemAudio,Self.state(.systemAudio,.needsRelaunch)).card.tone,.warning)
        XCTAssertEqual(PermissionPresentation.content(.microphone,Self.state(.microphone,.notDetermined)).card.tone,.neutral)
        for t in [PermissionTone.success,.waiting,.warning,.error,.neutral] { XCTAssertFalse(PermissionPresentation.symbol(t).isEmpty); XCTAssertFalse(PermissionPresentation.toneWord(t).isEmpty) }
        XCTAssertEqual(Set([PermissionTone.success,.waiting,.warning,.error,.neutral].map(PermissionPresentation.symbol)).count,5,"tones share a symbol")
    }

    func testNothingUnauthorizedEverSaysGranted() {
        for kind in PermissionKind.allCases { for st in Self.allStatuses where st != .authorized {
            var states=[Self.state(kind,st)]
            var waiting=Self.state(kind,st); waiting.phase = .waitingForSettings; waiting.pending=kind; waiting.pollsLeft=5; states.append(waiting)
            var skipped=Self.state(kind,st); skipped.skipped=[kind]; states.append(skipped)
            for s in states {
                let c=PermissionPresentation.content(kind,s)
                let text=[c.card.statusLabel,c.badgeAccessibilityLabel,c.card.footnote,c.settingsGuide ?? "",c.relaunchExplanation ?? ""].joined(separator:" ").lowercased()
                XCTAssertFalse(text.contains("izin verildi"),"\(kind) \(st): \(text)")
                XCTAssertNotEqual(c.card.tone,.success,"\(kind) \(st)")
            }
        } }
        XCTAssertEqual(PermissionPresentation.content(.microphone,Self.state(.microphone,.authorized)).card.statusLabel,"İzin verildi")
    }

    func testSkipOnlyOnOptionalOrConditional() {
        for kind in PermissionKind.allCases { for st in Self.allStatuses {
            let c=PermissionPresentation.content(kind,Self.state(kind,st))
            if c.actions.contains(where:{ $0.action == .skip }) {
                XCTAssertNotEqual(c.card.need,.required,"\(kind) \(st) can be skipped but is required")
                XCTAssertEqual(PermissionPresentation.label(.skip),"Şimdilik geç")
            }
        } }
        XCTAssertTrue(PermissionPresentation.content(.accessibility,Self.state(.accessibility,.notDetermined)).actions.contains { $0.action == .skip })
        XCTAssertFalse(PermissionPresentation.content(.microphone,Self.state(.microphone,.denied)).actions.contains { $0.action == .skip })
        XCTAssertFalse(PermissionPresentation.content(.systemAudio,Self.state(.systemAudio,.notDetermined)).actions.contains { $0.action == .skip })
    }

    func testSettingsGuideOnlyWhileWaitingForThatGrant() {
        var s=Self.state(.systemAudio,.denied)
        XCTAssertNil(PermissionPresentation.content(.systemAudio,s).settingsGuide)
        s=PermissionFlow.reduce(s,.primaryTapped(.systemAudio))
        XCTAssertEqual(s.effects,[.openSettings(.systemAudio)])
        XCTAssertEqual(PermissionPresentation.content(.systemAudio,s).settingsGuide,"Açılan pencerede Meeting OS’u açın, sonra buraya dönün; durum kendiliğinden güncellenir.")
        XCTAssertNil(PermissionPresentation.content(.microphone,s).settingsGuide)
        XCTAssertEqual(PermissionPresentation.content(.systemAudio,s).actions.first?.action,.recheck)
    }

    func testRelaunchExplanationAndRestrictedCard() {
        let r=PermissionPresentation.content(.systemAudio,Self.state(.systemAudio,.needsRelaunch))
        XCTAssertNotNil(r.relaunchExplanation); XCTAssertEqual(r.actions.first?.action,.relaunch)
        XCTAssertTrue(r.card.footnote.contains("yeniden açılınca"))
        let x=PermissionPresentation.content(.accessibility,Self.state(.accessibility,.restricted))
        XCTAssertTrue(x.actions.isEmpty); XCTAssertFalse(x.card.footnote.isEmpty); XCTAssertNil(x.relaunchExplanation)
        XCTAssertNil(PermissionPresentation.content(.microphone,Self.state(.microphone,.denied)).relaunchExplanation)
    }

    /// Back from Settings with the switch still reading off: the reopen is only offered, never promised. The card
    /// must not tell the user the grant will apply after a relaunch — the status is still `denied`.
    func testSuggestedRelaunchWhileDeniedIsConditional() {
        var s=Self.state(.systemAudio,.denied); s.relaunchSuggested=[.systemAudio]
        let c=PermissionPresentation.content(.systemAudio,s)
        XCTAssertEqual(c.card.statusLabel,"Kapalı")
        XCTAssertTrue(c.actions.contains { $0.action == .relaunch && !$0.isPrimary })
        let text=c.relaunchExplanation ?? ""
        XCTAssertTrue(text.hasPrefix("Anahtarı açtıysanız"),text)
        XCTAssertFalse(text.contains("izin yeniden açılıştan sonra geçerli olur"),text)
        XCTAssertTrue(text.contains("kapalıysa"),text)
        // On evidence (needsRelaunch) the firm sentence stays.
        let firm=PermissionPresentation.content(.systemAudio,Self.state(.systemAudio,.needsRelaunch)).relaunchExplanation ?? ""
        XCTAssertTrue(firm.contains("yeniden açılıştan sonra geçerli olur"),firm)
    }

    func testPrivacyNotes() {
        XCTAssertTrue(PermissionPresentation.privacyNote(.systemAudio).contains("Ekran görüntüsü alınmaz, saklanmaz"))
        XCTAssertTrue(PermissionPresentation.privacyNote(.accessibility).contains("Zoom’un Sesi Aç/Kapat menü satırı"))
    }

    func testStepsAndDoneSummary() {
        var s=PermissionFlowState(snapshot:PermissionSnapshot(statuses:[.microphone:.notDetermined,.systemAudio:.notDetermined,.accessibility:.notDetermined]))
        s.phase = .active; s.focus=PermissionFlow.nextFocus(s)
        XCTAssertEqual(PermissionPresentation.currentStep(s),.microphone)
        XCTAssertEqual(PermissionPresentation.progressText(s),"Adım 1 / 4")
        s.snapshot=s.snapshot.updating(.microphone,.authorized).updating(.systemAudio,.authorized); s.focus=PermissionFlow.nextFocus(s)
        XCTAssertEqual(PermissionPresentation.currentStep(s),.accessibility)
        XCTAssertEqual(PermissionPresentation.mark(.microphone,s),.granted)
        s=PermissionFlow.reduce(s,.skip(.accessibility))
        XCTAssertEqual(PermissionPresentation.currentStep(s),.done)
        XCTAssertEqual(PermissionPresentation.mark(.accessibility,s),.skipped)
        XCTAssertEqual(PermissionPresentation.missingOptional(s),[.accessibility])
        XCTAssertEqual(PermissionPresentation.doneTitle(s),"Kayda hazırsınız")
        XCTAssertTrue(PermissionPresentation.reopenHint.contains("Ayarlar → Sistem"))
        // A required grant locked by MDM: done is reached but never claims readiness.
        s.snapshot=s.snapshot.updating(.systemAudio,.restricted); s.focus=PermissionFlow.nextFocus(s)
        XCTAssertEqual(PermissionPresentation.doneTitle(s),"Kayıt için eksik izin var")
        XCTAssertTrue(PermissionPresentation.doneDetail(s).contains("Ekran ve Sistem Sesi Kaydı"))
    }
}
