import XCTest
@testable import MeetingOS
final class ResourceGuardTests:XCTestCase {
    func testSixteenGBBudgetReservesMostMemoryForDesktop() {
        XCTAssertEqual(ResourceGuard.budget(physical:16*1024*1024*1024),4*1024*1024*1024)
    }
    func testOnlyLocalModelJobsStopOnMemoryPressure() {
        XCTAssertTrue(ResourceGuard.stopsOnPressure(jobArguments:["retry","m1"]))
        XCTAssertTrue(ResourceGuard.stopsOnPressure(jobArguments:["analyze","m1"]))
        XCTAssertTrue(ResourceGuard.stopsOnPressure(jobArguments:["record","/d","--live","--seconds","14400"]))
        XCTAssertFalse(ResourceGuard.stopsOnPressure(jobArguments:["record","/d","--seconds","14400"]))
        XCTAssertFalse(ResourceGuard.stopsOnPressure(jobArguments:["openrouter-finalize","m1","--allow-upload"]))
        XCTAssertFalse(ResourceGuard.stopsOnPressure(jobArguments:["openrouter-import","--no-local","--allow-upload","/a.m4a"]))
        XCTAssertFalse(ResourceGuard.stopsOnPressure(jobArguments:[]))
    }
    func testDisplaySleepGuardIsHeldOnlyWhileActive() {
        XCTAssertFalse(DisplaySleepGuard.active)
        DisplaySleepGuard.begin();XCTAssertTrue(DisplaySleepGuard.active)
        DisplaySleepGuard.begin();XCTAssertTrue(DisplaySleepGuard.active)   // idempotent
        DisplaySleepGuard.end();XCTAssertFalse(DisplaySleepGuard.active)
        DisplaySleepGuard.end();XCTAssertFalse(DisplaySleepGuard.active)
    }
    func testFootprintReadsCurrentProcessWithoutAllocatingModels() {
        let bytes=ResourceGuard.footprint(pid:getpid())
        XCTAssertNotNil(bytes);XCTAssertGreaterThan(bytes ?? 0,0)
    }
}
