import XCTest
@testable import MeetingOS

/// Codex P2 #12: the naming sheet asks one question. These pin the mapping from the answer to the model call —
/// the whole of what the three old buttons used to decide — and the one explanation line each answer carries.
final class NamingScopeTests:XCTestCase {

    // MARK: which answers exist

    func testAClusterOffersAllThreeAnswersAndOpensOnTheLearningOne() {
        XCTAssertEqual(NamingScope.options(cluster:true),[.speaker,.segment,.meeting])
        XCTAssertEqual(NamingScope.initial(cluster:true),.speaker)
    }

    /// A row with no cluster behind it has nothing to choose: the picker is not drawn and the scope is the row.
    func testAPlainSegmentHasNothingToChoose() {
        XCTAssertEqual(NamingScope.options(cluster:false),[.segment])
        XCTAssertEqual(NamingScope.initial(cluster:false),.segment)
    }

    // MARK: scope → action

    func testTheDefaultAnswerNamesTheWholeVoiceAndLearnsIt() {
        XCTAssertEqual(NamingScope.speaker.action(cluster:true,clean:false),.speakerWithVoice)
        XCTAssertEqual(NamingScope.speaker.action(cluster:true,clean:true),.speakerWithVoice)   // the clean toggle is not part of this answer
    }

    func testOnlyThisMeetingNamesTheClusterWithoutLearning() {
        XCTAssertEqual(NamingScope.meeting.action(cluster:true,clean:false),.speakerThisMeeting)
        XCTAssertEqual(NamingScope.meeting.action(cluster:true,clean:true),.speakerThisMeeting)
    }

    func testOnlyThisPieceWritesOnePiece() {
        XCTAssertEqual(NamingScope.segment.action(cluster:true,clean:false),.segmentOnly)
    }

    /// The risk the review named: "yalnız burada" must never turn into global teaching. Every answer keeps its
    /// own call, and no answer reaches a different one.
    func testEveryAnswerKeepsItsOwnCall() {
        let actions=NamingScope.allCases.map { $0.action(cluster:true,clean:true) }
        XCTAssertEqual(Set(actions.map(String.init(describing:))).count,3)
        XCTAssertEqual(actions.filter { $0 == .speakerWithVoice }.count,1)   // only the default answer teaches the voice
        XCTAssertFalse(actions.contains(.label(enroll:true)))                // a cluster never falls through to the plain label
    }

    /// Without a cluster the scope is irrelevant: it is always the one segment, and only the Gelişmiş toggle
    /// decides whether the voice profile learns from it.
    func testAPlainSegmentIsLabelledAndLearnsOnlyWhenTheUserConfirmedACleanClip() {
        for scope in NamingScope.allCases {
            XCTAssertEqual(scope.action(cluster:false,clean:false),.label(enroll:false))
            XCTAssertEqual(scope.action(cluster:false,clean:true),.label(enroll:true))
        }
    }

    // MARK: what the sheet says

    func testEachAnswerHasItsOwnLabelAndItsOwnSingleLine() {
        let labels=NamingScope.allCases.map(\.label), lines=NamingScope.allCases.map(\.explanation)
        XCTAssertEqual(Set(labels).count,3); XCTAssertEqual(Set(lines).count,3)
        for text in labels+lines { XCTAssertFalse(text.isEmpty) }
    }

    func testTheLinesSayTheThingThatDecidesTheChoice() {
        XCTAssertTrue(NamingScope.speaker.explanation.contains("öğrenir"))
        XCTAssertTrue(NamingScope.speaker.explanation.contains("varsayılan"))
        XCTAssertTrue(NamingScope.segment.explanation.contains("yalnız bu cümle") || NamingScope.segment.explanation.contains("Yalnız bu cümle"))
        XCTAssertTrue(NamingScope.meeting.explanation.contains("Öğrenme yok"))
    }

    func testAPlainSegmentGetsALineInsteadOfAPicker() {
        XCTAssertTrue(NamingScope.plainExplanation(textOnly:true).contains("yalnızca metin"))
        XCTAssertTrue(NamingScope.plainExplanation(textOnly:false).contains("6 sn"))
        XCTAssertNotEqual(NamingScope.plainExplanation(textOnly:true),NamingScope.plainExplanation(textOnly:false))
    }

    // MARK: the piece picker

    /// The extra picker only appears where it is needed: a one-piece correction inside a paragraph that has pieces.
    func testThePiecePickerOnlyAppearsForAOnePieceCorrectionInASplitParagraph() {
        XCTAssertTrue(NamingScope.showsPiecePicker(scope:.segment,cluster:true,pieces:3))
        XCTAssertFalse(NamingScope.showsPiecePicker(scope:.segment,cluster:true,pieces:1))
        XCTAssertFalse(NamingScope.showsPiecePicker(scope:.speaker,cluster:true,pieces:3))
        XCTAssertFalse(NamingScope.showsPiecePicker(scope:.meeting,cluster:true,pieces:3))
        XCTAssertFalse(NamingScope.showsPiecePicker(scope:.segment,cluster:false,pieces:3))
    }
}
