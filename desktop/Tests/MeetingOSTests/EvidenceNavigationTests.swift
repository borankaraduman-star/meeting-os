import XCTest
@testable import MeetingOS
final class EvidenceNavigationTests:XCTestCase {
    let rows=[Row(["id":7,"text":"Düzeltilmiş metin"]),Row(["id":8,"text":"Aynı alıntı"]),Row(["id":9,"text":"Aynı alıntı"])]
    func testEditedQuoteStillResolvesItsSegment() {
        XCTAssertEqual(Evidence(["segment_id":7,"quote":"Eski metin"]).destination(in:rows)?.id,7)
    }
    func testDuplicateQuotesResolveBySegment() {
        XCTAssertEqual(Evidence(["segment_id":9,"quote":"Aynı alıntı"]).destination(in:rows)?.id,9)
    }
    func testDeletedSegmentDoesNotPointAtAnotherSpeaker() {
        XCTAssertNil(Evidence(["segment_id":99,"quote":"Aynı alıntı"]).destination(in:rows))
    }
}
