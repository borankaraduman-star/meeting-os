import XCTest
@testable import MeetingOS
final class RecoveryPresentationTests:XCTestCase {
    func testOnlyRecoverableCapturesCanRetry() {
        for status in ["incomplete","failed"] {
            XCTAssertTrue(RecoveryPresentation.canRetry(status:status,hasCapture:true,owner:"unknown"))
        }
        XCTAssertTrue(RecoveryPresentation.canRetry(status:"processing",hasCapture:true,owner:"interrupted"))
        for owner in ["active","unknown"] {
            XCTAssertFalse(RecoveryPresentation.canRetry(status:"processing",hasCapture:true,owner:owner))
        }
        XCTAssertFalse(RecoveryPresentation.canRetry(status:"complete",hasCapture:true,owner:"interrupted"))
        XCTAssertFalse(RecoveryPresentation.canRetry(status:"incomplete",hasCapture:false,owner:"interrupted"))
    }
    func testRecordingAndStoppedStatesAreDistinct() {
        let pending=Meeting(["status":"provisional","display_status":"pending_finalization"])
        XCTAssertEqual(statusLabel(pending.displayStatus),"Son işlem bekliyor")
        XCTAssertEqual(statusLabel(Meeting(["status":"incomplete","display_status":"not_started"]).displayStatus),"Kayıt başlayamadı")
        XCTAssertEqual(RecoveryPresentation.recordingLabel(recording:true,jobKind:"record"),"Kaydı bitir")
        XCTAssertEqual(RecoveryPresentation.recordingLabel(recording:false,jobKind:"record"),"Kayıt durduruluyor…")
        XCTAssertEqual(RecoveryPresentation.recordingLabel(recording:true,jobKind:nil),"Kaydı bitir")
        XCTAssertEqual(RecoveryPresentation.recordingLabel(recording:false,jobKind:nil),"Yeni kayıt")
        XCTAssertFalse(RecoveryPresentation.canRetry(status:"provisional",hasCapture:true,owner:"active"))
        XCTAssertFalse(RecoveryPresentation.canRetry(status:"provisional",hasCapture:true,owner:"unknown"))
        XCTAssertTrue(RecoveryPresentation.canRetry(status:"provisional",hasCapture:true,owner:"interrupted"))
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
