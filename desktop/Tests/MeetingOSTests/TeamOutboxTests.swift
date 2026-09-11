import XCTest
@testable import MeetingOS

/// The durable half of "the team gets it" (Codex, 10 Sep 2026, P1 #8): when the app's single background loop
/// is allowed to spend a slow-bridge call, and what the setup card says while a pass is still owed.
final class TeamOutboxTests: XCTestCase {
    let now=Date(timeIntervalSince1970:1_757_600_000)

    func testNothingOwedMeansNoCallAtAll() {
        XCTAssertFalse(TeamOutbox.shouldFlush(now:now,dirtySince:nil,lastAttempt:nil,recording:false))
        XCTAssertFalse(TeamOutbox.shouldFlush(now:now,dirtySince:nil,lastAttempt:now.addingTimeInterval(-3600),recording:false))
    }

    /// Naming four voices in a row is four changes in twenty seconds; the loop waits for the flurry to end.
    func testAChangeSettlesBeforeItTravels() {
        XCTAssertFalse(TeamOutbox.shouldFlush(now:now,dirtySince:now.addingTimeInterval(-5),lastAttempt:nil,recording:false))
        XCTAssertFalse(TeamOutbox.shouldFlush(now:now,dirtySince:now.addingTimeInterval(-19),lastAttempt:nil,recording:false))
        XCTAssertTrue(TeamOutbox.shouldFlush(now:now,dirtySince:now.addingTimeInterval(-TeamOutbox.settle),lastAttempt:nil,recording:false))
    }

    /// Still pending after a flush (the server was down): five minutes, not two seconds.
    func testAPendingOutboxRetriesOnItsOwnBeat() {
        let dirty=now.addingTimeInterval(-3600)
        XCTAssertFalse(TeamOutbox.shouldFlush(now:now,dirtySince:dirty,lastAttempt:now.addingTimeInterval(-60),recording:false))
        XCTAssertFalse(TeamOutbox.shouldFlush(now:now,dirtySince:dirty,lastAttempt:now.addingTimeInterval(-299),recording:false))
        XCTAssertTrue(TeamOutbox.shouldFlush(now:now,dirtySince:dirty,lastAttempt:now.addingTimeInterval(-TeamOutbox.retry),recording:false))
    }

    /// The one thing that outranks the team is the meeting the user is in.
    func testARecordingStopsEverything() {
        XCTAssertFalse(TeamOutbox.shouldFlush(now:now,dirtySince:now.addingTimeInterval(-3600),lastAttempt:nil,recording:true))
        XCTAssertTrue(TeamOutbox.shouldFlush(now:now,dirtySince:now.addingTimeInterval(-3600),lastAttempt:nil,recording:false))
    }

    /// "son eşitleme 09:14 ✓" while a word taught at 12:34 is still on this Mac is a lie. Green means delivered.
    func testTheCardSaysWhatIsStillWaiting() {
        let waiting=SetupStatus.teamRootCheck(["team_root_kind":"cloud",
            "team_cloud":["last_ok":"2026-09-11T06:14:00+00:00","outbox_pending_since":"2026-09-11T09:34:00+00:00","hosts":["a","b"]]])
        XCTAssertEqual(waiting.state,.optional)
        XCTAssertTrue(waiting.hint.hasPrefix("ekip bulutu · 2 Mac · eşitleme bekliyor · "))
        XCTAssertTrue(waiting.hint.hasSuffix("’ten beri"))
        XCTAssertEqual(waiting.hint.count,"ekip bulutu · 2 Mac · eşitleme bekliyor · ".count+5+"’ten beri".count)
        // Delivered: the row goes green again and reads as a time, not as a wait.
        let clear=SetupStatus.teamRootCheck(["team_root_kind":"cloud","team_cloud":["last_ok":"2026-09-11T06:14:00+00:00","hosts":["a","b"]]])
        XCTAssertEqual(clear.state,.ok)
        XCTAssertTrue(clear.hint.hasPrefix("ekip bulutu · 2 Mac · son eşitleme "))
        // An outage still outranks a pending outbox: the reason the pass has not happened is the useful half.
        let down=SetupStatus.teamRootCheck(["team_root_kind":"cloud",
            "team_cloud":["last_error":"URLError: bağlanılamadı","outbox_pending_since":"2026-09-11T09:34:00+00:00","hosts":["a"]]])
        XCTAssertEqual(down.state,.optional)
        XCTAssertTrue(down.hint.hasPrefix("bulut şu an erişilemiyor (URLError: bağlanılamadı)"))
    }

    func testSyncDateParsesWhatPythonWrites() {
        XCTAssertNotNil(SetupStatus.syncDate("2026-09-11T09:34:00.512345+00:00"))   // microseconds and all
        XCTAssertNotNil(SetupStatus.syncDate("2026-09-11T09:34:00+00:00"))
        XCTAssertNil(SetupStatus.syncDate("bir zaman"))
    }
}
