import XCTest
@testable import MeetingOS

final class NoteDocumentTests:XCTestCase {
    let t0=Date(timeIntervalSince1970:1_000_000)
    func at(_ s:Double)->Date { t0.addingTimeInterval(s) }
    func loadedDoc(_ key:NoteKey = .meeting("m1"),revision:Int=0,text:String="")->NoteDocument {
        var d=NoteDocument(key:key); d.applyLoaded(key:key,revision:revision,text:text,anchors:[],author:"user"); return d
    }

    func testKeystrokesInsideTheDebounceAreOneSave() {
        var d=loadedDoc()
        d.edit("K",now:at(0)); d.edit("Ka",now:at(0.2)); d.edit("Karar",now:at(0.4))
        XCTAssertNil(d.beginSave(now:at(0.8)),"0,4 sn sonra yazılan harfin üstünden 500 ms geçmedi")
        XCTAssertEqual(d.indicator,"Kaydediliyor…")
        let req=d.beginSave(now:at(0.9))
        XCTAssertEqual(req?.text,"Karar"); XCTAssertEqual(req?.baseRevision,0)
        XCTAssertNil(d.beginSave(now:at(5)),"aynı anda ikinci kayıt yok")
        d.finishSave(req!,.saved(revision:1))
        XCTAssertEqual(d.state,.clean); XCTAssertEqual(d.revision,1); XCTAssertEqual(d.indicator,"Kaydedildi")
        XCTAssertEqual(req?.payload["action"] as? String,"note_save"); XCTAssertEqual(req?.payload["meeting"] as? String,"m1")
    }

    func testFlushSkipsTheDebounceButNotTheConflict() {
        var d=loadedDoc()
        d.edit("Karar: deneme cuma",now:at(0))
        let req=d.beginSave(now:at(0.01),force:true)
        XCTAssertEqual(req?.text,"Karar: deneme cuma","odak kaybı / kayıt stop / çıkış beklemeden kaydeder")
        d.finishSave(req!,.conflict(NoteConflict(revision:4,text:"başka",anchors:[])))
        d.edit("Karar: deneme cuma!",now:at(1))
        // The flush only parks the text on screen as the conflict's draft; it never saves it as the note.
        let park=d.beginSave(now:at(9),force:true)
        XCTAssertEqual(park?.park,true,"çakışmayı flush çözmez, kullanıcı seçer"); XCTAssertEqual(park?.payload["park"] as? Bool,true)
        d.finishSave(park!,.conflict(NoteConflict(revision:4,text:"başka",anchors:[],parked:true)))
        XCTAssertEqual(d.state,.conflict); XCTAssertEqual(d.text,"Karar: deneme cuma!"); XCTAssertNil(d.beginSave(now:at(10),force:true))
        XCTAssertFalse(NoteDocument(key:.meeting("x")).due(now:at(9)),"değişiklik yokken kayıt yok")
    }

    func testConflictKeepsTheUsersTextAndOffersBothSides() {
        var d=loadedDoc(revision:3,text:"eski")
        d.edit("benim yazım",now:at(0))
        let req=d.beginSave(now:at(1))!
        XCTAssertEqual(req.baseRevision,3)
        d.finishSave(req,.conflict(NoteConflict(revision:4,text:"diğer Mac",anchors:[])))
        XCTAssertEqual(d.state,.conflict); XCTAssertEqual(d.text,"benim yazım"); XCTAssertEqual(d.conflict?.text,"diğer Mac")
        XCTAssertEqual(d.indicator,"Kaydedilmedi · başka bir sürüm var")
        // A late note_get must not slip the other text under the user's while the conflict is open.
        d.applyLoaded(key:.meeting("m1"),revision:4,text:"diğer Mac",anchors:[],author:"user")
        XCTAssertEqual(d.text,"benim yazım")
        var mine=d
        let again=mine.keepMine(now:at(2))
        XCTAssertEqual(again?.baseRevision,4); XCTAssertEqual(again?.text,"benim yazım")
        mine.finishSave(again!,.saved(revision:5)); XCTAssertEqual(mine.state,.clean); XCTAssertEqual(mine.revision,5)
        var theirs=d; theirs.takeTheirs()
        XCTAssertEqual(theirs.text,"diğer Mac"); XCTAssertEqual(theirs.state,.clean); XCTAssertEqual(theirs.revision,4); XCTAssertFalse(theirs.hasUnsavedWork)
    }

    func testAnOlderRevisionAnswerDoesNotOverwriteANewerState() {
        var d=loadedDoc(revision:2,text:"r2")
        d.edit("r3",now:at(0)); let r=d.beginSave(now:at(1))!; d.finishSave(r,.saved(revision:3))
        d.applyLoaded(key:.meeting("m1"),revision:2,text:"r2",anchors:[],author:"user")
        XCTAssertEqual(d.text,"r3"); XCTAssertEqual(d.revision,3)
        // An answer for another note (the user switched meetings) is dropped too.
        d.applyLoaded(key:.meeting("m2"),revision:9,text:"başka toplantı",anchors:[],author:"user")
        XCTAssertEqual(d.text,"r3")
        // A save reply that is not the request on the wire cannot mark a newer edit as saved.
        d.edit("r4",now:at(2)); let r4=d.beginSave(now:at(3))!
        d.finishSave(r,.saved(revision:7))
        XCTAssertEqual(d.state,.saving); XCTAssertEqual(d.revision,3)
        d.finishSave(r4,.saved(revision:4)); XCTAssertEqual(d.revision,4); XCTAssertEqual(d.state,.clean)
    }

    func testTypingDuringASaveStaysDirtyAndALoadMidEditKeepsTheTyping() {
        var d=loadedDoc()
        d.edit("a",now:at(0)); let r=d.beginSave(now:at(1))!
        d.edit("ab",now:at(1.1))
        d.applyLoaded(key:.meeting("m1"),revision:8,text:"sunucu",anchors:[],author:"ai_accepted")
        XCTAssertEqual(d.text,"ab","finalizer/AI metni kullanıcının yazısını ezmez")
        d.finishSave(r,.saved(revision:1))
        XCTAssertEqual(d.state,.dirty); XCTAssertTrue(d.hasUnsavedWork)
        XCTAssertEqual(d.beginSave(now:at(2))?.text,"ab")
    }

    func testFailedSaveSaysSoAndRetries() {
        var d=loadedDoc(); d.edit("x",now:at(0)); let r=d.beginSave(now:at(1))!
        d.finishSave(r,.failed)
        XCTAssertEqual(d.indicator,"Kaydedilmedi"); XCTAssertEqual(d.text,"x")
        XCTAssertNotNil(d.beginSave(now:at(2)))
    }

    func testNothingIsSavedBeforeTheNoteWasRead() {
        var d=NoteDocument(key:.meeting("m1"))
        d.edit("erken yazı",now:at(0))
        XCTAssertNil(d.beginSave(now:at(5),force:true),"bilinmeyen revizyona kör yazma yok")
        d.applyLoaded(key:.meeting("m1"),revision:2,text:"kayıtlı",anchors:[],author:"user")
        XCTAssertEqual(d.text,"erken yazı")
        XCTAssertEqual(d.beginSave(now:at(6))?.baseRevision,0,"CAS çakışma döndürür, kayıtlı metin ezilmez")
    }

    func testPendingNoteIsClaimedOntoTheMeeting() {
        var d=loadedDoc(.pending("UUID-1"))
        XCTAssertEqual(NoteKey.pending("UUID-1").request["pending_key"] as? String,"UUID-1")
        d.edit("hazırlıkta yazıldı",now:at(0)); let r=d.beginSave(now:at(1))!
        XCTAssertEqual(r.payload["pending_key"] as? String,"UUID-1"); XCTAssertNil(r.payload["meeting"])
        XCTAssertFalse(d.canClaim,"kayıt yoldayken anahtar değişmez")
        d.claimed(meeting:"m9"); XCTAssertEqual(d.key,.pending("UUID-1"))
        d.finishSave(r,.saved(revision:1))
        XCTAssertTrue(d.canClaim)
        d.claimed(meeting:"m9")
        XCTAssertEqual(d.key,.meeting("m9")); XCTAssertEqual(d.text,"hazırlıkta yazıldı"); XCTAssertEqual(d.revision,1)
        d.edit("hazırlıkta yazıldı, devamı",now:at(2))
        XCTAssertEqual(d.beginSave(now:at(3))?.payload["meeting"] as? String,"m9")
    }

    // Judge gap: a note saved while a recording was preparing, stopped or refused before its meeting row existed,
    // was only claimed by a meeting naming that folder — after a relaunch nothing ever opened it again.
    func testOrphanedPreparationNoteIsReachableAfterRelaunch() {
        let claims:Set<String>=["PREP-1","DONE-1","LIVE-1","NEXT-1","STARTED-1"]
        let orphans=NoteTarget.orphans(claims:claims,meetingFolders:["DONE-1"],startedFolders:["STARTED-1"],active:"LIVE-1",nextKey:"NEXT-1")
        XCTAssertEqual(orphans,["PREP-1"],"toplantısı, kaydedicisi olan ya da şu an açık not sahipsiz sayılmaz")
        XCTAssertEqual(NoteTarget.orphans(claims:["PREP-1"],meetingFolders:[],startedFolders:[],active:nil,nextKey:"FRESH"),["PREP-1"],"yeniden açılışta taze UUID notu gizlemez")
        // The next recording takes the orphan's folder, so the editor shows it and the new meeting claims it.
        let key=NoteTarget.recordingKey(nextKey:"FRESH",nextHoldsNote:false,orphans:orphans)
        XCTAssertEqual(key,"PREP-1")
        XCTAssertEqual(NoteTarget.key(recording:true,recordingKey:key,activeMeeting:nil,selected:"m-old",nextKey:"FRESH"),.pending("PREP-1"),"hazırlık notu yeni kayıtta editörde")
        XCTAssertEqual(NoteTarget.recordingKey(nextKey:"FRESH",nextHoldsNote:true,orphans:orphans),"FRESH","bu kayıt için yazılan not öncelikli; sahipsiz olan sonraki kayda kalır")
        XCTAssertEqual(NoteTarget.recordingKey(nextKey:"FRESH",nextHoldsNote:false,orphans:[]),"FRESH")
    }

    // Review s3 #1: a save reply landing while newer text waits for its debounce used to answer ⌘Q.
    func testQuitWaitsForTextTypedWhileASaveWasOnTheWire() {
        var d=loadedDoc()
        XCTAssertTrue(d.settledForQuit,"boş, temiz not çıkışı bekletmez")
        d.edit("ilk",now:at(0)); let r=d.beginSave(now:at(1),force:true)!
        d.edit("ilk ve son cümle",now:at(1.1))
        d.finishSave(r,.saved(revision:1))
        XCTAssertFalse(d.settledForQuit,"eski isteğin cevabı yeni metni kaydedilmiş saymaz")
        let last=d.beginSave(now:at(1.2),force:true)
        XCTAssertEqual(last?.text,"ilk ve son cümle")
        XCTAssertFalse(d.settledForQuit,"son kayıt yoldayken çıkış beklenir")
        d.finishSave(last!,.saved(revision:2))
        XCTAssertTrue(d.settledForQuit)
        d.edit("x",now:at(2)); let c=d.beginSave(now:at(3),force:true)!
        d.finishSave(c,.conflict(NoteConflict(revision:5,text:"diğer",anchors:[])))
        XCTAssertFalse(d.settledForQuit,"köprü kullanıcının metnini saklamadıysa çıkış bekler")
        var parked=loadedDoc(); parked.edit("x",now:at(2)); let pc=parked.beginSave(now:at(3),force:true)!
        parked.finishSave(pc,.conflict(NoteConflict(revision:5,text:"diğer",anchors:[],parked:true)))
        XCTAssertTrue(parked.settledForQuit,"çakışmayı yalnız kullanıcı çözer; iki sürüm de diskte")
        var unread=NoteDocument(key:.meeting("m1")); unread.edit("okunmadan yazıldı",now:at(0))
        XCTAssertFalse(unread.settledForQuit,"okunmamış nottaki yazı da beklenir")
    }

    // Judge 2026-10-16: an open conflict settled ⌘Q although `note_save` had written nothing, so the text typed
    // into the conflict bar — alive only in memory — was lost on quit.
    func testQuitDuringAConflictWaitsUntilTheTextOnScreenIsParked() {
        var d=loadedDoc(revision:3,text:"eski")
        d.edit("benim yazım",now:at(0)); let r=d.beginSave(now:at(1),force:true)!
        d.finishSave(r,.conflict(NoteConflict(revision:4,text:"diğer Mac",anchors:[],parked:true)))
        XCTAssertTrue(d.settledForQuit,"reddedilen metin köprüde taslak olarak saklandı")
        d.edit("benim yazım ve çatışma sırasında eklenen cümle",now:at(2))
        XCTAssertFalse(d.settledForQuit,"çatışma çubuğu açıkken yazılan metin yalnız bellekte; çıkış bekler")
        XCTAssertTrue(d.owesPark)
        let park=d.beginSave(now:at(2.1),force:true)!
        XCTAssertTrue(park.park); XCTAssertEqual(park.text,"benim yazım ve çatışma sırasında eklenen cümle"); XCTAssertEqual(park.baseRevision,3)
        XCTAssertFalse(d.settledForQuit,"park yoldayken çıkış beklenir")
        var failed=d; failed.finishSave(park,.failed)
        XCTAssertFalse(failed.settledForQuit); XCTAssertEqual(failed.state,.conflict); XCTAssertTrue(failed.owesPark,"başarısız park yeniden denenir")
        var unparked=d; unparked.finishSave(park,.conflict(NoteConflict(revision:4,text:"diğer Mac",anchors:[])))
        XCTAssertFalse(unparked.settledForQuit,"parked demeyen cevap metni saklanmış saymaz")
        d.finishSave(park,.conflict(NoteConflict(revision:4,text:"diğer Mac",anchors:[],parked:true)))
        XCTAssertTrue(d.settledForQuit); XCTAssertEqual(d.state,.conflict); XCTAssertEqual(d.revision,3,"park notu kaydetmez, taban değişmez")
        XCTAssertEqual(d.text,"benim yazım ve çatışma sırasında eklenen cümle")
        XCTAssertEqual(NoteWire.saveResult(["conflict":true,"parked":true,"revision":4,"text":"diğer Mac","anchors":[]]),
                       .conflict(NoteConflict(revision:4,text:"diğer Mac",anchors:[],parked:true)))
        // Next launch: `note_get` carries the parked draft, and the editor reopens on the conflict bar with the user's text.
        let got=NoteWire.loaded(["revision":4,"text":"diğer Mac","anchors":[],"author":"user",
                                 "draft":["text":"benim yazım ve çatışma sırasında eklenen cümle","anchors":[]]])
        var reopened=NoteDocument(key:.meeting("m1"))
        reopened.applyLoaded(key:.meeting("m1"),revision:got.revision,text:got.text,anchors:got.anchors,author:got.author,draft:got.draft)
        XCTAssertEqual(reopened.state,.conflict); XCTAssertEqual(reopened.text,"benim yazım ve çatışma sırasında eklenen cümle")
        XCTAssertEqual(reopened.conflict?.text,"diğer Mac"); XCTAssertTrue(reopened.settledForQuit); XCTAssertNil(reopened.beginSave(now:at(9),force:true))
        var keep=reopened; let k=keep.keepMine(now:at(10))!
        XCTAssertFalse(k.park); XCTAssertEqual(k.baseRevision,4)
        XCTAssertTrue(k.resolve,"yalnız 'Benim sürümümü kaydet' taslağı düşürmeyi ister"); XCTAssertEqual(k.payload["resolve"] as? Bool,true)
        // A failed resolving save is retried as the same choice; once one lands, saves are ordinary autosaves again.
        keep.finishSave(k,.failed); let retry=keep.beginSave(now:at(11),force:true)!
        XCTAssertTrue(retry.resolve); keep.finishSave(retry,.saved(revision:5))
        keep.edit("devam",now:at(12)); let plain=keep.beginSave(now:at(13),force:true)!
        XCTAssertFalse(plain.resolve); XCTAssertNil(plain.payload["resolve"],"sıradan otomatik kayıt başka pencerenin taslağını silmez")
        var take=reopened; XCTAssertTrue(take.takeTheirs()); XCTAssertEqual(take.text,"diğer Mac"); XCTAssertFalse(take.hasUnsavedWork)
        // A draft equal to the stored note is no conflict.
        var same=NoteDocument(key:.meeting("m1"))
        same.applyLoaded(key:.meeting("m1"),revision:4,text:"diğer Mac",anchors:[],author:"user",draft:NoteWire.Draft(text:"diğer Mac",anchors:[]))
        XCTAssertEqual(same.state,.clean)
    }

    // Review s3 #2: a refused claim (meeting_has_note) must not move the editor onto the meeting as if it worked.
    func testClaimRefusedByTheMeetingsOwnNoteIsAConflictNotASilentOverwrite() {
        XCTAssertEqual(NoteWire.claimResult(["claimed":true,"revision":1]),.moved)
        XCTAssertEqual(NoteWire.claimResult(["claimed":false,"reason":"no_note"]),.moved)
        XCTAssertEqual(NoteWire.claimResult(["claimed":false,"conflict":true,"reason":"meeting_has_note"]),.meetingHasNote)
        XCTAssertEqual(NoteWire.claimResult([:]),.failed)
        var d=loadedDoc(.pending("UUID-1"))
        d.edit("hazırlık notu",now:at(0)); let r=d.beginSave(now:at(1))!; d.finishSave(r,.saved(revision:1))
        // Both notes at revision 1: under the old claim the next autosave (base 1) passed the meeting note's CAS.
        XCTAssertTrue(d.claimConflicted(meeting:"m9",theirs:NoteConflict(revision:1,text:"toplantının kendi notu",anchors:[])))
        XCTAssertEqual(d.key,.meeting("m9")); XCTAssertEqual(d.state,.conflict)
        XCTAssertEqual(d.text,"hazırlık notu"); XCTAssertEqual(d.conflict?.text,"toplantının kendi notu")
        d.edit("hazırlık notu, devamı",now:at(2))
        XCTAssertFalse(d.settledForQuit,"reddedilen bağlamadaki metin henüz toplantının taslağı değil")
        // The autosave meets an equal revision (1 = 1): only a park, never a CAS save, may go on the wire.
        let park=d.beginSave(now:at(9))
        XCTAssertEqual(park?.park,true,"otomatik kayıt diğer notu ezmez"); XCTAssertEqual(park?.payload["meeting"] as? String,"m9")
        d.finishSave(park!,.conflict(NoteConflict(revision:1,text:"toplantının kendi notu",anchors:[],parked:true)))
        XCTAssertNil(d.beginSave(now:at(9),force:true)); XCTAssertTrue(d.settledForQuit); XCTAssertEqual(d.state,.conflict)
        var mine=d; let keep=mine.keepMine(now:at(10))
        XCTAssertEqual(keep?.baseRevision,1); XCTAssertEqual(keep?.payload["meeting"] as? String,"m9"); XCTAssertEqual(keep?.text,"hazırlık notu, devamı")
        var theirs=d; theirs.takeTheirs(); XCTAssertEqual(theirs.text,"toplantının kendi notu"); XCTAssertEqual(theirs.revision,1)
        // A higher pending revision is not carried over either: the base is the meeting note's own revision.
        var high=loadedDoc(.pending("UUID-2"),revision:6,text:"altı")
        high.claimConflicted(meeting:"m2",theirs:NoteConflict(revision:2,text:"iki",anchors:[]))
        XCTAssertEqual(high.keepMine(now:at(1))?.baseRevision,2)
        var busy=loadedDoc(.pending("UUID-3")); busy.edit("y",now:at(0)); _=busy.beginSave(now:at(1))
        XCTAssertFalse(busy.claimConflicted(meeting:"m3",theirs:NoteConflict(revision:1,text:"z",anchors:[])),"yoldaki kayıt anahtarını korur")
        XCTAssertEqual(busy.key,.pending("UUID-3"))
    }

    // Review s3 #5: the first note_get answering after the debounce left the typing unsaved until a focus change.
    func testTextTypedBeforeTheFirstReadIsOwedASaveWhenTheReadArrives() {
        var d=NoteDocument(key:.meeting("m1"))
        d.edit("erken",now:at(0))
        XCTAssertNil(d.beginSave(now:at(0.6)),"500 ms dolunca gelen kayıt okumadan önce reddedilir")
        XCTAssertFalse(d.owesSave)
        d.applyLoaded(key:.meeting("m1"),revision:0,text:"",anchors:[],author:"user")
        XCTAssertTrue(d.owesSave,"okuma gelince kayıt yeniden planlanmalı")
        XCTAssertEqual(d.beginSave(now:at(1.2))?.text,"erken")
        XCTAssertFalse(d.owesSave)
    }

    // Review s3 #3: a live anchor is corrected onto the audio clock only by note_get; the editor takes that range.
    func testALiveAnchorTakesTheBridgesAudioTimeOnReRead() {
        let wall=1_700_000_100.0
        var d=loadedDoc()
        let live=NoteTarget.liveAnchor(elapsed:100,source:"mic",wall:wall)   // app clock: 85–100, counts the permission wait
        d.addAnchor(live,now:at(0)); let r=d.beginSave(now:at(1))!; d.finishSave(r,.saved(revision:1))
        let audio=NoteAnchor(id:live.id,source:"mic",start:40,end:55,wall:wall)
        d.applyLoaded(key:.meeting("m1"),revision:1,text:"",anchors:[audio],author:"user")
        XCTAssertEqual(d.anchors.map(\.start),[40]); XCTAssertEqual(d.anchors.first?.label,"Mikrofon · 00:40–00:55")
        // Mid-edit the text stays exactly as typed, yet the range still moves to the audio clock.
        d.edit("yazıyorum",now:at(2))
        d.applyLoaded(key:.meeting("m1"),revision:1,text:"",anchors:[NoteAnchor(id:live.id,source:"mic",start:41,end:56,wall:wall)],author:"user")
        XCTAssertEqual(d.text,"yazıyorum"); XCTAssertEqual(d.anchors.first?.start,41); XCTAssertEqual(d.anchors.first?.wall,wall)
        // A segment anchor (no wall) is the user's own range and is never moved by a read.
        var s=loadedDoc(); let seg=NoteTarget.segmentAnchor(id:7,source:"system",start:10,end:20)
        s.addAnchor(seg,now:at(0)); s.edit("z",now:at(0))
        s.applyLoaded(key:.meeting("m1"),revision:0,text:"",anchors:[NoteAnchor(id:seg.id,source:"system",start:99,end:120,segment:7)],author:"user")
        XCTAssertEqual(s.anchors.first?.start,10)
    }

    func testNoteTargetFollowsTheRecording() {
        XCTAssertEqual(NoteTarget.key(recording:true,recordingKey:"U",activeMeeting:nil,selected:"old",nextKey:"N"),.pending("U"),"hazırlık: toplantı satırı yok")
        XCTAssertEqual(NoteTarget.key(recording:true,recordingKey:"U",activeMeeting:"m",selected:nil,nextKey:"N"),.meeting("m"))
        XCTAssertEqual(NoteTarget.key(recording:true,recordingKey:"U",activeMeeting:"m",selected:"other",nextKey:"N"),.meeting("other"))
        XCTAssertEqual(NoteTarget.key(recording:false,recordingKey:"U",activeMeeting:nil,selected:"s",nextKey:"N"),.meeting("s"))
        XCTAssertEqual(NoteTarget.key(recording:false,recordingKey:nil,activeMeeting:nil,selected:nil,nextKey:"N"),.pending("N"),"kayıt öncesi not sonraki kayıt klasörüne")
    }

    func testAnchorsCarrySourceTimeAndUnavailableSourcesAreLabelled() {
        let live=NoteTarget.liveAnchor(elapsed:125,source:"system")
        XCTAssertEqual(live.start,110); XCTAssertEqual(live.end,125); XCTAssertEqual(live.label,"Sistem sesi · 01:50–02:05")
        XCTAssertEqual(NoteTarget.liveAnchor(elapsed:4,source:"mic").start,0)
        // The live anchor carries its absolute moment to the bridge, which re-derives the audio range from it.
        let stamped=NoteTarget.liveAnchor(elapsed:125,source:"system",wall:1_790_000_000.5)
        XCTAssertEqual(stamped.payload["wall"] as? Double,1_790_000_000.5); XCTAssertNil(live.payload["wall"])
        let back=NoteWire.anchors([["id":"w","source":"system","start":100.0,"end":115.0,"wall":1_790_000_000.5,"clock":"audio"]])
        XCTAssertEqual(back.first?.wall,1_790_000_000.5); XCTAssertEqual(back.first?.start,100)
        XCTAssertNil(NoteTarget.liveAnchor(elapsed:1,source:"mic",wall:.nan).wall)
        let seg=NoteTarget.segmentAnchor(id:42,source:"mic",start:10,end:14)
        XCTAssertEqual(seg.payload["segment"] as? Int,42); XCTAssertNil(seg.payload["status"])
        XCTAssertEqual(NoteTarget.selectedSegment(lastPlayed:nil,focused:7,highlighted:3),7)
        var d=loadedDoc(); d.addAnchor(seg,now:at(0)); d.addAnchor(NoteTarget.segmentAnchor(id:42,source:"mic",start:10,end:14),now:at(0))
        XCTAssertEqual(d.anchors.count,1,"aynı aralık iki kez bağlanmaz")
        let got=NoteWire.loaded(["note":["revision":2,"text":"t","author":"ai_accepted","anchors":[["id":"a","source":"system","start":5.0,"end":9.0,"status":"source_unavailable"]]]])
        XCTAssertEqual(got.revision,2); XCTAssertEqual(got.author,"ai_accepted"); XCTAssertFalse(got.anchors[0].available)
        var e=loadedDoc(); e.applyLoaded(key:.meeting("m1"),revision:2,text:got.text,anchors:got.anchors,author:got.author)
        XCTAssertEqual(e.authorLabel,"Yapay zekâ önerisi · sizin onayınızla")
        XCTAssertEqual(NoteWire.saveResult(["ok":true,"revision":5]),.saved(revision:5))
        XCTAssertEqual(NoteWire.saveResult(["conflict":true,"revision":6,"text":"x","anchors":[]]),.conflict(NoteConflict(revision:6,text:"x",anchors:[])))
        XCTAssertEqual(NoteWire.saveResult([:]),.failed)
    }

    func testTranscriptJumpNeedsTheSameSourceAndAudioRange() {
        let a=NoteTarget.segmentAnchor(id:7,source:"system",start:10.5,end:13)
        func row(_ id:Int,_ src:String,_ s:Double,_ e:Double)->Row { Row(["id":id,"start":s,"end":e,"text":"x","source":src]) }
        XCTAssertEqual(a.transcriptRow(in:[row(7,"system",10,14)]),7)
        XCTAssertNil(a.transcriptRow(in:[row(7,"mic",10,14)]),"yeniden kullanılan kimlik başka kaynakta: bağlantı oraya gitmez")
        XCTAssertNil(a.transcriptRow(in:[row(7,"system",300,304)]),"yeniden kullanılan kimlik başka anda: bağlantı oraya gitmez")
        XCTAssertEqual(a.transcriptRow(in:[row(7,"system",300,304),row(12,"system",12,16),row(11,"system",9,12)]),11,"yeniden bölünmüş transkriptte aynı an")
        XCTAssertNil(NoteAnchor(source:"system",start:40,end:41).transcriptRow(in:[row(7,"system",10,14)]))
    }
}
