import XCTest
@testable import MeetingOS

final class SetupStatusTests: XCTestCase {
    func testServiceChecksReadBridgeAnswer() {
        let c=SetupStatus.serviceChecks(["api_key":true,"glossary_terms":300,"glossary_shared":true,"update_behind":0])
        XCTAssertEqual(c.map(\.state),[.ok,.ok,.ok]); XCTAssertTrue(c[1].hint.contains("300 terim"))
        let d=SetupStatus.serviceChecks([:])
        XCTAssertEqual(d.map(\.state),[.missing,.optional,.ok])
        XCTAssertEqual(SetupStatus.serviceChecks(["update_behind":3])[2].hint,"3 değişiklik geride · kenar çubuğundan güncelleyin")
    }
}
