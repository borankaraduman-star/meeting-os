import XCTest
@testable import MeetingOS

/// The back stack itself: what a jump leaves behind, what it refuses to leave behind, and what falls off
/// the bottom. The Model side (which jumps push) is UI behaviour; this is the arithmetic under it.
final class BackStackTests:XCTestCase {
    func point(_ meeting:String,_ tab:String="transcript",focus:Int?=nil,search:String="")->NavPoint {
        NavPoint(meeting:meeting,tab:tab,focusedSegment:focus,search:search)
    }

    func testPushKeepsOrderAndPopReturnsTheLastPlace() {
        var stack=NavHistory.pushed([],point("m1",  "analysis"))
        stack=NavHistory.pushed(stack,point("m2","memory"))
        XCTAssertEqual(stack.count,2)
        let (top,rest)=NavHistory.popped(stack)
        XCTAssertEqual(top,point("m2","memory"))
        XCTAssertEqual(rest,[point("m1","analysis")])
    }

    func testPoppingAnEmptyStackIsHarmless() {
        let (top,rest)=NavHistory.popped([])
        XCTAssertNil(top)
        XCTAssertTrue(rest.isEmpty)
    }

    func testTheSamePlaceIsNeverStackedTwice() {
        // Two jumps out of one place (evidence resolving in two steps) must cost one press of Geri, not two.
        let stack=NavHistory.pushed(NavHistory.pushed([],point("m1","review")),point("m1","review"))
        XCTAssertEqual(stack,[point("m1","review")])
    }

    func testADifferentSearchOrFocusIsADifferentPlace() {
        var stack=NavHistory.pushed([],point("m1",search:"bütçe"))
        stack=NavHistory.pushed(stack,point("m1",focus:12,search:"bütçe"))
        XCTAssertEqual(stack.count,2)
    }

    func testTheStackIsCappedAndDropsTheOldestPlaces() {
        var stack:[NavPoint]=[]
        for i in 0..<(NavHistory.cap+5) { stack=NavHistory.pushed(stack,point("m\(i)")) }
        XCTAssertEqual(stack.count,NavHistory.cap)
        XCTAssertEqual(stack.first,point("m5"))
        XCTAssertEqual(stack.last,point("m\(NavHistory.cap+4)"))
    }
}
