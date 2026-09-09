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
    /// The regression: memory pressure during an analyze/retry job used to stop the LIVE RECORDING and leave
    /// the job running, because the job slot predates the recorder's own slot.
    func testMemoryPressureStopsTheJobEvenWhileRecording() {
        XCTAssertEqual(ResourceGuard.pressureAction(hasJob:true,stopsOnPressure:true,recording:true,alreadyStopped:false),.terminateJob)
        XCTAssertEqual(ResourceGuard.pressureAction(hasJob:true,stopsOnPressure:true,recording:false,alreadyStopped:false),.terminateJob)
        XCTAssertEqual(ResourceGuard.pressureAction(hasJob:false,stopsOnPressure:true,recording:true,alreadyStopped:false),.none)   // nothing to stop; the recording is not ours to kill
        XCTAssertEqual(ResourceGuard.pressureAction(hasJob:true,stopsOnPressure:false,recording:false,alreadyStopped:false),.none)
        XCTAssertEqual(ResourceGuard.pressureAction(hasJob:true,stopsOnPressure:true,recording:false,alreadyStopped:true),.none)   // one message per job
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
