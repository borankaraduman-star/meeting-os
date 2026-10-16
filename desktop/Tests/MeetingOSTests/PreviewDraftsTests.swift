import XCTest
@testable import MeetingOS

/// The transcript tab's view of `transcript_previews`: drafts stay apart from the result, never move backwards
/// across a reconnect, give way to final rows and say plainly when they are paused or stopped.
final class PreviewDraftsTests:XCTestCase {
    func draft(_ span:String,_ s:Double,_ e:Double,_ text:String,src:String="system",epoch:Int=1,rev:Int=1,status:String="final",updated:Double=1)->[String:Any] {
        ["span_id":span,"source":src,"epoch":epoch,"revision":rev,"status":status,"text":text,"audio_start":s,"audio_end":e,"updated":updated]
    }
    func reply(_ rows:[[String:Any]],meeting:String="m1",status:[String:Any]?=["state":"running","lag_seconds":4.0,"epoch":1])->[String:Any] {
        var r:[String:Any]=["meeting":meeting,"previews":rows,"draft":true]; if let status { r["status"]=status }; return r
    }
    func final(_ id:Int,_ s:Double,_ e:Double,src:String="system")->Row { Row(["id":id,"start":s,"end":e,"text":"sonuç","speaker":"Konuşmacı 1","source":src,"flags":["cloud_transcript"]]) }

    func testFinalRowsHideTheDraftTheyCover() {
        let st=PreviewDrafts.merge(PreviewState(),reply:reply([draft("system:0.000",0,12,"ilk taslak"),draft("system:12.000",12,24,"ikinci taslak"),draft("mic:0.000",0,12,"mikrofon taslağı",src:"mic")]))
        XCTAssertEqual(PreviewDrafts.visible(st,finals:[],complete:false).map(\.id),["mic:0.000","system:0.000","system:12.000"])
        // The result for the first system span arrived: its draft goes, the uncovered ones and the other source stay.
        XCTAssertEqual(PreviewDrafts.visible(st,finals:[final(1,0,11)],complete:false).map(\.id),["mic:0.000","system:12.000"])
        XCTAssertFalse(PreviewDrafts.covered(PreviewDraft(draft("system:12.000",12,24,"x")),by:[final(2,22,30)]))   // a sliver of overlap is not coverage
        XCTAssertTrue(PreviewDraft(draft("a",0,12,"x")).label=="Taslak");XCTAssertEqual(PreviewDraft(draft("a",0,12,"x",status:"partial")).label,"Taslak · değişebilir")
        XCTAssertTrue(PreviewDrafts.visible(st,finals:[],complete:true).isEmpty)   // a finished meeting shows its transcript only
    }
    func testOlderRevisionOrEpochNeverReplacesTheKeptDraft() {
        var st=PreviewDrafts.merge(PreviewState(),reply:reply([draft("s",0,12,"yeni",epoch:2,rev:2,status:"partial",updated:5)]))
        st=PreviewDrafts.merge(st,reply:reply([draft("s",0,12,"eski revizyon",epoch:2,rev:1,status:"final",updated:6)]))
        XCTAssertEqual(st.cache["s"]?.text,"yeni")
        st=PreviewDrafts.merge(st,reply:reply([draft("s",0,12,"eski bağlantı",epoch:1,rev:9,status:"final",updated:7)]))
        XCTAssertEqual(st.cache["s"]?.text,"yeni")   // a reply from a replaced connection is stale whatever its revision
        st=PreviewDrafts.merge(st,reply:reply([draft("s",0,12,"son hali",epoch:2,rev:3,status:"final",updated:8)]))
        XCTAssertEqual(st.cache["s"]?.text,"son hali")
        st=PreviewDrafts.merge(st,reply:reply([draft("s",0,12,"yeniden açılmaz",epoch:3,rev:4,status:"partial",updated:9)]))
        XCTAssertEqual(st.cache["s"]?.text,"son hali")   // a final draft is never reopened
        XCTAssertEqual(st.cursor,9)
        // Another meeting's reply starts clean instead of painting over this one.
        let other=PreviewDrafts.merge(st,reply:reply([draft("t",0,12,"başka")],meeting:"m2"))
        XCTAssertEqual(other.meeting,"m2");XCTAssertEqual(Array(other.cache.keys),["t"])
        XCTAssertEqual(PreviewDrafts.merge(st,reply:["previews":[draft("u",0,1,"x")]]),st)   // no meeting id, no change
    }
    func testEmptyPausedAndStoppedSayWhatStillHappens() {
        let empty=PreviewDrafts.merge(PreviewState(),reply:reply([],status:nil))
        XCTAssertTrue(PreviewDrafts.visible(empty,finals:[],complete:false).isEmpty)
        XCTAssertEqual(PreviewDrafts.statusLine(empty,recording:true),"Canlı taslak bekleniyor · ilk ses parçası kapanınca gelir")
        let running=PreviewDrafts.merge(PreviewState(),reply:reply([]))
        XCTAssertEqual(PreviewDrafts.statusLine(running,recording:true),"Canlı taslak · ≈4 sn geride")
        XCTAssertEqual(PreviewDrafts.lagText(1),"güncel");XCTAssertEqual(PreviewDrafts.lagText(180),"≈3 dk geride")
        let paused=PreviewDrafts.merge(PreviewState(),reply:reply([draft("s",0,12,"",status:"failed")],status:["state":"paused","reason":"cost","lag_seconds":0,"epoch":1]))
        XCTAssertTrue(PreviewDrafts.visible(paused,finals:[],complete:false).isEmpty)   // a failed span is a count, never a blank line
        let line=PreviewDrafts.statusLine(paused,recording:true)
        XCTAssertTrue(line.hasPrefix("Canlı taslak duraklatıldı · maliyet sınırına ulaşıldı"));XCTAssertTrue(line.contains("kayıt sürüyor"));XCTAssertTrue(line.contains("1 parçanın taslağı alınamadı"))
        let stopped=PreviewDrafts.merge(PreviewState(),reply:reply([],status:["state":"stopped","reason":"grace_exceeded","epoch":2]))
        XCTAssertEqual(PreviewDrafts.statusLine(stopped,recording:false),"Canlı taslak durdu · son parçaların taslağı yetişmedi · asıl yazıya çevirme toplantı sonunda yapılır")
        XCTAssertEqual(PreviewDrafts.statusLine(PreviewDrafts.merge(PreviewState(),reply:reply([],status:["state":"paused","reason":"yeni_bir_sebep"])),recording:true).components(separatedBy:" · ")[1],"bir sınır aşıldı")
        XCTAssertEqual(PreviewDrafts.recordingBadge,"Canlı taslak açık · ses buluta gidiyor")
    }
    /// The bridge hands SQLite REAL columns over as NSNumber.
    func testNumbersFromTheBridgeParse() {
        let d=PreviewDraft(["span_id":"s","audio_start":NSNumber(value:61.5),"audio_end":NSNumber(value:73),"updated":NSNumber(value:2.5)])
        XCTAssertEqual(d.start,61.5);XCTAssertEqual(d.end,73);XCTAssertEqual(d.time,"01:01")
    }
}
