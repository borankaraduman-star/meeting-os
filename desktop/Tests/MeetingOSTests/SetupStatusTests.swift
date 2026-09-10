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
}
