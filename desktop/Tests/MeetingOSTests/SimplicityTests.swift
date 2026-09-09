import XCTest
@testable import MeetingOS

/// Sprint C · yalınlık: the pure decisions behind the trimmed sidebar, the three-section Ayarlar and the
/// task filter that no longer moves on its own.
final class SidebarTitleTests:XCTestCase {
    func testTimestampTitleIsRecognised() {
        XCTAssertTrue(SidebarTitle.isTimestamp("9 Eyl 2026 14:05"))
        XCTAssertTrue(SidebarTitle.isTimestamp("12 Ara 2025 09:30"))
        XCTAssertTrue(SidebarTitle.isTimestamp("1 Oca. 2026 8:05"))
    }
    func testOlderEnglishDefaultTitlesAreRecognised() {
        XCTAssertTrue(SidebarTitle.isTimestamp("Sep 9, 2026 at 4:45 AM"))
        XCTAssertTrue(SidebarTitle.isTimestamp("December 12, 2025 at 9:30 PM"))
        XCTAssertTrue(SidebarTitle.isTimestamp("Sep 9, 2026 at 16:45"))
        XCTAssertTrue(SidebarTitle.isTimestamp("Sep 9, 2026 at 4:45\u{202F}AM"))   // narrow no-break space
        XCTAssertEqual(SidebarTitle.mode(recording:false,busy:false,selectedTitle:"Sep 9, 2026 at 4:45 AM"),.rename)
    }
    func testEnglishSoundingTitlesAreStillTitles() {
        XCTAssertFalse(SidebarTitle.isTimestamp("Sync with Bob at 3:00 PM"))
        XCTAssertFalse(SidebarTitle.isTimestamp("Sep 9, 2026"))
        XCTAssertFalse(SidebarTitle.isTimestamp("Sep 9, 2026 at 4:45:30 AM"))
        XCTAssertFalse(SidebarTitle.isTimestamp("Standup Sep 9, 2026 at 4:45 AM"))
    }
    func testRealTitlesAreNotTimestamps() {
        XCTAssertFalse(SidebarTitle.isTimestamp("Sprint planlama"))
        XCTAssertFalse(SidebarTitle.isTimestamp(""))
        XCTAssertFalse(SidebarTitle.isTimestamp("9 Eyl 2026"))
        XCTAssertFalse(SidebarTitle.isTimestamp("Ekip 9 Eyl 2026 14:05"))
        XCTAssertFalse(SidebarTitle.isTimestamp("9 Eyl 2026 14:05:30"))
    }
    func testFieldSeedsTheNextRecordingWhenNothingIsSelected() {
        XCTAssertEqual(SidebarTitle.mode(recording:false,busy:false,selectedTitle:nil),.seed)
    }
    func testFieldRenamesAnUnnamedMeeting() {
        XCTAssertEqual(SidebarTitle.mode(recording:false,busy:false,selectedTitle:"9 Eyl 2026 14:05"),.rename)
    }
    func testFieldHidesWhereItCannotHelp() {
        XCTAssertEqual(SidebarTitle.mode(recording:false,busy:false,selectedTitle:"Sprint planlama"),.hidden)
        XCTAssertEqual(SidebarTitle.mode(recording:true,busy:false,selectedTitle:nil),.hidden)
        XCTAssertEqual(SidebarTitle.mode(recording:false,busy:true,selectedTitle:"9 Eyl 2026 14:05"),.hidden)
    }
}

final class SettingsSectionsTests:XCTestCase {
    func testTheThreeSectionsPassThrough() {
        for s in SettingsSections.all { XCTAssertEqual(SettingsSections.normalize(s),s) }
    }
    func testOldFiveWayChoiceStillOpensASection() {
        XCTAssertEqual(SettingsSections.normalize("sozluk"),"sesler")
        XCTAssertEqual(SettingsSections.normalize("depolama"),"sistem")
        XCTAssertEqual(SettingsSections.normalize("guncelleme"),"sistem")
        XCTAssertEqual(SettingsSections.normalize("durum"),"sistem")
        XCTAssertEqual(SettingsSections.normalize("bilinmeyen"),"genel")
    }
    func testEverySectionHasItsOwnHeight() {
        XCTAssertEqual(SettingsSections.height("genel"),540)
        XCTAssertEqual(SettingsSections.height("sozluk"),SettingsSections.height("sesler"))
        XCTAssertEqual(SettingsSections.height("durum"),SettingsSections.height("sistem"))
    }
}

final class ActionsFilterTests:XCTestCase {
    func testDefaultsToMineAndRejectsJunk() {
        XCTAssertEqual(ActionsFilter.normalize("mine"),"mine")
        XCTAssertEqual(ActionsFilter.normalize("meeting"),"meeting")
        XCTAssertEqual(ActionsFilter.normalize("all"),"all")
        XCTAssertEqual(ActionsFilter.normalize(""),"mine")
        XCTAssertEqual(ActionsFilter.normalize("owner"),"mine")
    }
    func testEmptyMineWithMeetingTasksExplainsAndOffersTheSwitch() {
        XCTAssertTrue(ActionsFilter.offersMeetingSwitch(filter:"mine",meetingOpen:3))
        XCTAssertTrue(ActionsFilter.emptyMessage(filter:"mine",meetingOpen:3).contains("3 açık görev"))
    }
    func testNoSwitchWhenTheMeetingHasNothingEither() {
        XCTAssertFalse(ActionsFilter.offersMeetingSwitch(filter:"mine",meetingOpen:0))
        XCTAssertFalse(ActionsFilter.offersMeetingSwitch(filter:"all",meetingOpen:3))
        XCTAssertTrue(ActionsFilter.emptyMessage(filter:"mine",meetingOpen:0).contains("Tüm görevler"))
    }
}

final class UpdateSidebarLineTests:XCTestCase {
    func line(_ v:String,_ d:[String:Any]?)->String { UpdateInfo.sidebarLine(version:v,info:d.map(UpdateInfo.parse)) }
    func testOneLineWhenCurrent() {
        XCTAssertEqual(line("1.2.27",["available":false,"local":"abc1234"]),"Sürüm 1.2.27 · güncel")
    }
    func testNotCheckedYet() {
        XCTAssertEqual(line("1.2.27",nil),"Sürüm 1.2.27 · kontrol edilmedi")
    }
    func testErrorAndDirtyAndAvailable() {
        XCTAssertEqual(line("1.2.27",["available":false,"error":"GitHub’a ulaşılamadı"]),"Sürüm 1.2.27 · GitHub’a ulaşılamadı")
        XCTAssertEqual(line("1.2.27",["available":false,"dirty":true]),"Sürüm 1.2.27 · yerel değişiklik var")
        XCTAssertEqual(line("1.2.27",["available":true,"behind":3]),"Sürüm 1.2.27 · yeni sürüm hazır")
    }
    func testDebugBuildFallsBackToTheGitHash() {
        XCTAssertEqual(line("",["available":false,"local":"abc1234"]),"Sürüm abc1234 · güncel")
        XCTAssertEqual(line("",nil),"Sürüm · kontrol edilmedi")
    }
}
