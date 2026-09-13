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

/// The bundle update channel (docs/BUNDLE.md). The same two bridge actions carry it — the Python side picks
/// the channel — so what Swift owns is: telling the bridge WHICH bundle to replace and which pid to wait for,
/// and turning the extra `update-status.json` states into one line of Turkish.
final class BundleUpdateTests:XCTestCase {
    override func tearDown() { BundleInfo.override=nil; super.tearDown() }

    func testAGitCheckoutSendsNoAppPathOrPid() {
        BundleInfo.override=[:]
        XCTAssertFalse(BundleInfo.bundled)
        let r=BundleInfo.updateStartRequest()
        XCTAssertEqual(r["action"] as? String,"update_start")
        XCTAssertNil(r["app_path"]); XCTAssertNil(r["pid"])
    }
    func testABundleSendsTheRunningAppPathAndThisProcessesPid() {
        BundleInfo.override=["bundled":true,"version":"1.2.72"]
        XCTAssertTrue(BundleInfo.bundled)
        let r=BundleInfo.updateStartRequest(appPath:"/Applications/Meeting OS.app",pid:4242)
        XCTAssertEqual(r["app_path"] as? String,"/Applications/Meeting OS.app")
        XCTAssertEqual(r["pid"] as? Int,4242)
        // and by default they are this app's own two answers, never a hard-coded /Applications
        let live=BundleInfo.updateStartRequest()
        XCTAssertEqual(live["app_path"] as? String,Bundle.main.bundleURL.path)
        XCTAssertEqual(live["pid"] as? Int,Int(ProcessInfo.processInfo.processIdentifier))
    }
    func testARuntimeJsonWithoutTheFlagIsNotABundle() {
        BundleInfo.override=["python":"runtime/bin/python3","repo":"repo"]
        XCTAssertFalse(BundleInfo.bundled)
        XCTAssertNil(BundleInfo.updateStartRequest()["pid"])
    }

    func testTheDownloadPercentageIsShown() {
        XCTAssertEqual(UpdateStatusLine.line(state:"downloading",message:"Yeni sürüm indiriliyor · %3",time:"",percent:42),
                       "Yeni sürüm indiriliyor · %42")
        // a caller that does not read the percent key still gets the worker's own sentence
        XCTAssertEqual(UpdateStatusLine.line(state:"downloading",message:"Yeni sürüm indiriliyor · %3",time:""),
                       "Yeni sürüm indiriliyor · %3")
        XCTAssertEqual(UpdateStatusLine.line(state:"downloading",message:"",time:""),UpdateStatusLine.downloadingPrefix)
    }
    func testTheOtherBundleStatesEachSayOneThing() {
        XCTAssertEqual(UpdateStatusLine.line(state:"verifying",message:"",time:""),"Paket doğrulanıyor")
        XCTAssertEqual(UpdateStatusLine.line(state:"extracting",message:"",time:""),"Paket açılıyor")
        XCTAssertEqual(UpdateStatusLine.line(state:"swapping",message:"",time:""),UpdateStatusLine.swappingMessage)
    }
    func testAFailedDownloadReadsLikeEveryOtherFailure() {
        XCTAssertEqual(UpdateStatusLine.line(state:"failed",message:"İndirilen paket doğrulanamadı (sha256); yeniden deneyin",time:""),
                       "Güncelleme başarısız · İndirilen paket doğrulanamadı (sha256); yeniden deneyin")
    }
    func testOnlySwappingAsksTheAppToQuit() {
        XCTAssertTrue(UpdateStatusLine.shouldQuit(state:"swapping"))
        for state in ["downloading","verifying","extracting","done","failed","running",""] {
            XCTAssertFalse(UpdateStatusLine.shouldQuit(state:state),state)
        }
    }
    /// The git channel's own states must read exactly as they did before the second channel existed.
    func testTheGitChannelIsUnchanged() {
        XCTAssertEqual(UpdateStatusLine.line(state:"done",message:"Güncellendi: a → b",time:""),"Güncelleme tamam · Güncellendi: a → b")
        XCTAssertNil(UpdateStatusLine.line(state:"kim bilir",message:"x",time:""))
    }

    /// The bundle channel's check answers the same dict shape, so the sidebar and the card keep one reader.
    func testABundleReleaseReadsLikeAGitRelease() {
        let u=UpdateInfo.parse(["available":true,"behind":1,"subjects":["Tek parça uygulama paketi"],
                                "local":"1.2.71","remote":"1.2.72","target":"1.2.72","bundled":true])
        XCTAssertTrue(u.canUpdate)
        XCTAssertEqual(u.headline,"Yeni sürüm hazır · 1 değişiklik · Tek parça uygulama paketi")
        XCTAssertEqual(UpdateInfo.sidebarLine(version:"1.2.71",info:u),"Sürüm 1.2.71 · yeni sürüm hazır")
    }
    func testABundleWithoutADownloadSecretSaysSoInsteadOfSayingUpToDate() {
        let u=UpdateInfo.parse(["available":false,"behind":0,"local":"1.2.72",
                                "error":"Güncelleme adresi bu pakette yok · Boran’a bildirin"])
        XCTAssertFalse(u.canUpdate)
        XCTAssertEqual(u.headline,"Güncelleme adresi bu pakette yok · Boran’a bildirin")
    }
}

/// Finding #12: a detached download worker that dies (logout, OOM, sleep) leaves `update-status.json` frozen
/// at `downloading`. The card said "%37" for the rest of the day, `updating` stayed true and the button could
/// never be pressed again. Every bundle state now has a budget for how long its `time` may stand still.
final class UpdateStallTests:XCTestCase {
    func stamp(_ minutesAgo:Double,now:Date)->String {
        let f=DateFormatter(); f.dateFormat="yyyy-MM-dd HH:mm:ss"; f.locale=Locale(identifier:"en_US_POSIX"); f.timeZone=TimeZone.current
        return f.string(from:now.addingTimeInterval(-minutesAgo*60))
    }
    func testAMovingDownloadIsNeverCalledDead() {
        let now=Date()
        XCTAssertFalse(UpdateStatusLine.isStalled(state:"downloading",time:stamp(1,now:now),now:now))
        XCTAssertEqual(UpdateStatusLine.line(state:"downloading",message:"",time:stamp(1,now:now),percent:37,now:now),"Yeni sürüm indiriliyor · %37")
    }
    func testADownloadThatStoppedWritingIsStalled() {
        let now=Date()
        XCTAssertTrue(UpdateStatusLine.isStalled(state:"downloading",time:stamp(6,now:now),now:now))
        XCTAssertEqual(UpdateStatusLine.line(state:"downloading",message:"",time:stamp(6,now:now),percent:37,now:now),UpdateStatusLine.bundleStalledMessage)
    }
    func testVerifyingGetsTheSameShortBudget() {
        let now=Date()
        XCTAssertFalse(UpdateStatusLine.isStalled(state:"verifying",time:stamp(4,now:now),now:now))
        XCTAssertTrue(UpdateStatusLine.isStalled(state:"verifying",time:stamp(6,now:now),now:now))
    }
    /// Extracting and swapping write the status once and then work through ~1 GB in silence: five minutes of
    /// quiet is normal there, and cancelling on it would abandon an update that is going fine.
    func testExtractingAndSwappingGetTheLongerBudget() {
        let now=Date()
        for state in ["extracting","swapping"] {
            XCTAssertFalse(UpdateStatusLine.isStalled(state:state,time:stamp(10,now:now),now:now),state)
            XCTAssertTrue(UpdateStatusLine.isStalled(state:state,time:stamp(16,now:now),now:now),state)
        }
        XCTAssertEqual(UpdateStatusLine.line(state:"swapping",message:"",time:stamp(16,now:now),now:now),UpdateStatusLine.bundleStalledMessage)
    }
    /// Finished states cannot go stale, and `running` keeps the git channel's own half-hour sentence.
    func testFinalStatesHaveNoBudgetAndRunningKeepsItsOwn() {
        let now=Date()
        for state in ["done","failed","refused","kim bilir"] {
            XCTAssertNil(UpdateStatusLine.stallBudget(state:state),state)
            XCTAssertFalse(UpdateStatusLine.isStalled(state:state,time:stamp(600,now:now),now:now),state)
        }
        XCTAssertEqual(UpdateStatusLine.stallBudget(state:"running"),UpdateStatusLine.stallSeconds)
        XCTAssertEqual(UpdateStatusLine.line(state:"running",message:"x",time:stamp(31,now:now),now:now),UpdateStatusLine.stalledMessage)
    }
    /// An unwritten or unreadable timestamp is "cannot tell", not "dead": the poll loop's own deadline covers
    /// that case rather than this one cancelling a healthy update.
    func testAnUnreadableTimestampIsNotAStall() {
        XCTAssertFalse(UpdateStatusLine.isStalled(state:"downloading",time:"",now:Date()))
        XCTAssertFalse(UpdateStatusLine.isStalled(state:"downloading",time:"10 Eyl 2026",now:Date()))
        XCTAssertGreaterThan(UpdateStatusLine.pollDeadline,UpdateStatusLine.heavyStallSeconds)
    }
    func testTheStalledLineTellsTheUserTheButtonWorksAgain() {
        XCTAssertEqual(UpdateStatusLine.bundleStalledMessage,"Güncelleme yanıt vermiyor · yeniden deneyin")
    }
}
