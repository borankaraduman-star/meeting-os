import XCTest
@testable import MeetingOS
final class StorageReportTests:XCTestCase {
    func testParsesTotalsAndRanksLargestMeetings() {
        let report=StorageReport.parse(["totals":["recordings":1_800_000_000,"imports":50_000_000,"database":2_000_000],
            "meetings":[["meeting":"a","title":"Küçük","bytes":10,"active":false],["meeting":"b","title":"Büyük","bytes":900,"active":true],["meeting":"","bytes":5],["meeting":"c","title":"Orta","bytes":100]]])
        XCTAssertEqual(report.total,1_852_000_000)
        XCTAssertEqual(report.audio,1_850_000_000)
        XCTAssertEqual(report.teamCache,0);XCTAssertEqual(report.logs,0)   // an older bridge sends neither; the card still adds up
        XCTAssertEqual(report.meetings.count,3)
        XCTAssertEqual(report.largest(2).map(\.meeting),["b","c"])
        XCTAssertEqual(report.largest(5).map(\.meeting),["b","c","a"])
        XCTAssertTrue(report.largest(1)[0].active)
        XCTAssertEqual(StorageReport.parse([:]).total,0)
    }
    /// Codex P2 #11: the team mirror and the journals are disk the user can free, so "Toplam" has to count them.
    func testTotalCountsTheTeamCacheAndTheLogs() {
        let report=StorageReport.parse(["totals":["recordings":100,"imports":50,"database":10,"team_cache_bytes":5_000,"logs_bytes":385],
                                        "text_retention_warning":["meetings":2,"line":"2 toplantının yazısı yarın tümüyle silinecek (30 gün)"]])
        XCTAssertEqual(report.teamCache,5_000);XCTAssertEqual(report.logs,385)
        XCTAssertEqual(report.audio,150);XCTAssertEqual(report.total,5_545)
        XCTAssertEqual(report.textRetentionWarning,"2 toplantının yazısı yarın tümüyle silinecek (30 gün)")
        XCTAssertNil(StorageReport.parse(["totals":["recordings":100]]).textRetentionWarning)   // the setting is off: no line
    }
    func testFormatsDecimalUnitsWithTurkishComma() {
        XCTAssertEqual(StorageReport.format(bytes:1_800_000_000),"1,8 GB")
        XCTAssertEqual(StorageReport.format(bytes:340_000_000),"340 MB")
        XCTAssertEqual(StorageReport.format(bytes:12_600_000),"13 MB")
        XCTAssertEqual(StorageReport.format(bytes:400_000),"0,4 MB")
        XCTAssertEqual(StorageReport.format(bytes:0),"0,0 MB")
    }
}
