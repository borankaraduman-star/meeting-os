import XCTest
@testable import MeetingOS

final class RecordingContinuityTests: XCTestCase {
    func testNothingIsSaidWhileTheRecordingIsSimplyRunning() {
        let quiet=RecordingContinuity.read(["state":"capturing","seconds":1200.0])
        XCTAssertEqual(quiet,RecordingContinuity.State(capture:"capturing"))
        XCTAssertNil(RecordingContinuity.notice(from:quiet,to:quiet))
    }
    func testASurvivedInterruptionIsAnnouncedOnceWithTheSecondsItCost() {
        let before=RecordingContinuity.read(["state":"capturing"])
        let after=RecordingContinuity.read(["state":"capturing","relaunches":1,"wakes":1,"gap_seconds":2.5,"wake_gap_seconds":180.0])
        XCTAssertEqual(RecordingContinuity.notice(from:before,to:after),"Kayıt devam ediyor · 183 sn boşluk")
        XCTAssertNil(RecordingContinuity.notice(from:after,to:after))   // one line per event, not one per poll
        let rebuilt=RecordingContinuity.read(["state":"capturing","restarts":1])
        XCTAssertEqual(RecordingContinuity.notice(from:before,to:rebuilt),"Kayıt devam ediyor")
    }
    func testAnErrorOrAnExhaustedBudgetWithNothingWrittenReadsAsInterrupted() {
        let running=RecordingContinuity.read(["state":"capturing"])
        let failed=RecordingContinuity.read(["state":"error","relaunches":2])
        XCTAssertEqual(RecordingContinuity.notice(from:running,to:failed),"Kayıt kesildi · yeniden başlatılıyor")
        XCTAssertNil(RecordingContinuity.notice(from:failed,to:failed))
        // Out of relaunches and nothing written for over a minute: the supervisor has stopped trying.
        let spent=RecordingContinuity.read(["state":"capturing","relaunches":5,"last_event_age":90.0])
        XCTAssertTrue(RecordingContinuity.interrupted(spent))
        XCTAssertEqual(RecordingContinuity.notice(from:running,to:spent),"Kayıt kesildi · yeniden başlatılıyor")
        // Same budget, but chunks are still landing: a busy afternoon, not a dead recording.
        XCTAssertFalse(RecordingContinuity.interrupted(RecordingContinuity.read(["state":"capturing","relaunches":5,"last_event_age":4.0])))
        // Still trying: fewer relaunches than the budget is never called an interruption.
        XCTAssertFalse(RecordingContinuity.interrupted(RecordingContinuity.read(["state":"capturing","relaunches":4,"last_event_age":300.0])))
    }
    func testMalformedCaptureStateCannotProduceAbsurdNumbers() {
        let junk=RecordingContinuity.read(["state":42,"restarts":true,"relaunches":"iki","wakes":Double.nan,"gap_seconds":-5.0,"wake_gap_seconds":1e12,"last_event_age":Double.infinity])
        XCTAssertEqual(junk.capture,"")
        XCTAssertEqual([junk.restarts,junk.relaunches,junk.wakes],[0,0,0])
        XCTAssertEqual(junk.gapSeconds,86400)
        XCTAssertNil(junk.lastEventAge)
        XCTAssertNil(RecordingContinuity.notice(from:junk,to:junk))
    }
}
