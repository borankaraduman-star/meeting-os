import XCTest
@testable import MeetingOS

final class JobPriorityTests: XCTestCase {
    func testRecordingStaysResponsiveEverythingElseYields() {
        XCTAssertEqual(JobPriority.qos(args:["record","/x"],zoomOpen:true),.userInitiated)
        XCTAssertEqual(JobPriority.qos(args:["openrouter-finalize","abc"],zoomOpen:false),.utility)
        XCTAssertEqual(JobPriority.qos(args:["openrouter-finalize","abc"],zoomOpen:true),.background)
        XCTAssertEqual(JobPriority.environment(args:["analyze","abc"],zoomOpen:true),["MEETING_OS_LOW_PRIORITY":"1"])
        XCTAssertEqual(JobPriority.environment(args:["record","/x"],zoomOpen:true),[:])
        XCTAssertEqual(JobPriority.environment(args:["analyze","abc"],zoomOpen:false),[:])
    }
    func testIdlePollingIsThreeTimesSlower() {
        XCTAssertTrue(RefreshCadence.shouldRefresh(tick:1,recording:true,busy:false,active:false))
        XCTAssertTrue(RefreshCadence.shouldRefresh(tick:1,recording:false,busy:false,active:true))
        XCTAssertFalse(RefreshCadence.shouldRefresh(tick:1,recording:false,busy:false,active:false))
        XCTAssertFalse(RefreshCadence.shouldRefresh(tick:2,recording:false,busy:false,active:false))
        XCTAssertTrue(RefreshCadence.shouldRefresh(tick:3,recording:false,busy:false,active:false))
    }
}
