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
        XCTAssertEqual(c.map(\.id),["key","glossary","signing","update","reports"])
        XCTAssertEqual(c.map(\.state),[.ok,.ok,.ok,.ok,.optional]); XCTAssertTrue(c[1].hint.contains("300 terim"))
        let d=SetupStatus.serviceChecks([:])
        XCTAssertEqual(d.map(\.state),[.missing,.optional,.missing,.ok,.optional])
        XCTAssertEqual(SetupStatus.reportsCheck(["reports_on":true,"reports_writable":true,"reports_written":3]).hint,"Açık · 3 rapor iCloud Drive’da")
        XCTAssertEqual(SetupStatus.reportsCheck(["reports_on":true,"reports_writable":false,"reports_dir":"/x"]).state,.missing)
        XCTAssertEqual(SetupStatus.serviceChecks(["update_behind":3])[3].hint,"3 değişiklik geride · kenar çubuğundan güncelleyin")
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
    /// P0-4: the setup card and the sidebar must say the same thing about a branch that cannot be updated.
    func testDivergedBranchReplacesTheUpToDateRow() {
        let info=UpdateInfo.parse(["available":false,"diverged":true,"ahead":2])
        let row=SetupStatus.serviceChecks(["update_behind":0],divergedNotice:info.divergedNotice)[3]
        XCTAssertEqual(row.state,.missing)
        XCTAssertEqual(row.hint,info.divergedNotice)
        XCTAssertTrue(row.hint.hasPrefix(UpdateInfo.divergedMessage))
        // The bridge's own flag is enough when the sidebar has not checked yet.
        XCTAssertEqual(SetupStatus.serviceChecks(["update_behind":0,"update_diverged":true,"update_hint":"Dal ayrıştı"])[3].hint,"Dal ayrıştı")
    }
}
