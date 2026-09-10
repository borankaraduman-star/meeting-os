import XCTest
@testable import MeetingOS

/// Joining a team is a click, so the pieces the app owns are the ones a click passes through: is this URL an
/// invite at all, where does the Ekip card say my knowledge goes, and what does the confirmation sheet read.
/// The payload itself is parsed in Python (`team_cloud.parse_invite`) and never here, on purpose — one rule
/// about what a valid invite is, in one place.
final class TeamInviteTests:XCTestCase {
    let token=String(repeating:"a",count:32)

    func testAJoinLinkIsRecognisedAndATranscriptWordLinkIsNot() {
        XCTAssertTrue(TeamInvite.isJoinURL(URL(string:"meetingos://join?team=\(token)")!))
        XCTAssertTrue(TeamInvite.isJoinURL(URL(string:"MEETINGOS://JOIN?team=\(token)&key=sk-or-v1-abcdefgh")!))
        // The transcript renders every word as meetingos://word; mistaking one for an invite would try to join
        // a team on every click in the reading view.
        XCTAssertFalse(TeamInvite.isJoinURL(URL(string:"meetingos://word?seg=1&i=2&w=Jira")!))
        XCTAssertFalse(TeamInvite.isJoinURL(URL(string:"https://join/?team=\(token)")!))
        XCTAssertNotNil(WordClick.parse(URL(string:"meetingos://word?seg=1&i=2&w=Jira")!))
        XCTAssertNil(WordClick.parse(URL(string:"meetingos://join?team=\(token)")!))
    }

    func testAnInviteFileIsRecognisedByItsExtension() {
        XCTAssertEqual(TeamInvite.fileName,"Meeting OS Daveti.meetingos-invite")
        XCTAssertTrue(TeamInvite.isInviteFile(URL(fileURLWithPath:"/tmp/"+TeamInvite.fileName)))
        XCTAssertTrue(TeamInvite.isInviteFile(URL(fileURLWithPath:"/tmp/Davet.MEETINGOS-INVITE")))
        XCTAssertFalse(TeamInvite.isInviteFile(URL(fileURLWithPath:"/tmp/davet.json")))
        XCTAssertFalse(TeamInvite.isInviteFile(URL(string:"meetingos://join?team=\(token)")!))
        XCTAssertEqual(TeamInvite.uti,"local.boran.meeting-os.invite")
    }

    func testThePasteFieldSendsOnAnythingButWhitespace() {
        XCTAssertNil(TeamInvite.payload(""))
        XCTAssertNil(TeamInvite.payload("   \n\t "))
        XCTAssertEqual(TeamInvite.payload("  meetingos://join?team=\(token)  "),"meetingos://join?team=\(token)")
        XCTAssertEqual(TeamInvite.payload(token),token)   // a bare token is an invite too; Python decides
    }

    /// P0 #1 of the 10 Sep 2026 review: the card said "Seçilmedi" and greyed the switches out while the cloud
    /// was sharing everything. The line has to name the target that is actually in use.
    func testTheCardNamesTheTargetThatIsActuallyInUse() {
        let cloud=TeamInvite.target(["team_root_kind":"cloud",
                                     "team_cloud":["team_id_short":"a1b2c3","hosts":["mac-a","mac-b"],
                                                   "last_ok":"2026-09-10T21:40:03.512345+00:00"]])
        XCTAssertEqual(cloud.kind,.cloud)
        XCTAssertTrue(cloud.sharing)
        XCTAssertTrue(cloud.line.hasPrefix("Ekip bulutu · a1b2c3 · 2 Mac · son eşitleme "))
        XCTAssertEqual(cloud.line.count,"Ekip bulutu · a1b2c3 · 2 Mac · son eşitleme ".count+5)   // HH:mm
        // Before the first pass the server lists no hosts; this Mac is still one Mac and the line says so.
        let fresh=TeamInvite.target(["team_root_kind":"cloud","team_cloud":["team_id_short":"a1b2c3"]])
        XCTAssertEqual(fresh.line,"Ekip bulutu · a1b2c3 · 1 Mac · ilk eşitleme bekleniyor")
        XCTAssertTrue(fresh.sharing)

        let folder=TeamInvite.target(["team_root_kind":"team","team_root":"/Users/x/Ekip"],home:"/Users/x")
        XCTAssertEqual(folder.kind,.folder)
        XCTAssertEqual(folder.line,"Ekip klasörü · ~/Ekip")
        XCTAssertTrue(folder.sharing)
        XCTAssertEqual(TeamInvite.target(["team_root_kind":"team","team_root":"/Volumes/Ekip"]).line,"Ekip klasörü · /Volumes/Ekip")
        // iCloud Drive is a folder as far as the switches are concerned: files really do go there.
        let icloud=TeamInvite.target(["team_root_kind":"icloud","team_root":"/Users/x/iCloud/MeetingOS-Shared"],home:"/Users/x")
        XCTAssertEqual(icloud.kind,.folder)
        XCTAssertTrue(icloud.line.hasSuffix("(iCloud Drive)"))

        for empty in [["team_root_kind":"none"],[String:Any]()] {
            let off=TeamInvite.target(empty)
            XCTAssertEqual(off.kind,.off)
            XCTAssertFalse(off.sharing)   // and ONLY here are the three share switches dead
            XCTAssertEqual(off.line,"Kapalı (bulut bağlı değil: OpenRouter anahtarı girilince kendiliğinden bağlanır)")
        }
    }

    func testTheConfirmationSheetSaysWhichTeamAndHowManyMacs() {
        let joined=TeamInvite.outcome(["joined":true,"team_id_short":"a1b2c3","key_written":false,
                                       "synced":["hosts":["mac-a","mac-b","mac-c"]]])
        XCTAssertTrue(joined.ok)
        XCTAssertEqual(joined.line,"Ekibe katıldınız · ekip a1b2c3 · 3 Mac")
        let withKey=TeamInvite.outcome(["joined":true,"team_id_short":"a1b2c3","key_written":true,"synced":[String:Any]()])
        XCTAssertEqual(withKey.line,"Ekibe katıldınız · ekip a1b2c3 · 1 Mac · OpenRouter anahtarı da geldi")
        // Python writes the refusals in Turkish; the sheet repeats them rather than inventing its own.
        let bad=TeamInvite.outcome(["error":"Davetteki ekip belirteci geçersiz"])
        XCTAssertFalse(bad.ok)
        XCTAssertEqual(bad.line,"Davetteki ekip belirteci geçersiz")
        XCTAssertFalse(TeamInvite.outcome([String:Any]()).ok)
        XCTAssertEqual(TeamInvite.outcome([String:Any]()).line,"Davet uygulanamadı")
    }

    /// Both new sheets wear the standard chrome, so both titles have to be in the list the chrome test walks.
    func testTheInviteSheetsAreDeclaredInTheChrome() {
        XCTAssertTrue(SheetChrome.titles.contains("Ekibe katıl"))
        XCTAssertTrue(SheetChrome.titles.contains("Ekip daveti"))
    }
}
