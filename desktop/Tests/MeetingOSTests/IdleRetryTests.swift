import XCTest
@testable import MeetingOS

final class IdleRetryTests: XCTestCase {
    let now=Date(timeIntervalSince1970:1_757_000_000)

    func testQueueOnlyRunsWhenTheMacIsTheUsersToLend() {
        func ask(enabled:Bool=true,recording:Bool=false,hasJob:Bool=false,queued:Bool=false,zoomOpen:Bool=false,pressureAt:Date?=nil,last:Date?=nil)->Bool {
            IdleRetry.shouldAsk(enabled:enabled,recording:recording,hasJob:hasJob,queued:queued,zoomOpen:zoomOpen,pressureAt:pressureAt,last:last,now:now)
        }
        XCTAssertTrue(ask())                                            // idle and never asked before
        XCTAssertFalse(ask(enabled:false))                              // the user turned it off
        XCTAssertFalse(ask(recording:true))
        XCTAssertFalse(ask(hasJob:true))
        XCTAssertFalse(ask(queued:true))
        XCTAssertFalse(ask(zoomOpen:true))                              // a meeting is on screen (or being shared)
        XCTAssertFalse(ask(pressureAt:now.addingTimeInterval(-60)))     // memory pressure a minute ago
        XCTAssertTrue(ask(pressureAt:now.addingTimeInterval(-600)))     // ten minutes ago: clear again
        XCTAssertFalse(ask(last:now.addingTimeInterval(-599)))          // asked 9 min 59 s ago
        XCTAssertTrue(ask(last:now.addingTimeInterval(-600)))
    }

    func testBlockedHintNamesTheFixAndStaysQuiet() {
        XCTAssertNil(IdleRetry.blockedHint([]))
        XCTAssertEqual(IdleRetry.blockedHint([["kind":"credit"]]),"OpenRouter kredisi bitti · 1 toplantı bekliyor · Ayarlar → Sistem → OpenRouter anahtarı")
        XCTAssertEqual(IdleRetry.blockedHint([["kind":"auth"],["kind":"auth"]]),"OpenRouter anahtarı geçersiz · 2 toplantı bekliyor · Ayarlar → Sistem → OpenRouter anahtarı")
        XCTAssertEqual(IdleRetry.blockedHint([["kind":"auth"],["kind":"credit"]])?.hasPrefix("OpenRouter anahtarı veya kredisi"),true)
        XCTAssertFalse(IdleRetry.shouldNotifyBlocked(count:0,last:nil,now:now))
        XCTAssertTrue(IdleRetry.shouldNotifyBlocked(count:2,last:nil,now:now))
        XCTAssertFalse(IdleRetry.shouldNotifyBlocked(count:2,last:now.addingTimeInterval(-3600),now:now))   // one notice a day
        XCTAssertTrue(IdleRetry.shouldNotifyBlocked(count:2,last:now.addingTimeInterval(-24*3600),now:now))
    }

    func testIdleJobRunsAtBackgroundPriorityWithOneUploader() {
        let args=["openrouter-finalize","m1"]
        XCTAssertEqual(JobPriority.qos(args:args,zoomOpen:false),.utility)
        XCTAssertEqual(JobPriority.qos(args:args,zoomOpen:false,idle:true),.background)
        XCTAssertEqual(JobPriority.environment(args:args,zoomOpen:false,idle:true),["MEETING_OS_LOW_PRIORITY":"1"])
        XCTAssertEqual(JobPriority.environment(args:args,zoomOpen:false),[:])
        XCTAssertEqual(JobPriority.qos(args:["record","dir"],zoomOpen:false,idle:true),.userInitiated)   // recording is never demoted
    }

    func testCloudLineReplacesTheGenericStatusInTheSidebar() {
        let blocked=Meeting(["id":"m1","title":"Toplantı","status":"incomplete","display_status":"incomplete","cloud_line":"Kredi bitti"])
        XCTAssertEqual(blocked.sidebarDetail,"Kredi bitti")
        let plain=Meeting(["id":"m2","title":"Toplantı","status":"incomplete","display_status":"incomplete"])
        XCTAssertEqual(plain.sidebarDetail,statusLabel("incomplete"))
        XCTAssertNotEqual(blocked.fingerprint,Meeting(["id":"m1","title":"Toplantı","status":"incomplete","display_status":"incomplete"]).fingerprint)
        XCTAssertEqual(Meeting(["id":"m3","cloud_kind":"auth"]).cloudKind,"auth")
        XCTAssertNil(plain.cloudKind)
    }
}
