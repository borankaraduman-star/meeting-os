import XCTest
@testable import MeetingOS

/// "Teach a word once": the Kontrol item the bridge sends for a suspicious word, and the learned-word
/// list Ayarlar shows. Parsing only — no bridge call, no recording.
final class WordReviewItemTests:XCTestCase {
    func testWordItemParsesTitleCountAndId() {
        let w=ReviewItem(["segment_id":12,"start":125.0,"kind":"word","severity":2,"reason":"Yakın yazım","original":"pemede","replacement":"PMD","count":4])
        XCTAssertEqual(w.title,"Kelime: “pemede” muhtemelen “PMD”")
        XCTAssertEqual(w.count,4)
        XCTAssertEqual(w.id,"word:12:pemede")
        XCTAssertEqual(w.time,"02:05")
        XCTAssertEqual(w.replacement,"PMD")
    }
    func testCountIsZeroWhenTheBridgeOmitsIt() {
        XCTAssertEqual(ReviewItem(["segment_id":3,"kind":"glossary","original":"a","replacement":"b"]).count,0)
    }
    @MainActor func testLearnedLineNamesBothSpellingsAndTheCount() {
        let line=Model.wordLearnedLine(original:"pemede",replacement:"PMD",fixes:4)
        XCTAssertTrue(line.contains("“pemede” → “PMD”"))
        XCTAssertTrue(line.contains("4 yerde"))
        XCTAssertTrue(line.contains("öğrenildi"))
    }
}

final class WordRuleTests:XCTestCase {
    func testRulesParseFromTheBridgePayload() {
        let payload:[String:Any]=["rules":[
            ["original":"pemede","replacement":"PMD","source":"taught","count":4,"meetings":2,"created":"2026-09-10","vocabulary_added":true],
            ["original":"sıkrım","replacement":"Scrum","source":"learned","count":9,"meetings":3,"created":"2026-09-01"]
        ]]
        let rules=(payload["rules"] as? [[String:Any]] ?? []).map(WordRule.init)
        XCTAssertEqual(rules.count,2)
        XCTAssertEqual(rules[0].id,"pemede")
        XCTAssertEqual(rules[0].sourceLabel,"öğretildi")
        XCTAssertTrue(rules[0].vocabularyAdded)
        XCTAssertEqual(rules[0].line,"“pemede” → “PMD” · öğretildi · 2 toplantı")
        XCTAssertEqual(rules[1].sourceLabel,"öğrenildi")
        XCTAssertFalse(rules[1].vocabularyAdded)
        XCTAssertEqual(rules[1].meetings,3)
    }
    func testMissingFieldsFallBackInsteadOfCrashing() {
        let r=WordRule([:])
        XCTAssertEqual(r.original,"");XCTAssertEqual(r.meetings,0);XCTAssertEqual(r.sourceLabel,"öğrenildi")
    }
}
