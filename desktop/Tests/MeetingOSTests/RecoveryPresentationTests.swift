import XCTest
@testable import MeetingOS
final class RecoveryPresentationTests:XCTestCase {
    func testOnlyRecoverableCapturesCanRetry() {
        for status in ["incomplete","provisional","failed"] {
            XCTAssertTrue(RecoveryPresentation.canRetry(status:status,hasCapture:true,owner:"unknown"))
        }
        XCTAssertTrue(RecoveryPresentation.canRetry(status:"processing",hasCapture:true,owner:"interrupted"))
        for owner in ["active","unknown"] {
            XCTAssertFalse(RecoveryPresentation.canRetry(status:"processing",hasCapture:true,owner:owner))
        }
        XCTAssertFalse(RecoveryPresentation.canRetry(status:"complete",hasCapture:true,owner:"interrupted"))
        XCTAssertFalse(RecoveryPresentation.canRetry(status:"incomplete",hasCapture:false,owner:"interrupted"))
    }
    func testCancelExcludesCaptureDrainAndMissingJob() {
        XCTAssertTrue(RecoveryPresentation.canCancel(jobKind:"retry",running:true,requested:false))
        XCTAssertFalse(RecoveryPresentation.canCancel(jobKind:"record",running:true,requested:false))
        XCTAssertFalse(RecoveryPresentation.canCancel(jobKind:"finalize",running:true,requested:false))
        XCTAssertFalse(RecoveryPresentation.canCancel(jobKind:"import",running:true,requested:false))
        XCTAssertFalse(RecoveryPresentation.canCancel(jobKind:"retry",running:false,requested:false))
        XCTAssertFalse(RecoveryPresentation.canCancel(jobKind:"retry",running:true,requested:true))
    }
}
