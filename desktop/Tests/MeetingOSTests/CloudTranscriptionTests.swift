import XCTest
@testable import MeetingOS
final class TranscriptBlocksTests:XCTestCase {
    func row(_ id:Int,_ s:Double,_ e:Double,_ text:String,_ name:String,src:String="system",flags:[String]=["cloud_transcript","cloud_diarization","confidence_unavailable","speaker_unverified"],suggested:String="")->Row {
        Row(["id":id,"start":s,"end":e,"text":text,"speaker":name,"source":src,"flags":flags,"suggested":suggested])
    }
    func testInterjectionsFoldIntoTheInterruptedParagraph() {
        let rows=[row(1,0,26,"Uzun konuşma.","Gözlük"),row(2,26.4,27.2,"Hı hı.","Sol Üst"),row(3,27.4,29,"devamı.","Gözlük"),row(4,29.4,29.6,"Tabii.","Sol Üst"),row(5,29.9,36,"son kısım.","Gözlük"),row(6,36.8,61,"Ben ama şey demek istiyorum.","Sol Üst"),row(7,61,61.1,"Evet.","Gözlük"),row(8,61.2,68,"devam ediyorum.","Sol Üst")]
        let blocks=TranscriptBlocks.build(rows)
        XCTAssertEqual(blocks.map(\.label),["Gözlük","Sol Üst"])
        XCTAssertEqual(blocks[0].text,"Uzun konuşma. devamı. son kısım.");XCTAssertEqual(blocks[0].asides.map(\.id),[2,4])
        XCTAssertEqual(blocks[1].asides.map(\.id),[7]);XCTAssertEqual(TranscriptBlocks.asideCount(blocks),3)
    }
    func testShortTurnAtSpeakerChangeStaysItsOwnBlock() {
        let rows=[row(1,0,10,"A konuşuyor.","A"),row(2,10,11,"Evet.","B"),row(3,11,20,"B uzun konuşuyor.","B")]
        let blocks=TranscriptBlocks.build(rows)
        XCTAssertEqual(blocks.map(\.label),["A","B"]);XCTAssertEqual(blocks[1].rows.map(\.id),[2,3]);XCTAssertTrue(blocks[1].asides.isEmpty)
    }
    func testCloudNoticesAreSaidOncePerMeeting() {
        let r=row(1,0,5,"x","Gözlük")
        XCTAssertEqual(r.notices,"")
        XCTAssertEqual(TranscriptBlocks.meetingNotice([r]),"Bulut transkript · OpenRouter · güven ölçümü yok · konuşmacı adları doğrulanmadı · konuşmacı ayrımı sağlayıcıdan")
        XCTAssertNil(TranscriptBlocks.meetingNotice([row(2,0,5,"x","S0",flags:[])]))
        XCTAssertTrue(row(3,0,5,"x","Boran",src:"mic",flags:["cloud_transcript","possible_echo"]).notices.contains("yankı"))
    }
    func testSuggestedNameShowsQuestionMarkUntilConfirmed() {
        XCTAssertEqual(row(1,0,5,"x","Konuşmacı 3",suggested:"Sol Üst").label,"Sol Üst?")
        XCTAssertEqual(Row(["id":1,"speaker":"Konuşmacı 3","speaker_name":"Sol Üst","suggested":"Sol Üst","flags":["cloud_transcript"]]).label,"Sol Üst")
    }
}
final class CloudTranscriptionTests:XCTestCase {
    func testOpenRouterModeRecordsWithoutLivePreview() {
        XCTAssertFalse(CloudTranscription.recordArguments(mode:"openrouter",directory:"/d",title:"T",receipt:"/r").contains("--live"))
        XCTAssertTrue(CloudTranscription.recordArguments(mode:"local",directory:"/d",title:"T",receipt:"/r").contains("--live"))
    }
    func testFinalizeAndImportNeverCarryKeysAndResumeKeepsStoredModel() {
        let f=CloudTranscription.finalizeArguments(meeting:"m1",model:"deepgram/nova-3",output:"/o")
        XCTAssertEqual(f,["openrouter-finalize","m1","--allow-upload","--output","/o","--model","deepgram/nova-3"])
        XCTAssertTrue(CloudTranscription.importArguments(path:"/a.m4a",title:"T",model:"deepgram/nova-3",output:"/o").contains("--no-local"))
        let cloud=Meeting(["id":"m2","status":"incomplete","recovery_state":"interrupted","metadata":["cloud_mode":"capture","model":"deepgram/nova-3"]])
        XCTAssertEqual(CloudTranscription.resumeArguments(meeting:cloud,model:"openai/gpt-transcribe",output:"/o").prefix(2),["openrouter-finalize","m2"])
        XCTAssertFalse(CloudTranscription.resumeArguments(meeting:cloud,model:"openai/gpt-transcribe",output:"/o").contains("--model"))
        let legacy=Meeting(["id":"m3","status":"incomplete","recovery_state":"interrupted","metadata":["engine":"openrouter","model":"openai/gpt-transcribe"]])
        XCTAssertEqual(CloudTranscription.resumeArguments(meeting:legacy,model:"openai/gpt-transcribe",output:"/o").first,"openrouter-import")
    }
    func testCloudRowsShowClusterLabelsUntilNamed() {
        let cluster=Row(["id":1,"start":0.0,"end":3.0,"text":"x","speaker":"Konuşmacı 2","source":"system","flags":["cloud_transcript","cloud_diarization"]])
        XCTAssertEqual(cluster.label,"Konuşmacı 2")
        let named=Row(["id":2,"start":0.0,"end":3.0,"text":"x","speaker":"Konuşmacı 2","speaker_name":"Ayşe","source":"system","flags":["cloud_transcript"]])
        XCTAssertEqual(named.label,"Ayşe")
        let mic=Row(["id":3,"start":0.0,"end":3.0,"text":"x","speaker":"Boran","source":"mic","flags":["cloud_transcript"]])
        XCTAssertEqual(mic.label,"Boran")
        let echo=Row(["id":5,"start":0.0,"end":3.0,"text":"x","speaker":"Boran","source":"mic","flags":["cloud_transcript","possible_echo"]])
        XCTAssertEqual(echo.label,"Hoparlör yankısı")
        let local=Row(["id":4,"start":0.0,"end":3.0,"text":"x","speaker":"S1","source":"system","flags":[]])
        XCTAssertEqual(local.label,"Konuşmacı 2")
    }
    func testEchoRowsHiddenByDefault() {
        let system=Row(["id":1,"start":0.0,"end":50.0,"text":"a","speaker":"Konuşmacı 1","speaker_name":"Sağ üst","source":"system","flags":["cloud_transcript"]])
        let echo=Row(["id":2,"start":0.0,"end":50.0,"text":"a","speaker":"Boran","source":"mic","flags":["cloud_transcript","possible_echo"]])
        XCTAssertEqual(CloudTranscription.visibleRows([echo,system],showEcho:false).map(\.id),[1])
        XCTAssertEqual(CloudTranscription.visibleRows([echo,system],showEcho:true).map(\.id),[2,1])
        XCTAssertEqual(CloudTranscription.hiddenEchoCount([echo,system]),1)
    }
    func testFinalizeOnlyForStoppedRecordingsWithAudio() {
        let rec=Meeting(["id":"r","status":"incomplete","recovery_state":"interrupted","metadata":["capture_dir":"/c"]])
        XCTAssertTrue(CloudTranscription.canFinalize(meeting:rec,busy:false))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:rec,busy:true))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:Meeting(["id":"r","status":"processing","recovery_state":"active","metadata":["capture_dir":"/c"]]),busy:false))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:Meeting(["id":"r","status":"complete","metadata":["capture_dir":"/c"]]),busy:false))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:Meeting(["id":"t","status":"incomplete","metadata":["text_only":true]]),busy:false))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:nil,busy:false))
    }
}
