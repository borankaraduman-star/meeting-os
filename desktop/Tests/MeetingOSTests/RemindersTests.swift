import XCTest
@testable import MeetingOS

final class RemindersTests: XCTestCase {
    func testNoteCarriesSourceOwnerAndTiming() {
        XCTAssertEqual(RemindersBridge.note(meetingTitle:"Sprint",owner:"Ayşe",due:"Cuma"),"Meeting OS · Sprint\nSahip: Ayşe\nZaman: Cuma")
        XCTAssertEqual(RemindersBridge.note(meetingTitle:"",owner:"",due:""),"Meeting OS · toplantı")
    }
}
