import XCTest
@testable import MeetingOS

final class BridgeStatsTests: XCTestCase {
    func testPercentilesWindowAndCounters() {
        let s=BridgeStats(capacity:5)
        XCTAssertNil(s.percentile(0.5)); XCTAssertEqual(s.summary,"henüz ölçüm yok")
        for v in [0.01,0.02,0.03,0.04,1.5,0.05,0.06] { s.record(seconds:v,failed:v==0.06) }
        XCTAssertEqual(s.percentile(0.5)!,0.05,accuracy:0.0001)   // window keeps the last 5: .03 .04 1.5 .05 .06
        XCTAssertEqual(s.percentile(0.95)!,1.5,accuracy:0.0001)
        XCTAssertEqual(s.slow,1); XCTAssertEqual(s.failures,1)
        XCTAssertTrue(s.summary.contains(">1 sn: 1"))
    }
}
