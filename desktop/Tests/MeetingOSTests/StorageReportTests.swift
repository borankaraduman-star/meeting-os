import XCTest
@testable import MeetingOS
final class StorageReportTests:XCTestCase {
    func testParsesTotalsAndRanksLargestMeetings() {
        let report=StorageReport.parse(["totals":["recordings":1_800_000_000,"imports":50_000_000,"database":2_000_000],
            "meetings":[["meeting":"a","title":"Küçük","bytes":10,"active":false],["meeting":"b","title":"Büyük","bytes":900,"active":true],["meeting":"","bytes":5],["meeting":"c","title":"Orta","bytes":100]]])
        XCTAssertEqual(report.total,1_852_000_000)
        XCTAssertEqual(report.meetings.count,3)
        XCTAssertEqual(report.largest(2).map(\.meeting),["b","c"])
        XCTAssertEqual(report.largest(5).map(\.meeting),["b","c","a"])
        XCTAssertTrue(report.largest(1)[0].active)
        XCTAssertEqual(StorageReport.parse([:]).total,0)
    }
    func testFormatsDecimalUnitsWithTurkishComma() {
        XCTAssertEqual(StorageReport.format(bytes:1_800_000_000),"1,8 GB")
        XCTAssertEqual(StorageReport.format(bytes:340_000_000),"340 MB")
        XCTAssertEqual(StorageReport.format(bytes:12_600_000),"13 MB")
        XCTAssertEqual(StorageReport.format(bytes:400_000),"0,4 MB")
        XCTAssertEqual(StorageReport.format(bytes:0),"0,0 MB")
    }
}
