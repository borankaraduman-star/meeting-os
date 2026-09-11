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
        XCTAssertEqual(rules[0].id,"taught::pemede")   // source + host + original: a team rule and a local rule for the same word are two rows
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
        XCTAssertEqual(r.repeatLine,"");XCTAssertFalse(r.conflict)
    }
    /// Did teaching the word actually help? The row says so in one sentence, or says nothing at all.
    func testRepeatLineSaysWhetherTheRuleCaughtTheRepeats() {
        func rule(_ repeats:Int,_ fixed:Int)->WordRule { WordRule(["original":"pemede","replacement":"PMD","source":"taught","repeats":repeats,"repeats_fixed":fixed]) }
        XCTAssertEqual(rule(0,0).repeatLine,"")                                    // never came back wrong: nothing to report
        XCTAssertEqual(rule(3,3).repeatLine,"3 kez tekrar etti, hepsi düzeltildi")
        XCTAssertEqual(rule(3,0).repeatLine,"3 kez tekrar etti, düzeltilmedi")
        XCTAssertEqual(rule(3,1).repeatLine,"3 kez tekrar etti, 2 tanesi düzeltilmedi")
    }
    /// Three different reasons a team row is listed but does not rewrite anything, and they do not mean the same.
    func testTeamNoteTellsTheThreeReasonsApart() {
        func team(_ extra:[String:Any])->WordRule { WordRule(["original":"Ayşen","replacement":"Ayşe","source":"team","host":"mac-a"].merging(extra) { _,b in b }) }
        XCTAssertEqual(team(["enabled":false,"active":false]).teamNote,"bu Mac’te kapalı")
        XCTAssertEqual(team(["enabled":true,"active":false]).teamNote,"bu Mac’in kendi yazımı öncelikli")
        XCTAssertEqual(team(["enabled":true,"active":false,"conflict":true]).teamNote,"ekipte iki yazım var · Kontrol’de soruluyor")
        XCTAssertEqual(team(["enabled":true,"active":true]).teamNote,"")
    }
}

/// The team spelling question: two teammates, two spellings, one local answer.
final class WordConflictItemTests:XCTestCase {
    func item()->ReviewItem {
        ReviewItem(["segment_id":4,"start":30.0,"kind":"word_conflict","severity":2,"key":"word_conflict:trendyoll",
                    "source_version":"w:trendyol|trendyol a.ş.","original":"Trendyoll",
                    "reason":"Ekipte iki yazım: Trendyol / Trendyol A.Ş. — hangisi? · mac-a, mac-c",
                    "options":[["replacement":"Trendyol","host":"mac-a"],["replacement":"Trendyol A.Ş.","host":"mac-c"]]])
    }
    func testTheOptionsAndTheQuestionSurviveTheBridge() {
        let i=item()
        XCTAssertEqual(i.title,"Ekipte iki yazım: “Trendyoll”")
        XCTAssertEqual(i.options.map { $0.replacement },["Trendyol","Trendyol A.Ş."])
        XCTAssertEqual(i.options.map { $0.host },["mac-a","mac-c"])
        XCTAssertTrue(i.reason.contains("hangisi?"))
        XCTAssertTrue(ReviewUX.resolvable(i))
        XCTAssertEqual(i.key,"word_conflict:trendyoll")       // the word, not the segment: one question, asked once
        XCTAssertEqual(i.sourceVersion,"w:trendyol|trendyol a.ş.")
    }
    func testAnItemWithNoOptionsOffersNoButtons() {
        XCTAssertEqual(ReviewItem(["kind":"word_conflict","original":"x"]).options.count,0)
        XCTAssertEqual(ReviewItem(["kind":"word_conflict","options":[["host":"mac-a"]]]).options.count,0)
    }
}
