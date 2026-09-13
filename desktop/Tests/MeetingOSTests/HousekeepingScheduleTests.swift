import XCTest
@testable import MeetingOS

/// Finding #10. The sweep's "last run" used to be an in-memory var, nil at every launch, so the heaviest pass
/// in the product was armed on the first poll of every run. The schedule is now a persisted stamp and this
/// arithmetic; the notes are what the app finally says when a step of that sweep keeps failing.
final class HousekeepingScheduleTests:XCTestCase {
    let now=Date()
    func testNeverRunIsDue() {
        XCTAssertTrue(HousekeepingSchedule.isDue(last:nil,now:now))
    }
    func testARunTenMinutesAgoIsNotDue() {
        XCTAssertFalse(HousekeepingSchedule.isDue(last:now.addingTimeInterval(-600),now:now))
    }
    func testARunSixtyOneMinutesAgoIsDueAgain() {
        XCTAssertTrue(HousekeepingSchedule.isDue(last:now.addingTimeInterval(-61*60),now:now))
        XCTAssertTrue(HousekeepingSchedule.isDue(last:now.addingTimeInterval(-3600),now:now))   // exactly the interval counts
    }
    /// A restart is the whole point: the stamp survives it, so the second launch of the morning sweeps nothing.
    func testARestartDoesNotReArmTheSweep() {
        let last=now.addingTimeInterval(-5*60)
        XCTAssertFalse(HousekeepingSchedule.isDue(last:last,now:now))
        XCTAssertTrue(HousekeepingSchedule.isDue(last:last,now:now.addingTimeInterval(3600)))
    }
    /// A clock that jumped backwards must not lock the sweep out until the wall clock catches up.
    func testAStampInTheFutureIsTreatedAsBroken() {
        XCTAssertTrue(HousekeepingSchedule.isDue(last:now.addingTimeInterval(900),now:now))
    }

    func testASilentPassSaysNothing() {
        XCTAssertNil(HousekeepingSchedule.note(failures:[:],skipped:[],streaks:[:]))
    }
    func testARepeatedTeamSyncFailureIsCounted() {
        var streaks=HousekeepingSchedule.streaks(previous:[:],failures:["team":"klasör bulunamadı"])
        XCTAssertEqual(streaks["team"],1)
        XCTAssertEqual(HousekeepingSchedule.note(failures:["team":"x"],skipped:[],streaks:streaks),"Bakım: ekip eşitleme başarısız oldu")
        streaks=HousekeepingSchedule.streaks(previous:streaks,failures:["team":"x"])
        streaks=HousekeepingSchedule.streaks(previous:streaks,failures:["team":"x"])
        XCTAssertEqual(streaks["team"],3)
        XCTAssertEqual(HousekeepingSchedule.note(failures:["team":"x"],skipped:[],streaks:streaks),"Bakım: ekip eşitleme 3 kez üst üste başarısız oldu")
    }
    /// "Consecutive" has to mean consecutive: a pass where the step worked clears its count.
    func testARecoveredStepLosesItsCount() {
        let previous=["team":4,"archive":1]
        let next=HousekeepingSchedule.streaks(previous:previous,failures:["archive":"disk dolu"])
        XCTAssertNil(next["team"]); XCTAssertEqual(next["archive"],2)
    }
    func testTheOldestFailureLeadsAndTheRestAreCounted() {
        let line=HousekeepingSchedule.note(failures:["team":"x","archive":"y"],skipped:[],streaks:["team":3,"archive":1])
        XCTAssertEqual(line,"Bakım: ekip eşitleme 3 kez üst üste başarısız oldu · 1 adım daha")
    }
    func testSkippedStepsAreReportedWhenNothingFailed() {
        XCTAssertEqual(HousekeepingSchedule.note(failures:[:],skipped:["calibration"],streaks:[:]),"Bakım: kalibrasyon atlandı")
        XCTAssertEqual(HousekeepingSchedule.note(failures:[:],skipped:["calibration","experiments"],streaks:[:]),"Bakım: kalibrasyon atlandı · 1 adım daha")
    }
    /// The Python side gains these keys separately: an older bridge reports neither and must read as healthy.
    func testAnOlderBridgeReadsAsNothingFailed() {
        let (failures,skipped)=HousekeepingSchedule.outcome(["archived_bytes":12])
        XCTAssertTrue(failures.isEmpty); XCTAssertTrue(skipped.isEmpty)
        XCTAssertNil(HousekeepingSchedule.note(failures:failures,skipped:skipped,streaks:[:]))
    }
    func testBothKeysAreReadWhenTheyArrive() {
        let (failures,skipped)=HousekeepingSchedule.outcome(["failures":["team":"izin yok"],"skipped":["experiments"]])
        XCTAssertEqual(failures["team"],"izin yok"); XCTAssertEqual(skipped,["experiments"])
    }
    /// A step this Swift version has never heard of still has to reach the user, under its own name.
    func testAnUnknownStepKeepsItsKey() {
        XCTAssertEqual(HousekeepingSchedule.note(failures:["new_step":"x"],skipped:[],streaks:["new_step":1]),"Bakım: new_step başarısız oldu")
    }
}
