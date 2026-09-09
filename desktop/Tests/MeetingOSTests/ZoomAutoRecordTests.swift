import XCTest
@testable import MeetingOS

final class ZoomAutoRecordTests: XCTestCase {
    func testStartsOnlyAfterConfirmationAndStopsAfterGrace() {
        var m=ZoomAutoRecord(); let t0=Date()
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:false,busy:false,enabled:true,now:t0))
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:false,busy:false,enabled:true,now:t0.addingTimeInterval(4)))
        XCTAssertEqual(m.evaluate(zoomOpen:true,recording:false,busy:false,enabled:true,now:t0.addingTimeInterval(11)),.start)
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(20)))
        XCTAssertNil(m.evaluate(zoomOpen:false,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(30)))   // window flickers away
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(40)))    // and comes back: grace resets
        XCTAssertNil(m.evaluate(zoomOpen:false,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(50)))
        XCTAssertNil(m.evaluate(zoomOpen:false,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(100)))
        XCTAssertNil(m.evaluate(zoomOpen:false,meetingLikely:true,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(400)))   // mic still in use: keep going
        XCTAssertNil(m.evaluate(zoomOpen:false,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(410)))
        XCTAssertEqual(m.evaluate(zoomOpen:false,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(711)),.stop)
    }
    func testManualRecordingsAreNeverStoppedAndDisabledDoesNothing() {
        var m=ZoomAutoRecord(); let t0=Date()
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:false,busy:false,enabled:false,now:t0))
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:false,busy:false,enabled:false,now:t0.addingTimeInterval(60)))
        XCTAssertNil(m.evaluate(zoomOpen:false,recording:true,busy:true,enabled:true,now:t0))            // started by hand
        XCTAssertNil(m.evaluate(zoomOpen:false,recording:true,busy:true,enabled:true,now:t0.addingTimeInterval(500)))
    }
    func testOpenWindowWhileBusyDoesNotStart() {
        var m=ZoomAutoRecord(); let t0=Date()
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:false,busy:true,enabled:true,now:t0))
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:false,busy:true,enabled:true,now:t0.addingTimeInterval(30)))
        XCTAssertNil(m.evaluate(zoomOpen:true,recording:false,busy:false,enabled:true,now:t0.addingTimeInterval(31)))   // confirmation restarts
        XCTAssertEqual(m.evaluate(zoomOpen:true,recording:false,busy:false,enabled:true,now:t0.addingTimeInterval(42)),.start)
    }
}
