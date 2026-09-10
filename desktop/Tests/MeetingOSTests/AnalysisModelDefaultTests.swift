import XCTest
@testable import MeetingOS

final class AnalysisModelDefaultTests:XCTestCase {
    func testOldDefaultMovesOnceAndChoicesStay() {
        var written:[String?]=[]
        XCTAssertEqual(AnalysisModelDefault.resolve(stored:"deepseek/deepseek-v3.2",migrated:false) { written.append($0) },"openai/gpt-4.1-mini")
        XCTAssertEqual(written,[nil])                                   // stored value cleared → new default from now on
        XCTAssertEqual(AnalysisModelDefault.resolve(stored:"google/gemini-2.5-flash",migrated:false) { written.append($0) },"google/gemini-2.5-flash")
        XCTAssertEqual(AnalysisModelDefault.resolve(stored:nil,migrated:false) { written.append($0) },"openai/gpt-4.1-mini")
        XCTAssertEqual(AnalysisModelDefault.resolve(stored:"deepseek/deepseek-v3.2",migrated:true) { written.append($0) },"deepseek/deepseek-v3.2")   // chosen after the move: kept
        XCTAssertEqual(written.count,3)
    }
}
