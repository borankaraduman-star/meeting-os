import XCTest
@testable import MeetingOS
final class ErrorPresentationTests: XCTestCase {
    func testRepeatedErrorIsBoundedAndExplainsWhereDetailsAre() {
        let text=String(repeating:"Mac bellek baskısı altında; ",count:1000)
        let result=ErrorPresentation.summary(text)
        XCTAssertLessThanOrEqual(result.count,400)
        XCTAssertTrue(result.contains("bellek baskısı"))
        XCTAssertTrue(result.contains("last-job.log"))
    }
    func testShortErrorIsPreserved() {
        XCTAssertEqual(ErrorPresentation.summary("İzin reddedildi"),"İzin reddedildi")
    }
    func testHugeLogTailIsBoundedAndUnicodeSafe() throws {
        let url=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:url) }
        try ("old line\n"+String(repeating:"ğ",count:100_000)+"\n").write(to:url,atomically:true,encoding:.utf8)
        let result=ErrorPresentation.logSummary(url)
        XCTAssertLessThanOrEqual(result.count,400)
        XCTAssertFalse(result.isEmpty)
    }
}
