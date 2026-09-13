import XCTest
@testable import MeetingOS

/// Finding #13. `stop()` sent one SIGINT and declared the recording over on the same line, so a wedged
/// supervisor left every stop control disabled, the second press a no-op, and Force Quit the only way out.
final class StopEscalationTests:XCTestCase {
    typealias Signal=StopEscalation.Signal

    func testTheFirstPressSendsSigint() {
        XCTAssertEqual(StopEscalation.next(elapsed:0,alive:true,sent:nil),.interrupt)
    }
    func testNothingMoreIsSentWhileTheChildIsStillDraining() {
        XCTAssertNil(StopEscalation.next(elapsed:2,alive:true,sent:.interrupt))
    }
    func testSigtermAfterFiveSecondsThenSigkillAfterTen() {
        XCTAssertEqual(StopEscalation.next(elapsed:5,alive:true,sent:.interrupt),.terminate)
        XCTAssertNil(StopEscalation.next(elapsed:7,alive:true,sent:.terminate))
        XCTAssertEqual(StopEscalation.next(elapsed:10,alive:true,sent:.terminate),.kill)
    }
    /// A child that ignored SIGINT for eleven seconds skips straight to the signal it cannot ignore.
    func testALateFirstTickDoesNotWalkTheLadderOneRungPerCheck() {
        XCTAssertEqual(StopEscalation.next(elapsed:11,alive:true,sent:.interrupt),.kill)
    }
    func testSigkillIsTheLastWord() {
        XCTAssertNil(StopEscalation.next(elapsed:60,alive:true,sent:.kill))
    }
    /// Signalling a pid that has already exited is how a reused pid gets killed instead.
    func testADeadChildIsNeverSignalled() {
        XCTAssertNil(StopEscalation.next(elapsed:0,alive:false,sent:nil))
        XCTAssertNil(StopEscalation.next(elapsed:30,alive:false,sent:.interrupt))
    }

    /// The UI may not say "not recording" while the helper is still writing audio: that was the bug that
    /// disabled the second press.
    func testTheRecordingEndsOnlyWhenTheChildIsGoneOrKilled() {
        XCTAssertFalse(StopEscalation.finished(alive:true,sent:nil))
        XCTAssertFalse(StopEscalation.finished(alive:true,sent:.interrupt))
        XCTAssertFalse(StopEscalation.finished(alive:true,sent:.terminate))
        XCTAssertTrue(StopEscalation.finished(alive:true,sent:.kill))      // the escalation is over; nothing else to wait for
        XCTAssertTrue(StopEscalation.finished(alive:false,sent:.interrupt))
        XCTAssertTrue(StopEscalation.finished(alive:false,sent:nil))
    }

    /// A second press has to do something. It brings the next rung forward instead of restarting the clock —
    /// restarting it would let an impatient user postpone the kill forever.
    func testASecondPressAdvancesTheClockInsteadOfRestartingIt() {
        XCTAssertEqual(StopEscalation.bringForward(sent:nil),0)
        XCTAssertEqual(StopEscalation.bringForward(sent:.interrupt),StopEscalation.termAfter)
        XCTAssertEqual(StopEscalation.bringForward(sent:.terminate),StopEscalation.killAfter)
        // Pressed again one second in, having sent SIGINT: the clock moves to five seconds, so the next check
        // sends SIGTERM rather than nothing.
        let elapsed=1+StopEscalation.bringForward(sent:.interrupt)
        XCTAssertEqual(StopEscalation.next(elapsed:elapsed,alive:true,sent:.interrupt),.terminate)
    }
    func testAThirdPressReachesSigkill() {
        let elapsed=StopEscalation.bringForward(sent:.terminate)
        XCTAssertEqual(StopEscalation.next(elapsed:elapsed,alive:true,sent:.terminate),.kill)
    }

    /// Both quit budgets are bounded: an eight-second deadline on `.terminateLater` (it had none), and a name
    /// save that happens a second after typing instead of on the main thread at quit.
    func testQuitBudgetsAreBounded() {
        XCTAssertGreaterThan(QuitSequence.deadlineSeconds,0)
        XCTAssertLessThanOrEqual(QuitSequence.deadlineSeconds,10)
        XCTAssertLessThan(QuitSequence.nameDebounceSeconds,QuitSequence.deadlineSeconds)
    }
    /// ⌘Q during a recording waits out the whole ladder: quitting at eight seconds would leave a helper that
    /// had just been sent SIGTERM running, with the app that was going to SIGKILL it gone.
    func testQuitWaitsOutTheEscalationWhenARecordingIsDraining() {
        XCTAssertEqual(QuitSequence.deadline(draining:false),QuitSequence.deadlineSeconds)
        XCTAssertGreaterThan(QuitSequence.deadline(draining:true),StopEscalation.killAfter)
        XCTAssertLessThanOrEqual(QuitSequence.deadline(draining:true),15)   // still bounded: ⌘Q always finishes
    }
}
