import XCTest
@testable import MeetingOS

final class JobLifecycleTests:XCTestCase {
    func testStartingARecordingDoesNotResetCancellationOfThePreviousJob() {
        let slots=JobLifecycles()
        let finalize=slots.begin(recording:false)
        finalize.canceled=true
        let recorder=slots.begin(recording:true)
        XCTAssertTrue(slots.job === finalize)
        XCTAssertFalse(finalize.completion(exitStatus:2,log:"interrupted").succeeded)
        XCTAssertNil(finalize.completion(exitStatus:2,log:"interrupted").failure)
        XCTAssertTrue(recorder.completion(exitStatus:0,log:"").succeeded)
    }

    func testCancelingThePreviousJobCannotHideARecorderFailure() {
        let slots=JobLifecycles()
        let finalize=slots.begin(recording:false)
        let recorder=slots.begin(recording:true)
        finalize.canceled=true
        XCTAssertEqual(recorder.completion(exitStatus:1,log:"microphone unavailable").failure,"microphone unavailable")
    }

    func testResourceFailureBelongsOnlyToTheJobThatWasStopped() {
        let slots=JobLifecycles()
        let finalize=slots.begin(recording:false)
        finalize.resourceFailure="memory pressure"
        let recorder=slots.begin(recording:true)
        XCTAssertTrue(recorder.completion(exitStatus:0,log:"").succeeded)
        XCTAssertEqual(recorder.completion(exitStatus:1,log:"capture failed").failure,"capture failed")
        XCTAssertEqual(finalize.completion(exitStatus:15,log:"terminated").failure,"memory pressure")
    }

    func testAReplacementJobCannotChangeTheFinishedJobsVerdict() {
        let slots=JobLifecycles()
        let earlier=slots.begin(recording:false)
        earlier.canceled=true
        slots.finish(earlier)
        let next=slots.begin(recording:false)
        slots.finish(earlier)
        XCTAssertTrue(slots.job === next)
        XCTAssertNil(earlier.completion(exitStatus:2,log:"interrupted").failure)
        XCTAssertTrue(next.completion(exitStatus:0,log:"").succeeded)
    }
}
