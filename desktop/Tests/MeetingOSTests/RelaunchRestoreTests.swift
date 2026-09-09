import XCTest
@testable import MeetingOS
final class RelaunchRestoreTests:XCTestCase {
    func meeting(_ id:String,_ status:String,owner:String,created:String,display:String?=nil)->Meeting {
        Meeting(["id":id,"title":id,"status":status,"recovery_state":owner,"created":created,"display_status":display ?? status])
    }
    func testPicksMostRecentInterruptedMeetingAndIgnoresActiveOwners() {
        let meetings=[
            meeting("old","incomplete",owner:"interrupted",created:"2026-09-08T10:00:00+00:00"),
            meeting("live","provisional",owner:"active",created:"2026-09-09T12:00:00+00:00"),
            meeting("mid","processing",owner:"interrupted",created:"2026-09-09T09:00:00+00:00"),
            meeting("done","complete",owner:"complete",created:"2026-09-09T11:00:00+00:00"),
            meeting("failed","failed",owner:"unknown",created:"2026-09-09T11:30:00+00:00"),
        ]
        XCTAssertEqual(RelaunchRestore.pick(meetings:meetings)?.id,"mid")
    }
    func testUnknownOwnerStillRestoresAndEmptyListGivesNothing() {
        XCTAssertNil(RelaunchRestore.pick(meetings:[]))
        XCTAssertNil(RelaunchRestore.pick(meetings:[meeting("live","processing",owner:"active",created:"2026-09-09T12:00:00+00:00")]))
        XCTAssertEqual(RelaunchRestore.pick(meetings:[meeting("u","provisional",owner:"unknown",created:"2026-09-09T12:00:00+00:00")])?.id,"u")
    }
    func testHeadlineUsesDisplayStatusLabel() {
        let pending=meeting("p","provisional",owner:"interrupted",created:"2026-09-09T12:00:00+00:00",display:"pending_finalization")
        XCTAssertEqual(RelaunchRestore.headline(pending),"Sesiniz korundu · işlem şurada kaldı: Son işlem bekliyor")
        XCTAssertEqual(RelaunchRestore.headline(meeting("i","incomplete",owner:"interrupted",created:"")),"Sesiniz korundu · işlem şurada kaldı: Kurtarılabilir")
    }
}
