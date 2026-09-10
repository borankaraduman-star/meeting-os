import XCTest
@testable import MeetingOS

/// P0-4: a Mac whose branch has drifted away from GitHub can never be fast-forwarded, so `update_check` reports
/// `diverged`. Before this, `UpdateInfo` dropped the flag on the floor and every screen said "güncel" forever
/// while the setup card said "N değişiklik geride" — two answers, neither of them the truth.
final class UpdateDivergenceTests:XCTestCase {
    func info(_ d:[String:Any])->UpdateInfo { UpdateInfo.parse(d) }

    func testDivergenceKeysAreParsed() {
        let u=info(["available":false,"behind":4,"diverged":true,"ahead":2,"hint":"Dal ayrıştı · 2 yerel işleme"])
        XCTAssertTrue(u.diverged); XCTAssertEqual(u.ahead,2); XCTAssertEqual(u.hint,"Dal ayrıştı · 2 yerel işleme")
        XCTAssertEqual(u.behind,4)
    }
    func testTheKeysDefaultToACleanBranchWhenTheBridgeIsOlder() {
        let u=info(["available":true,"behind":3])
        XCTAssertFalse(u.diverged); XCTAssertEqual(u.ahead,0); XCTAssertEqual(u.hint,"")
        XCTAssertTrue(u.canUpdate)
    }
    func testHeadlineSaysTheBranchDivergedInsteadOfUpToDate() {
        XCTAssertEqual(info(["available":false,"local":"abc1234","diverged":true]).headline,UpdateInfo.divergedMessage)
        XCTAssertEqual(info(["available":false,"local":"abc1234","diverged":false]).headline,"Güncel (abc1234)")
    }
    func testTheBridgeHintWinsOverTheStandardSentence() {
        XCTAssertEqual(info(["diverged":true,"ahead":2,"hint":"Depo elle değiştirilmiş"]).headline,"Depo elle değiştirilmiş")
        XCTAssertEqual(info(["diverged":true,"ahead":2]).headline,UpdateInfo.divergedMessage+" · 2 yerel değişiklik ileride")
        XCTAssertEqual(info(["diverged":true,"ahead":0]).headline,UpdateInfo.divergedMessage)
    }
    /// A divergence outranks a waiting release: the release is exactly what cannot be installed.
    func testDivergenceOutranksAnAvailableRelease() {
        let u=info(["available":true,"behind":3,"diverged":true])
        XCTAssertEqual(u.headline,UpdateInfo.divergedMessage)
        XCTAssertFalse(u.canUpdate)   // no "Güncelle ve yeniden başlat" button anywhere
    }
    func testAnErrorStillComesFirst() {
        XCTAssertEqual(info(["diverged":true,"error":"GitHub’a ulaşılamadı"]).headline,"GitHub’a ulaşılamadı")
    }
    func testSidebarLineAgreesWithTheHeadline() {
        let u=info(["available":false,"diverged":true,"ahead":2])
        XCTAssertEqual(UpdateInfo.sidebarLine(version:"1.2.44",info:u),"Sürüm 1.2.44 · "+u.headline)
        XCTAssertEqual(UpdateInfo.sidebarLine(version:"1.2.44",info:info(["available":false])),"Sürüm 1.2.44 · güncel")
    }
    func testDivergedNoticeIsEmptyOnACleanBranch() {
        XCTAssertEqual(info(["available":false]).divergedNotice,"")
    }
}

/// The "Son durum" line for `update-status.json`. A `running` state is the normal thing to find right after a
/// restart, but one left behind half an hour ago means the updater died between two steps.
final class UpdateStatusLineTests:XCTestCase {
    func stamp(_ minutesAgo:Double,now:Date)->String {
        let f=DateFormatter(); f.dateFormat="yyyy-MM-dd HH:mm:ss"; f.locale=Locale(identifier:"en_US_POSIX"); f.timeZone=TimeZone.current
        return f.string(from:now.addingTimeInterval(-minutesAgo*60))
    }
    func testDoneAndFailedAreReported() {
        let now=Date()
        XCTAssertEqual(UpdateStatusLine.line(state:"done",message:"Güncellendi: a → b",time:stamp(1,now:now),now:now),"Güncelleme tamam · Güncellendi: a → b")
        XCTAssertEqual(UpdateStatusLine.line(state:"failed",message:"Derleme başarısız",time:stamp(1,now:now),now:now),"Güncelleme başarısız · Derleme başarısız")
    }
    func testAFreshRunningStateSaysNothing() {
        let now=Date()
        XCTAssertNil(UpdateStatusLine.line(state:"running",message:"Uygulama derleniyor",time:stamp(5,now:now),now:now))
        XCTAssertNil(UpdateStatusLine.line(state:"running",message:"x",time:stamp(29,now:now),now:now))
    }
    func testARunningStateLeftBehindHalfAnHourIsAStalledUpdate() {
        let now=Date()
        XCTAssertEqual(UpdateStatusLine.line(state:"running",message:"Uygulama derleniyor",time:stamp(31,now:now),now:now),UpdateStatusLine.stalledMessage)
        XCTAssertEqual(UpdateStatusLine.line(state:"running",message:"x",time:stamp(600,now:now),now:now),UpdateStatusLine.stalledMessage)
    }
    func testAnUnreadableOrUnknownStateSaysNothing() {
        XCTAssertNil(UpdateStatusLine.line(state:"running",message:"x",time:"",now:Date()))
        XCTAssertNil(UpdateStatusLine.line(state:"kim bilir",message:"x",time:"",now:Date()))
    }
    func testTheScriptsOwnTimestampFormatParses() {
        XCTAssertNotNil(UpdateStatusLine.parseTime("2026-09-10 13:45:02"))
        XCTAssertNil(UpdateStatusLine.parseTime("10 Eyl 2026"))
    }
}
