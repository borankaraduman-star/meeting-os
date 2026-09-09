import XCTest
@testable import MeetingOS
final class ShareOptionsTests:XCTestCase {
    func testRequestCarriesEveryOptionAndDropsTranscriptForDecisionsOnly() {
        var o=ShareOptions()
        var r=o.request(action:"share_preview",meeting:"m1")
        XCTAssertEqual(r["action"] as? String,"share_preview");XCTAssertEqual(r["meeting"] as? String,"m1")
        XCTAssertEqual(r["mask_names"] as? Bool,true);XCTAssertEqual(r["only_decisions"] as? Bool,false);XCTAssertEqual(r["kinds"] as? [String],["transcript","summary"]);XCTAssertNil(r["path"])
        o.includeTranscript=false
        XCTAssertEqual(o.kinds,["summary"])
        o.includeTranscript=true;o.onlyDecisions=true;o.maskNames=false
        r=o.request(action:"share_export",meeting:"m1",path:"/tmp/x.md")
        XCTAssertEqual(r["kinds"] as? [String],["summary"]);XCTAssertEqual(r["only_decisions"] as? Bool,true);XCTAssertEqual(r["mask_names"] as? Bool,false);XCTAssertEqual(r["path"] as? String,"/tmp/x.md")
    }
    func testSummaryLineReflectsMaskingAndScope() {
        var o=ShareOptions()
        XCTAssertEqual(o.summary(maskedNames:3,segments:12),"3 isim maskelendi · 12 bölüm")
        XCTAssertEqual(o.summary(maskedNames:0,segments:12),"Maskelenecek isim bulunmadı · 12 bölüm")
        o.maskNames=false;o.includeTranscript=false
        XCTAssertEqual(o.summary(maskedNames:0,segments:0),"İsimler açık · transkript yok")
        o.onlyDecisions=true
        XCTAssertEqual(o.summary(maskedNames:0,segments:0),"İsimler açık · yalnız kararlar")
    }
    func testFileNameIsSafeAndDescribesTheVariant() {
        var o=ShareOptions()
        XCTAssertEqual(o.fileName(title:"Sprint/planı: eylül "),"Sprint-planı- eylül · paylaşım · maskeli.md")
        o.maskNames=false;o.onlyDecisions=true
        XCTAssertEqual(o.fileName(title:""),"Toplantı · paylaşım · kararlar.md")
    }
}
