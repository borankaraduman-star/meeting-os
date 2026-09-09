import XCTest
@testable import MeetingOS

final class TalkShareTests: XCTestCase {
    private func row(_ id:Int,_ start:Double,_ end:Double,name:String="",speaker:String="Konuşmacı 1",flags:[String]=[])->Row {
        Row(["id":id,"start":start,"end":end,"text":"x","speaker":speaker,"speaker_name":name,"source":"system","flags":flags])
    }
    func testSharesSumToOneAndSkipEcho() {
        let rows=[row(1,0,60,name:"Ayşe"),row(2,60,90,name:"Ali"),row(3,90,100,speaker:"Konuşmacı 3",flags:["cloud_transcript"]),row(4,0,50,flags:["possible_echo"])]
        let shares=TalkShare.compute(rows)
        XCTAssertEqual(shares.map(\.id),["Ayşe","Ali","Konuşmacı 3"])
        XCTAssertEqual(shares.map(\.share).reduce(0,+),1,accuracy:0.0001)
        XCTAssertEqual(shares[0].share,0.6,accuracy:0.0001)
        XCTAssertEqual(shares[0].minutes,"1 dk"); XCTAssertEqual(shares[2].minutes,"10 sn")
    }
    func testEmptyOrZeroLengthRowsGiveNoShares() {
        XCTAssertTrue(TalkShare.compute([]).isEmpty)
        XCTAssertTrue(TalkShare.compute([row(1,5,5)]).isEmpty)
    }
}
