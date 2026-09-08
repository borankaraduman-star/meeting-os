import XCTest
@testable import MeetingOS
final class RecordingCompletionTests:XCTestCase {
    func testReceiptSelectsRecordedMeetingWithoutLibraryPolling() {
        let receipt:[String:Any] = ["meeting":"recorded", "capture_dir":"/capture", "status":"provisional", "finalized_chunks":2]
        XCTAssertEqual(RecordingCompletion.retryMeeting(receipt,capture:"/capture"),"recorded")
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
