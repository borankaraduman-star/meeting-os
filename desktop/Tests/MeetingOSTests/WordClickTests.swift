import XCTest
import SwiftUI
@testable import MeetingOS

/// "Kelimeye tıkla, düzelt": the pure parts of the direct path — the link a word carries, the token it
/// points at, and the one-occurrence rewrite. No bridge call, no recording, no view.
final class WordClickURLTests:XCTestCase {
    private func roundTrip(_ ref:WordRef,file:StaticString=#filePath,line:UInt=#line) {
        guard let url=WordClick.url(ref) else { return XCTFail("no url for \(ref.word)",file:file,line:line) }
        XCTAssertEqual(url.scheme,"meetingos",file:file,line:line)
        XCTAssertEqual(url.host,"word",file:file,line:line)
        XCTAssertEqual(WordClick.parse(url),ref,file:file,line:line)
    }
    func testPlainWordRoundTrips() {
        roundTrip(WordRef(segment:12,index:0,word:"toplanti"))
    }
    func testTurkishLettersSurviveTheRoundTrip() {
        roundTrip(WordRef(segment:7,index:3,word:"görüşme"))
        roundTrip(WordRef(segment:7,index:4,word:"İstanbul"))
        roundTrip(WordRef(segment:7,index:5,word:"ÇĞİÖŞÜçğıöşü"))
    }
    func testApostrophesAndAmpersandsSurviveTheRoundTrip() {
        roundTrip(WordRef(segment:3,index:9,word:"Ahmet'in"))
        roundTrip(WordRef(segment:3,index:10,word:"Ar-Ge&Tasarım"))
        roundTrip(WordRef(segment:3,index:11,word:"i=5&seg=9"))   // a token that looks like the query itself
    }
    func testForeignAndMalformedURLsAreNotOurs() {
        XCTAssertNil(WordClick.parse(URL(string:"https://example.com/word?seg=1&i=0&w=a")!))
        XCTAssertNil(WordClick.parse(URL(string:"meetingos://other?seg=1&i=0&w=a")!))
        XCTAssertNil(WordClick.parse(URL(string:"meetingos://word?seg=1&i=0")!))        // no word
        XCTAssertNil(WordClick.parse(URL(string:"meetingos://word?seg=abc&i=0&w=a")!))  // no segment
        XCTAssertNil(WordClick.parse(URL(string:"meetingos://word?seg=1&i=-1&w=a")!))   // no such token
    }
}

final class WordTokenTests:XCTestCase {
    func testTokensCountEveryWordAndKeepTheirPunctuation() {
        let t=WordClick.tokens("Merhaba, bugün PMD'yi konuştuk.")
        XCTAssertEqual(t.count,4)
        XCTAssertEqual(t.map(\.raw),["Merhaba,","bugün","PMD'yi","konuştuk."])
        XCTAssertEqual(t.map(\.core),["Merhaba","bugün","PMD'yi","konuştuk"])
        XCTAssertEqual(t.map(\.index),[0,1,2,3])
    }
    func testFillersAreRecognisedOneTokenAtATime() {
        XCTAssertTrue(WordClick.isFiller("eee"))
        XCTAssertTrue(WordClick.isFiller("ııı"))
        XCTAssertTrue(WordClick.isFiller("hı"))
        XCTAssertTrue(WordClick.isFiller("Bi-"))
        XCTAssertFalse(WordClick.isFiller("bugün"))
        XCTAssertFalse(WordClick.isFiller("PMD"))
        XCTAssertFalse(WordClick.isFiller(""))
    }
    func testReplacingSwapsTheWordAndKeepsWhatSurroundsIt() {
        let text="Merhaba, bugün pemede konuştuk."
        XCTAssertEqual(WordClick.replacing(text,index:2,with:"PMD"),"Merhaba, bugün PMD konuştuk.")
    }
    func testReplacingKeepsPunctuationGluedToTheToken() {
        XCTAssertEqual(WordClick.replacing("Sonra pemede, tamam.",index:1,with:"PMD"),"Sonra PMD, tamam.")
        XCTAssertEqual(WordClick.replacing("Sonra “pemede” dedi.",index:1,with:"PMD"),"Sonra “PMD” dedi.")
        XCTAssertEqual(WordClick.replacing("pemede'yi aldık",index:0,with:"PMD"),"PMD aldık")   // the whole token is the word
    }
    func testReplacingKeepsSpacingAndOtherOccurrences() {
        XCTAssertEqual(WordClick.replacing("pemede ve  pemede",index:2,with:"PMD"),"pemede ve  PMD")
    }
    func testReplacingDoesNothingWhenTheIndexIsOutOfRange() {
        let text="Merhaba, bugün pemede konuştuk."
        XCTAssertEqual(WordClick.replacing(text,index:9,with:"PMD"),text)
        XCTAssertEqual(WordClick.replacing(text,index:-1,with:"PMD"),text)
        XCTAssertEqual(WordClick.replacing(text,index:1,with:"   "),text)   // nothing to write
    }
}

final class WordClickAttributedTextTests:XCTestCase {
    private func row(_ id:Int,_ text:String)->Row { Row(["id":id,"text":text,"start":0.0,"end":1.0]) }
    private func linked(_ s:AttributedString)->[WordRef] { s.runs.compactMap { $0.link.flatMap(WordClick.parse) } }

    func testEveryWordOfARowBecomesItsOwnLink() {
        let text="Merhaba, bugün pemede konuştuk."
        let a=WordClick.attributedText([row(4,text)],hideFillers:false)
        XCTAssertEqual(String(a.characters),text)                       // the drawn text is untouched
        XCTAssertEqual(linked(a).count,WordClick.tokens(text).count)    // one link per word
        XCTAssertEqual(linked(a).map(\.word),["Merhaba","bugün","pemede","konuştuk"])
        XCTAssertEqual(linked(a).map(\.index),[0,1,2,3])
        XCTAssertTrue(linked(a).allSatisfy { $0.segment==4 })
    }
    func testHiddenFillersDisappearFromTheTextButNotFromTheIndices() {
        let a=WordClick.attributedText([row(4,"Eee bugün pemede konuştuk.")],hideFillers:true)
        XCTAssertEqual(String(a.characters),"Bugün pemede konuştuk.")   // re-capitalised, like Fillers.clean
        XCTAssertEqual(linked(a).map(\.index),[1,2,3])                  // indices still point at the raw text
        XCTAssertEqual(WordClick.replacing("Eee bugün pemede konuştuk.",index:2,with:"PMD"),"Eee bugün PMD konuştuk.")
    }
    func testAParagraphLinksEveryPieceToItsOwnSegment() {
        let a=WordClick.attributedText([row(4,"Bugün pemede"),row(5,"konuştuk.")],hideFillers:false)
        XCTAssertEqual(String(a.characters),"Bugün pemede konuştuk.")
        XCTAssertEqual(linked(a).map(\.segment),[4,4,5])
        XCTAssertEqual(linked(a).map(\.index),[0,1,0])                  // each piece counts its own words
    }
    func testPunctuationOnlyTokensCarryNoLink() {
        let a=WordClick.attributedText([row(4,"Bugün — pemede")],hideFillers:false)
        XCTAssertEqual(linked(a).map(\.word),["Bugün","pemede"])
    }
}
