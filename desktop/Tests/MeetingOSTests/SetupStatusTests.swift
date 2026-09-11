import XCTest
@testable import MeetingOS

final class SetupStatusTests: XCTestCase {
    func testFixLabelDependsOnWhetherMacOSWasEverAsked() {
        XCTAssertEqual(SetupStatus.fixLabel(SetupCheck(id:"notify",title:"",state:.unknown,hint:"")),"İzin iste")
        XCTAssertEqual(SetupStatus.fixLabel(SetupCheck(id:"notify",title:"",state:.optional,hint:"")),"Ayarları aç")
        XCTAssertEqual(SetupStatus.panes["screen"],"Privacy_ScreenCapture")
    }
    func testServiceChecksReadBridgeAnswer() {
        let c=SetupStatus.serviceChecks(["api_key":true,"glossary_terms":300,"glossary_shared":true,"update_behind":0,"signing_partition":true])
        XCTAssertEqual(c.map(\.id),["key","glossary","signing","team","update","reports"])
        XCTAssertEqual(c.map(\.state),[.ok,.ok,.ok,.missing,.ok,.optional])   // no team root in this answer → missing; XCTAssertTrue(c[1].hint.contains("300 terim"))
        let d=SetupStatus.serviceChecks([:])
        XCTAssertEqual(d.map(\.state),[.missing,.optional,.missing,.missing,.ok,.optional])
        XCTAssertEqual(SetupStatus.reportsCheck(["reports_on":true,"reports_writable":true,"reports_written":3]).hint,"Açık · 3 rapor iCloud Drive’da")
        XCTAssertEqual(SetupStatus.reportsCheck(["reports_on":true,"reports_writable":false,"reports_dir":"/x"]).state,.missing)
        XCTAssertEqual(SetupStatus.serviceChecks(["update_behind":3])[4].hint,"3 değişiklik geride · kenar çubuğundan güncelleyin")
    }
    /// 1.2.82: the fleet's own numbers on the setup card. A Mac with nothing measured gets NO row — an
    /// empty measurement must never be drawn as a green zero — and the row only turns red on the same bar
    /// the fleet alert uses: a 30 % rise with enough observations behind both periods.
    func testQualityTrendRowAppearsOnlyWhenThereIsSomethingToSay() {
        XCTAssertNil(SetupStatus.qualityCheck([:]))
        XCTAssertNil(SetupStatus.qualityCheck(["quality_trend":["line":"   "]]))
        XCTAssertEqual(SetupStatus.serviceChecks([:]).map(\.id),["key","glossary","signing","team","update","reports"])
        let quiet=SetupStatus.qualityCheck(["quality_trend":["line":"Kalite ölçümü: düzeltme oranı %4,0 → %4,2","eligible":true,"change":0.05]])
        XCTAssertEqual(quiet?.id,"quality"); XCTAssertEqual(quiet?.state,.optional)
        XCTAssertEqual(quiet?.hint,"Kalite ölçümü: düzeltme oranı %4,0 → %4,2")
        let worse=SetupStatus.qualityCheck(["quality_trend":["line":"Kalite ölçümü: düzeltme oranı %4,0 ↑ %8,0 (16/200)","eligible":true,"change":1.0,
                                                             "top_errors":[["metric":"word_repeat_errors","n":9,"d":100]]]])
        XCTAssertEqual(worse?.state,.missing)
        XCTAssertTrue(worse!.hint.hasSuffix(" · en çok: öğretilen kelime yine yanlış"))
        // Not enough observations: the Python side says so in the line and the row stays a note.
        let thin=SetupStatus.qualityCheck(["quality_trend":["line":"Kalite ölçümü: son 7 günde düzeltme oranı %50,0 (5/10) · karşılaştırma için en az 20 gözlem gerek","eligible":false,"change":4.0]])
        XCTAssertEqual(thin?.state,.optional)
        XCTAssertEqual(SetupStatus.serviceChecks(["quality_trend":["line":"Kalite ölçümü: bu dönemde sayılacak gözlem yok"]]).map(\.id).last,"quality")
    }
    /// 1.2.83: the identity calibration shares the quality row and the team counterfactual the team row.
    /// Both are read from files the idle housekeeping writes, so an install that has never measured either
    /// gets neither line — and a calibration with too little evidence says so instead of recommending.
    func testIdentityCalibrationAndTeamEffectRideTheRowsTheyBelongTo() {
        // Nothing measured at all: still no quality row.
        XCTAssertNil(SetupStatus.qualityCheck(["calibration":["line":""]]))
        // A calibration alone is enough to draw the row, even with no fleet trend behind it.
        let alone=SetupStatus.qualityCheck(["calibration":["line":"kalibrasyon: veri yetersiz (n=7)"]])
        XCTAssertEqual(alone?.state,.optional)
        XCTAssertEqual(alone?.hint,"kalibrasyon: veri yetersiz (n=7)")
        // Both: one row, both sentences, trend first.
        let both=SetupStatus.qualityCheck(["quality_trend":["line":"Kalite ölçümü: düzeltme oranı %4,0 → %4,2","eligible":true,"change":0.05],
                                           "calibration":["line":"kalibrasyon önerisi: eşik 0.85 (+2 doğru, 0 yanlış, n=24)"]])
        XCTAssertEqual(both?.hint,"Kalite ölçümü: düzeltme oranı %4,0 → %4,2 · kalibrasyon önerisi: eşik 0.85 (+2 doğru, 0 yanlış, n=24)")
        // The team row gains the counterfactual only when there is one; a zero effect is not drawn.
        XCTAssertEqual(SetupStatus.teamEffectTail(["team_profile_effect":["line":""]]),"")
        let team=SetupStatus.serviceChecks(["team_root_kind":"team","team_root":"/Volumes/Ekip",
                                            "team_profile_effect":["line":"ekipten gelen profiller: +2 doğru / \u{2212}1 yanlış"]])
        let row=team.first { $0.id=="team" }
        XCTAssertEqual(row?.state,.ok)
        XCTAssertEqual(row?.hint,"ortak bilgi tabanı: /Volumes/Ekip · ekipten gelen profiller: +2 doğru / \u{2212}1 yanlış")
        XCTAssertEqual(SetupStatus.serviceChecks(["team_root_kind":"team","team_root":"/Volumes/Ekip"]).first { $0.id=="team" }?.hint,
                       "ortak bilgi tabanı: /Volumes/Ekip")
    }

    /// 1.2.85. Two things share the quality row with the calibration: whether the machine will ACT on the
    /// recommendation it just printed, and which policy version is live. A Mac that has never promoted one
    /// gets no policy sentence — "politika v0" would announce something that never happened.
    func testThePolicyVersionAndTheOffSwitchAppearOnTheQualityRow() {
        let off=SetupStatus.qualityCheck(["calibration":["line":"kalibrasyon önerisi: eşik 0.85 (+2 doğru, 0 yanlış, n=24) · otomatik uygulama kapalı"],
                                          "policy":["line":""]])
        XCTAssertEqual(off?.state,.optional)
        XCTAssertEqual(off?.hint,"kalibrasyon önerisi: eşik 0.85 (+2 doğru, 0 yanlış, n=24) · otomatik uygulama kapalı")
        let promoted=SetupStatus.qualityCheck(["calibration":["line":"kalibrasyon: mevcut eşik en iyisi (n=31)"],
                                               "policy":["line":"politika v2 · eşik 0.85 · marj 0.05 · kuyruk recency"]])
        XCTAssertEqual(promoted?.hint,"kalibrasyon: mevcut eşik en iyisi (n=31) · politika v2 · eşik 0.85 · marj 0.05 · kuyruk recency")
        // A policy version alone still draws the row: it is the one place the user can see what got applied.
        XCTAssertEqual(SetupStatus.qualityCheck(["policy":["line":"politika v1 · eşik 0.85 · marj 0.05"]])?.hint,
                       "politika v1 · eşik 0.85 · marj 0.05")
    }

    /// The promotion switch is a setting like any other: parsed with a safe default and sent back verbatim.
    func testAutomaticPromotionIsOffUnlessTheSettingsFileSaysOtherwise() {
        XCTAssertFalse(ReportSettings.parse([:]).autoPromotePolicies)
        XCTAssertTrue(ReportSettings.parse(["auto_promote_policies":true]).autoPromotePolicies)
        XCTAssertEqual(ReportSettings.parse(["auto_promote_policies":true]).changes["auto_promote_policies"] as? Bool,true)
    }
    /// P1-4: the signing partition is the step that silently stops every update on a second Mac.
    func testSigningRowCarriesTheOneLineFix() {
        let missing=SetupStatus.serviceChecks(["signing_partition":false],repo:"/Users/x/repo")[2]
        XCTAssertEqual(missing.id,"signing"); XCTAssertEqual(missing.title,"İmzalama izni"); XCTAssertEqual(missing.state,.missing)
        XCTAssertEqual(missing.hint,"Güncelleme başlamadan durur · Terminal’de bir kez: sh /Users/x/repo/scripts/fix-signing-prompts.sh")
        XCTAssertTrue(SetupStatus.serviceChecks(["signing_partition":false])[2].hint.hasSuffix("sh scripts/fix-signing-prompts.sh"))
        XCTAssertEqual(SetupStatus.serviceChecks(["signing_partition":true])[2].hint,"verildi")
        XCTAssertFalse(SetupStatus.fixable(missing))   // only macOS can be asked from here; this one needs a Terminal
    }
    /// A key held only in the Keychain is not a missing key: the app files it the first time it reads it.
    func testKeychainOnlyKeyIsAWarningNotAFailure() {
        let c=SetupStatus.serviceChecks(["api_key":false,"api_key_keychain":true])[0]
        XCTAssertEqual(c.state,.optional)
        XCTAssertEqual(c.hint,"Anahtar Keychain’de; uygulama bir kez okuyunca dosyaya alınır")
        XCTAssertEqual(SetupStatus.serviceChecks(["api_key":true,"api_key_keychain":true])[0].state,.ok)
        XCTAssertEqual(SetupStatus.serviceChecks(["api_key":false,"api_key_keychain":false])[0].state,.missing)
    }
    /// The team knowledge base with nothing to set up: the bridge says "cloud" and the row has to read as a
    /// working shared brain, an outage the app survives, or a first sync that has not happened yet — never as
    /// a missing folder the user has to go and pick.
    func testTeamRowReadsTheCloudState() {
        let ok=SetupStatus.teamRootCheck(["team_root_kind":"cloud","team_cloud":["last_ok":"2026-09-10T21:40:03.512345+00:00","hosts":["mac-a","mac-b"]]])
        XCTAssertEqual(ok.id,"team"); XCTAssertEqual(ok.state,.ok)
        XCTAssertTrue(ok.hint.hasPrefix("ekip bulutu · 2 Mac · son eşitleme "))
        XCTAssertEqual(ok.hint.count,"ekip bulutu · 2 Mac · son eşitleme ".count+5)   // HH:mm, in the reader's own time zone
        let down=SetupStatus.teamRootCheck(["team_root_kind":"cloud","team_cloud":["last_error":"URLError: bağlanılamadı","hosts":["mac-a"]]])
        XCTAssertEqual(down.state,.optional)
        XCTAssertEqual(down.hint,"bulut şu an erişilemiyor (URLError: bağlanılamadı); yerel bilgi korunuyor, bağlanınca eşitlenir")
        // An outage outranks an older success: a Mac that synced this morning and has been failing since noon
        // used to show only "son eşitleme 09:14" (Codex, 10 Sep 2026, P1 #8 note).
        let stale=SetupStatus.teamRootCheck(["team_root_kind":"cloud","team_cloud":["last_ok":"2026-09-10T06:14:00+00:00","last_error":"URLError: bağlanılamadı","hosts":["mac-a","mac-b"]]])
        XCTAssertEqual(stale.state,.optional)
        XCTAssertTrue(stale.hint.hasPrefix("bulut şu an erişilemiyor (URLError: bağlanılamadı) · son başarılı eşitleme "))
        XCTAssertEqual(stale.hint.count,"bulut şu an erişilemiyor (URLError: bağlanılamadı) · son başarılı eşitleme ".count+5)
        let first=SetupStatus.teamRootCheck(["team_root_kind":"cloud","team_cloud":[String:Any]()])
        XCTAssertEqual(first.state,.optional); XCTAssertEqual(first.hint,"ekip bulutu · ilk eşitleme bekleniyor")
        // The folder answers are untouched: a picked folder still wins and a Mac with neither still says so.
        XCTAssertEqual(SetupStatus.teamRootCheck(["team_root_kind":"team","team_root":"/Volumes/Ekip"]).state,.ok)
        XCTAssertEqual(SetupStatus.teamRootCheck(["team_root_kind":"icloud"]).state,.optional)
        XCTAssertEqual(SetupStatus.teamRootCheck([:]).state,.missing)
        XCTAssertEqual(SetupStatus.serviceChecks(["team_root_kind":"cloud","team_cloud":["last_ok":"2026-09-10T21:40:03+00:00"]])[3].state,.ok)
    }
    /// P0-4: the setup card and the sidebar must say the same thing about a branch that cannot be updated.
    func testDivergedBranchReplacesTheUpToDateRow() {
        let info=UpdateInfo.parse(["available":false,"diverged":true,"ahead":2])
        let row=SetupStatus.serviceChecks(["update_behind":0],divergedNotice:info.divergedNotice)[4]
        XCTAssertEqual(row.state,.missing)
        XCTAssertEqual(row.hint,info.divergedNotice)
        XCTAssertTrue(row.hint.hasPrefix(UpdateInfo.divergedMessage))
        // The bridge's own flag is enough when the sidebar has not checked yet.
        XCTAssertEqual(SetupStatus.serviceChecks(["update_behind":0,"update_diverged":true,"update_hint":"Dal ayrıştı"])[4].hint,"Dal ayrıştı")
    }
    /// A downloaded package has no checkout: the row that tells the user to run a script in one, and the row
    /// that offers a git update, cannot stand there. What is left is the package version.
    func testBundledCardDropsTheCheckoutRows() {
        let answer:[String:Any]=["api_key":true,"signing_partition":false,"update_behind":0]
        let plain=SetupStatus.serviceChecks(answer)
        XCTAssertEqual(plain.map(\.id),["key","glossary","signing","team","update","reports"])
        let bundled=SetupStatus.serviceChecks(answer,bundled:true,bundleVersion:"1.2.72")
        XCTAssertEqual(bundled.map(\.id),["key","glossary","team","update","reports"])
        XCTAssertFalse(bundled.contains { $0.id=="signing" })   // names scripts/fix-signing-prompts.sh in a repo nobody has
        let version=bundled[3]
        XCTAssertEqual(version.title,"Paket sürümü")
        XCTAssertEqual(version.hint,"Paket sürümü 1.2.72")
        XCTAssertEqual(version.state,.ok)
        // A package cannot diverge from a branch it does not have; the bundle channel speaks through update_behind.
        let diverged=SetupStatus.serviceChecks(["update_behind":0,"update_diverged":true],bundled:true,bundleVersion:"1.2.72")[3]
        XCTAssertEqual(diverged.state,.ok); XCTAssertEqual(diverged.hint,"Paket sürümü 1.2.72")
        XCTAssertEqual(SetupStatus.serviceChecks(["update_behind":2],bundled:true,bundleVersion:"1.2.72")[3].state,.missing)
    }
}
