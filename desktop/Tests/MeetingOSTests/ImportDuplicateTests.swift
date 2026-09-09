import XCTest
@testable import MeetingOS
final class ImportDuplicateTests:XCTestCase {
    func testParsesBridgeResponseAndNullMeansNoDuplicate() {
        XCTAssertNil(ImportDuplicate.parse(["duplicate":NSNull(),"digest":"ab"]))
        XCTAssertNil(ImportDuplicate.parse([:]))
        XCTAssertNil(ImportDuplicate.parse(["duplicate":["meeting":""]]))
        let dup=ImportDuplicate.parse(["duplicate":["meeting":"abc","title":"Sprint","model":"microsoft/mai-transcribe-2"]])
        XCTAssertEqual(dup,ImportDuplicate(meeting:"abc",title:"Sprint",model:"microsoft/mai-transcribe-2"))
        XCTAssertEqual(dup?.notice,"Bu dosyayı zaten işlemiştin: “Sprint” · microsoft/mai-transcribe-2")
        XCTAssertEqual(ImportDuplicate(meeting:"x",title:"",model:"").notice,"Bu dosyayı zaten işlemiştin: “Adsız toplantı”")
    }
    func testUploadLabelStillAllowsSending() {
        XCTAssertEqual(ImportDuplicate.uploadLabel(duplicate:true),"Yine de gönder")
        XCTAssertEqual(ImportDuplicate.uploadLabel(duplicate:false),"Yükle ve yazıya çevir")
    }
}
