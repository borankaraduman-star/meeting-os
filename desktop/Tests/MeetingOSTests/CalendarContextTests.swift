import XCTest
@testable import MeetingOS

final class CalendarContextTests: XCTestCase {
    private func c(_ title:String,_ startMin:Double,_ endMin:Double,attendees:[String]=[],now:Date)->CalendarContext.Candidate {
        CalendarContext.Candidate(title:title,start:now.addingTimeInterval(startMin*60),end:now.addingTimeInterval(endMin*60),attendees:attendees)
    }
    func testPicksTheEventCoveringNowAndPrefersTheMostRecentStart() {
        let now=Date()
        let ev=CalendarContext.pick([c("Sabah standup",-60,-30,now:now),c("Sprint planlama",-20,40,attendees:["Ayşe","ayşe","Ali"],now:now),c("Retro",-40,20,now:now),c("Yarın",120,180,now:now)],now:now)
        XCTAssertEqual(ev?.title,"Sprint planlama"); XCTAssertEqual(ev?.attendees,["Ayşe","Ali"])
    }
    func testGraceAndEmptyTitles() {
        let now=Date()
        XCTAssertEqual(CalendarContext.pick([c("Bitti",-60,-3,now:now)],now:now)?.title,"Bitti")   // ended 3 min ago still counts
        XCTAssertNil(CalendarContext.pick([c("Bitti",-60,-9,now:now)],now:now))
        XCTAssertNil(CalendarContext.pick([c("   ",-10,10,now:now)],now:now))
        XCTAssertNil(CalendarContext.pick([],now:now))
    }
    func testDisplayNameFromAddress() {
        XCTAssertEqual(CalendarContext.displayName(fromAddress:"mailto:ayse.yilmaz@firma.com"),"Ayse Yilmaz")
        XCTAssertEqual(CalendarContext.displayName(fromAddress:"boran_k@x.io"),"Boran K")
        XCTAssertNil(CalendarContext.displayName(fromAddress:"mailto:12345@x.io"))
        XCTAssertNil(CalendarContext.displayName(fromAddress:""))
    }
}
