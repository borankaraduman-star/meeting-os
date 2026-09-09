import XCTest
@testable import MeetingOS
final class RecordingCompletionTests:XCTestCase {
    func testReceiptSelectsRecordedMeetingWithoutLibraryPolling() {
        let receipt:[String:Any] = ["meeting":"recorded", "capture_dir":"/capture", "status":"provisional", "finalized_chunks":2]
        XCTAssertEqual(RecordingCompletion.retryMeeting(receipt,capture:"/capture"),"recorded")
    }
    /// A supervisor complaint rides the receipt now. The meeting is still finalized; the user gets one calm
    /// line instead of "Kayıt tamamlanamadı" over a folder that holds the whole meeting.
    func testAReceiptWithErrorsStillFinalizesAndSaysSoCalmly() {
        let receipt:[String:Any] = ["meeting":"recorded","capture_dir":"/capture","status":"provisional","finalized_chunks":3,
                                    "errors":["Kayıt yardımcısı bir saat içinde 5 kez yeniden başlatıldı; ses korundu"]]
        XCTAssertEqual(RecordingCompletion.retryMeeting(receipt,capture:"/capture"),"recorded")
        XCTAssertEqual(RecordingCompletion.notice(receipt),"Kayıt sırasında bir aksama oldu · alınan ses korundu, yazıya çevriliyor")
        XCTAssertNil(RecordingCompletion.notice(["errors":[]] as [String:Any]))
        XCTAssertNil(RecordingCompletion.notice(["errors":[""]] as [String:Any]))
        XCTAssertNil(RecordingCompletion.notice([:]))
    }
    func testMissingWrongCanceledAndEmptyReceiptsDoNotFinalize() {
        let receipt:[String:Any] = ["meeting":"recorded", "capture_dir":"/capture", "status":"provisional", "finalized_chunks":2]
        XCTAssertNil(RecordingCompletion.retryMeeting([:],capture:"/capture"))
        XCTAssertNil(RecordingCompletion.retryMeeting(receipt,capture:"/other"))
        for update in [["status":"canceled"],["finalized_chunks":0],["meeting":""]] as [[String:Any]] {
            XCTAssertNil(RecordingCompletion.retryMeeting(receipt.merging(update){_,new in new},capture:"/capture"))
        }
    }
}

extension RecordingCompletionTests {
    func testSymlinkedCapturePathMatchesCanonicalReceipt() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let actual=root.appendingPathComponent("actual")
        let alias=root.appendingPathComponent("alias")
        try FileManager.default.createDirectory(at:actual,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:root) }
        try FileManager.default.createSymbolicLink(at:alias,withDestinationURL:actual)
        let receipt:[String:Any] = ["meeting":"recorded","capture_dir":actual.resolvingSymlinksInPath().path,"status":"provisional","finalized_chunks":1]
        XCTAssertEqual(RecordingCompletion.retryMeeting(receipt,capture:alias.path),"recorded")
    }
}
