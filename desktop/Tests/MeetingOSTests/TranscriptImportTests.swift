import XCTest
@testable import MeetingOS
final class TranscriptImportTests:XCTestCase {
    func testPreviewMustMatchExactCurrentTextAndTitle() {
        var draft=TranscriptImportDraft(text:"Boran: Sprint planı hazır.",title:"Toplantı")
        XCTAssertFalse(draft.canSave)
        draft.markPreviewed();XCTAssertTrue(draft.canSave)
        draft.text += " Yeni karar.";XCTAssertFalse(draft.canSave)
        draft.markPreviewed();draft.title="Başka toplantı";XCTAssertFalse(draft.canSave)
        draft.markPreviewed();draft.invalidatePreview();XCTAssertFalse(draft.canSave)
    }
    func testInvalidInputsCannotSave() {
        for text in [" \n", "Ses\0",String(repeating:"ğ",count:TranscriptImportDraft.byteLimit/2+1)] {
            var draft=TranscriptImportDraft(text:text,title:"Toplantı");draft.markPreviewed()
            XCTAssertNotNil(draft.inputError);XCTAssertFalse(draft.canSave)
        }
    }
    func testUntimedRowsDoNotInventVisibleZeroTimestamp() {
        let row=Row(["text":"Merhaba","start":NSNull(),"flags":["untimed","imported_text"]])
        XCTAssertEqual(row.time,"")
        XCTAssertFalse(row.notices.contains("untimed"))
        XCTAssertEqual(Row(["start":12.0]).time,"00:12")
    }
    func testFileReadsAreBoundedAndStrictUTF8() throws {
        let url=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".txt")
        defer { try? FileManager.default.removeItem(at:url) }
        try Data("Boran: Türkçe\n".utf8).write(to:url)
        XCTAssertEqual(try TranscriptImportDraft.readFile(url),"Boran: Türkçe\n")
        try Data([0xff,0xfe]).write(to:url)
        XCTAssertThrowsError(try TranscriptImportDraft.readFile(url))
        try Data(repeating:65,count:TranscriptImportDraft.byteLimit+1).write(to:url)
        XCTAssertThrowsError(try TranscriptImportDraft.readFile(url))
    }
}
