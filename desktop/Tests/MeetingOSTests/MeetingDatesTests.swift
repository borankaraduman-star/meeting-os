import XCTest
@testable import MeetingOS

final class MeetingDatesTests: XCTestCase {
    var cal:Calendar { var c=Calendar(identifier:.gregorian); c.timeZone=TimeZone(identifier:"Europe/Istanbul")!; return c }
    func testGroupsAndLabels() {
        let now=MeetingDates.date("2026-09-09T12:00:00+03:00")!   // Wednesday
        XCTAssertEqual(MeetingDates.group("2026-09-09T10:37:17.232217+00:00",now:now,calendar:cal),"Bugün")
        XCTAssertEqual(MeetingDates.group("2026-09-08T20:00:00+03:00",now:now,calendar:cal),"Dün")
        XCTAssertEqual(MeetingDates.group("2026-09-07T09:00:00+03:00",now:now,calendar:cal),"Bu hafta")   // Monday
        XCTAssertEqual(MeetingDates.group("2026-09-06T09:00:00+03:00",now:now,calendar:cal),"Daha eski")  // Sunday of last week
        XCTAssertEqual(MeetingDates.group("garbage",now:now,calendar:cal),"Daha eski")
        XCTAssertEqual(MeetingDates.label("2026-09-09T10:37:17.232217+00:00",now:now,calendar:cal),"Bugün 13:37")
        XCTAssertEqual(MeetingDates.label("2026-09-08T06:05:00+03:00",now:now,calendar:cal),"Dün 06:05")
        XCTAssertTrue(MeetingDates.label("2026-09-01T14:05:00+03:00",now:now,calendar:cal).hasSuffix("14:05"))
        XCTAssertFalse(MeetingDates.label("2026-09-01T14:05:00+03:00",now:now,calendar:cal).contains("2026"))
        XCTAssertTrue(MeetingDates.label("2025-03-01T14:05:00+03:00",now:now,calendar:cal).contains("2025"))
    }

    func testDayLabels() {
        let now=MeetingDates.date("2026-09-09T12:00:00+03:00")!
        XCTAssertEqual(MeetingDates.dayLabel("2026-09-12",now:now),"12 Eyl")
        XCTAssertEqual(MeetingDates.dayLabel("2025-01-05",now:now),"5 Oca 2025")
        XCTAssertEqual(MeetingDates.dayLabel("garbage",now:now),"garbage")
        XCTAssertTrue(MeetingDates.isPast("2026-09-08",now:now)); XCTAssertFalse(MeetingDates.isPast("2026-09-09",now:now))
    }
}
