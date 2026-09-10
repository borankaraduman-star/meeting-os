import XCTest
@testable import MeetingOS

/// The Özet page reads as bullets now: one compact line under the title, and the state that used to
/// take an extra row under every item is a chip.
final class SummaryUXTests:XCTestCase {
    func testStatsLineReadsAsOneSentence() {
        XCTAssertEqual(SummaryUX.statsLine(segments:335,openTasks:8,hasSummary:true,stale:false),"335 bölüm · 8 açık görev · özet hazır")
    }
    func testZeroCountsDropOutButTheSummaryStateStays() {
        XCTAssertEqual(SummaryUX.statsLine(segments:0,openTasks:0,hasSummary:false,stale:false),"özet bekliyor")
        XCTAssertEqual(SummaryUX.statsLine(segments:12,openTasks:0,hasSummary:true,stale:true),"12 bölüm · özet güncel değil")
    }
    func testAStaleSummarySaysSoEvenBeforeItIsRefreshed() {
        XCTAssertTrue(SummaryUX.statsLine(segments:4,openTasks:1,hasSummary:true,stale:true).hasSuffix("özet güncel değil"))
    }
    func testACleanItemCarriesNoChip() {
        XCTAssertTrue(SummaryUX.chips(review:false,superseded:false).isEmpty)
    }
    func testReviewAndSupersededEachGetOneChip() {
        XCTAssertEqual(SummaryUX.chips(review:true,superseded:false).map(\.text),["kontrol"])
        XCTAssertEqual(SummaryUX.chips(review:false,superseded:true).map(\.text),["geri alındı"])
    }
    func testSupersededItemDoesNotAlsoAskForAReview() {
        XCTAssertEqual(SummaryUX.chips(review:true,superseded:true).map(\.text),["geri alındı"])
    }
    func testExpansionKeysAreScopedToTheirSection() {
        XCTAssertNotEqual(SummaryUX.key("decisions","Aynı cümle"),SummaryUX.key("risks","Aynı cümle"))
        XCTAssertEqual(SummaryUX.key("risks","Aynı cümle"),SummaryUX.key("risks","Aynı cümle"))
    }
}
