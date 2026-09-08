import XCTest
@testable import MeetingOS
final class ResourceGuardTests:XCTestCase {
    func testSixteenGBBudgetReservesMostMemoryForDesktop() {
        XCTAssertEqual(ResourceGuard.budget(physical:16*1024*1024*1024),4*1024*1024*1024)
    }
    func testFootprintReadsCurrentProcessWithoutAllocatingModels() {
        let bytes=ResourceGuard.footprint(pid:getpid())
        XCTAssertNotNil(bytes);XCTAssertGreaterThan(bytes ?? 0,0)
    }
}
