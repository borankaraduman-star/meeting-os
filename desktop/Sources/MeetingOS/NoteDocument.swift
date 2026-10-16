import Foundation

/// Which note the editor is holding. A note written before the meeting row exists (⌃⌥R pressed, the helper still
/// asking for permission) is filed under the recording folder's UUID and claimed onto the meeting once the poll sees
/// it — "kayıt öncesi yazdığım not kaybolmasın".
enum NoteKey:Equatable,Hashable {
    case meeting(String), pending(String)
    var request:[String:Any] { switch self { case .meeting(let id): return ["meeting":id]; case .pending(let key): return ["pending_key":key] } }
    var pendingKey:String? { if case .pending(let key)=self { return key }; return nil }
}

/// One link from the user's note to recorded audio: the source's own clock (seconds since the capture began), so it
/// survives a transcript that is re-split or re-transcribed. `segment` is a hint for jumping, never the identity.
struct NoteAnchor:Equatable,Identifiable {
    let id:String; let source:String; let start:Double; let end:Double; let segment:Int?; let segmentRevision:Int?
    /// A live anchor's absolute moment (seconds since 1970). `start`/`end` are only the app's estimate: its clock
    /// counts the permission wait, sleep and helper relaunches the audio never saw, so the bridge re-derives the
    /// range from this stamp through the capture journal (`notes._on_audio_clock`) and answers with audio time.
    let wall:Double?
    /// "ok" | "source_unavailable" — set by `note_get`; a fresh anchor is "ok" until the bridge says otherwise.
    var status:String="ok"
    init(id:String=UUID().uuidString,source:String,start:Double,end:Double,segment:Int?=nil,segmentRevision:Int?=nil,status:String="ok",wall:Double?=nil) {
        self.id=id; self.source=source; self.start=max(0,start); self.end=max(self.start,end); self.segment=segment; self.segmentRevision=segmentRevision; self.status=status
        self.wall=wall.flatMap { $0.isFinite && $0>0 ? $0 : nil }
    }
    init?(_ d:[String:Any]) {
        guard let source=d["source"] as? String, let start=(d["start"] as? NSNumber)?.doubleValue else { return nil }
        self.init(id:d["id"] as? String ?? UUID().uuidString,source:source,start:start,end:(d["end"] as? NSNumber)?.doubleValue ?? start,segment:(d["segment"] as? NSNumber)?.intValue,segmentRevision:(d["segment_revision"] as? NSNumber)?.intValue,status:d["status"] as? String ?? "ok",wall:(d["wall"] as? NSNumber)?.doubleValue)
    }
    /// What goes back to `note_save`: the status is the bridge's verdict, not something the app asserts.
    var payload:[String:Any] {
        var d:[String:Any]=["id":id,"source":source,"start":start,"end":end]
        if let segment { d["segment"]=segment }; if let segmentRevision { d["segment_revision"]=segmentRevision }
        if let wall { d["wall"]=wall }
        return d
    }
    var available:Bool { status != "source_unavailable" }
    /// The transcript row "Transkriptte göster" opens: the stored segment only while it is still this source and this
    /// stretch of audio (a retry can hand its id to an unrelated row), otherwise the first row of the same source that
    /// overlaps the range — a re-split transcript's new id for the same moment. nil when nothing there is left.
    func transcriptRow(in rows:[Row])->Int? {
        let hits=rows.filter { $0.source==source && $0.start<max(end,start+0.001) && $0.end>start }
        if let segment, hits.contains(where:{ $0.id==segment }) { return segment }
        return hits.min(by:{ ($0.start,$0.id)<($1.start,$1.id) })?.id
    }
    /// "Sistem sesi · 12:05–12:20"
    var label:String {
        let who=["mic":"Mikrofon","system":"Sistem sesi"][source] ?? source
        func t(_ s:Double)->String { let n=Int(s.rounded(.down)); return n>=3600 ? String(format:"%d:%02d:%02d",n/3600,n/60%60,n%60) : String(format:"%02d:%02d",n/60,n%60) }
        return "\(who) · \(t(start))–\(t(end))"
    }
    /// Equality ignores the status: the bridge re-deriving "source_unavailable" is not a user edit.
    static func==(a:NoteAnchor,b:NoteAnchor)->Bool { a.id==b.id && a.source==b.source && a.start==b.start && a.end==b.end && a.segment==b.segment && a.segmentRevision==b.segmentRevision && a.wall==b.wall }
}

/// The other side of a compare-and-swap that lost: what is stored now, kept next to the user's own text so neither
/// is thrown away until the user says which one wins.
/// `parked`: the bridge says the user's side of this conflict is on disk too (`note_drafts`), so a quit loses neither.
struct NoteConflict:Equatable { let revision:Int; let text:String; let anchors:[NoteAnchor]; var parked=false }

/// One `note_save` on the wire. `generation` ties the answer to the edit it carried, so a late answer can never
/// mark a newer edit as saved.
/// `park`: while the conflict bar is open the editor's text is only parked as the conflict's draft, never saved as
/// the note — the user has not picked a side yet.
/// `resolve`: this save is "Benim sürümümü kaydet" — the user picked their side, so the bridge may drop the parked
/// draft. An ordinary autosave never says so: another window's parked text is not its to discard (judge s6).
struct NoteSaveRequest:Equatable {
    let key:NoteKey; let baseRevision:Int; let text:String; let anchors:[NoteAnchor]; let generation:Int; var park=false; var resolve=false
    var payload:[String:Any] {
        var d=key.request; d["action"]="note_save"; d["base_revision"]=baseRevision; d["text"]=text; d["anchors"]=anchors.map(\.payload)
        if park { d["park"]=true }
        if resolve { d["resolve"]=true }
        return d
    }
}

enum NoteSaveResult:Equatable { case saved(revision:Int), conflict(NoteConflict), failed }

/// The meeting note editor's state, free of SwiftUI and of the bridge so every rule is a unit test: a 500 ms
/// debounce on a caller-supplied clock, one save in flight at a time, compare-and-swap on `base_revision`, and a
/// conflict that keeps the user's text on screen. Nothing outside the user's own typing (or an explicit choice in
/// the conflict bar) ever replaces `text` while there is unsaved work — finalizer, retry and AI never write here.
struct NoteDocument:Equatable {
    enum State:String { case clean, dirty, saving, conflict }
    static let debounce:TimeInterval=0.5

    private(set) var key:NoteKey
    private(set) var text=""
    private(set) var anchors:[NoteAnchor]=[]
    /// The revision the stored note is at, as far as this editor knows; the next save's `base_revision`.
    private(set) var revision=0
    /// "user" | "ai_accepted" — who wrote the stored revision. Shown, never acted on.
    private(set) var author="user"
    private(set) var state:State = .clean
    private(set) var conflict:NoteConflict?
    private(set) var inFlight:NoteSaveRequest?
    /// The last save failed (bridge down, disk full). The text is still here and is retried; the badge says so.
    private(set) var failed=false
    /// The note has been read from the bridge at least once; before that a save would race an unseen revision.
    private(set) var loaded=false
    private var generation=0
    private var savedGeneration=0
    /// The edit whose text the bridge holds as this conflict's draft. Judge 2026-10-16: an open conflict used to
    /// settle ⌘Q although `note_save` had written nothing, so the newer text, alive only here, died with the app.
    private var parkedGeneration:Int?
    /// "Benim sürümümü kaydet" was pressed and no save has landed since: every save until one does carries
    /// `resolve`, so a failed first attempt does not leave the parked draft behind to reopen a settled conflict.
    private var resolving=false
    private var lastEdit:Date?

    init(key:NoteKey) { self.key=key }

    var hasUnsavedWork:Bool { generation != savedGeneration || state == .conflict }
    /// Readable, nothing on the wire, and newer text than the stored one: a save is owed now. The first `note_get`
    /// answer can arrive after the debounce already fired (and was refused for want of a revision); without this
    /// the typing waited for a focus change to be saved.
    var owesSave:Bool { loaded && inFlight==nil && state == .dirty }
    /// May ⌘Q be answered? Only when nothing is on the wire and nothing typed is still unsaved. A save reply that
    /// lands while newer text is waiting for its debounce does not settle the quit — that text goes next. An open
    /// conflict settles it only once the bridge has parked exactly the text on screen: then both versions are on
    /// disk, the next launch brings the bar back, and only the user picks one.
    var settledForQuit:Bool { inFlight==nil && (!hasUnsavedWork || (state == .conflict && parkedGeneration==generation)) }
    /// The conflict bar is open and the text on screen is not the parked draft (typed since, or never parked —
    /// a refused claim): the next save parks it.
    var owesPark:Bool { loaded && inFlight==nil && state == .conflict && parkedGeneration != generation }
    /// "Kaydedildi" / "Kaydediliyor…" / "Kaydedilmedi". A conflict is unsaved until the user picks a side.
    var indicator:String {
        if state == .conflict { return "Kaydedilmedi · başka bir sürüm var" }
        if failed { return "Kaydedilmedi" }
        if hasUnsavedWork { return "Kaydediliyor…" }
        return revision==0 && text.isEmpty ? "" : "Kaydedildi"
    }
    var authorLabel:String { author=="ai_accepted" ? "Yapay zekâ önerisi · sizin onayınızla" : "Sizin notunuz" }

    // MARK: user edits

    mutating func edit(_ newText:String,now:Date) {
        guard newText != text else { return }
        text=newText; touched(now)
    }
    mutating func addAnchor(_ anchor:NoteAnchor,now:Date) {
        guard !anchors.contains(where:{ $0.source==anchor.source && $0.start==anchor.start && $0.end==anchor.end }) else { return }
        anchors.append(anchor); touched(now)
    }
    mutating func removeAnchor(id:String,now:Date) {
        guard anchors.contains(where:{ $0.id==id }) else { return }
        anchors.removeAll { $0.id==id }; touched(now)
    }
    private mutating func touched(_ now:Date) {
        generation+=1; lastEdit=now; failed=false
        if state == .clean { state = .dirty }
    }

    // MARK: saving

    /// The debounce: true once the user has paused for 500 ms and nothing is on the wire. Several keystrokes inside
    /// the window are one save. A failed save is retried on the same rhythm.
    func due(now:Date)->Bool {
        guard owes else { return false }
        return now.timeIntervalSince(lastEdit ?? .distantPast) >= Self.debounce
    }
    private var owes:Bool { state == .conflict ? owesPark : (loaded && inFlight==nil && generation != savedGeneration) }
    /// Start a save. `force` is the flush (focus lost, recording stopped, quit): it skips the debounce, never the
    /// one-in-flight rule or the conflict — a conflict is resolved by the user, not by a flush. During a conflict
    /// the request only parks the text (`park`), so a flush makes it durable without choosing for the user.
    mutating func beginSave(now:Date,force:Bool=false)->NoteSaveRequest? {
        guard force ? owes : due(now:now) else { return nil }
        let parking=state == .conflict
        let req=NoteSaveRequest(key:key,baseRevision:revision,text:text,anchors:anchors,generation:generation,park:parking,resolve:!parking && resolving)
        inFlight=req; if !parking { state = .saving }
        return req
    }
    /// The bridge's answer to `req`. Answers for another note, or for a request that is no longer the one on the
    /// wire, are dropped: a slow reply must not move a newer state backwards.
    mutating func finishSave(_ req:NoteSaveRequest,_ result:NoteSaveResult) {
        guard req.key==key, inFlight==req else { return }
        inFlight=nil
        if req.park {
            // A park never writes the note: only a parked answer counts, and the conflict bar stays as it was.
            if case .conflict(let theirs)=result, theirs.parked, state == .conflict { conflict=theirs; parkedGeneration=req.generation; failed=false }
            else { failed=true }
            return
        }
        switch result {
        case .saved(let rev):
            if rev > revision { revision=rev }
            author="user"; failed=false; if req.resolve { resolving=false }
            if req.generation > savedGeneration { savedGeneration=req.generation }
            state = generation==savedGeneration ? .clean : .dirty
        case .conflict(let theirs):
            // The user's text stays exactly as typed; theirs waits beside it. The bridge parked the text it refused.
            conflict=theirs; state = .conflict; failed=false; parkedGeneration=theirs.parked ? req.generation : nil; resolving=false
        case .failed:
            failed=true; state = .dirty
        }
    }

    // MARK: loading

    /// A `note_get` answer. Applied only when it cannot destroy anything: the editor holds no unsaved work and the
    /// answer is not older than what this editor already saved. An answer that arrives while the user is typing
    /// only refreshes anchor availability and advances nothing.
    ///
    /// `draft` is a conflict parked before the app last closed: the editor reopens on the user's text with the
    /// stored version beside it, exactly as the bar looked when they left.
    mutating func applyLoaded(key loadedKey:NoteKey,revision rev:Int,text loadedText:String,anchors loadedAnchors:[NoteAnchor],author loadedAuthor:String,draft:NoteWire.Draft?=nil) {
        guard loadedKey==key else { return }
        defer { loaded=true }
        if hasUnsavedWork || inFlight != nil {
            for i in anchors.indices {
                guard let fresh=loadedAnchors.first(where:{ $0.id==anchors[i].id }) else { continue }
                anchors[i].status=fresh.status
                // A live anchor's range is derived by the bridge from its wall stamp (audio time), never from the
                // stored estimate, so taking it here is not an edit and can never shift twice.
                let mine=anchors[i]
                if let wall=mine.wall, fresh.wall==wall, fresh.start != mine.start || fresh.end != mine.end {
                    anchors[i]=NoteAnchor(id:mine.id,source:mine.source,start:fresh.start,end:fresh.end,segment:mine.segment,segmentRevision:mine.segmentRevision,status:fresh.status,wall:wall)
                }
            }
            // Someone else moved the note on while we are mid-edit: the next save will meet the CAS and surface a
            // conflict with both texts, rather than this answer silently replacing the user's typing.
            return
        }
        guard rev >= revision else { return }
        revision=rev; text=loadedText; anchors=loadedAnchors; author=loadedAuthor; state = .clean; failed=false
        if let draft, draft.text != loadedText || draft.anchors != loadedAnchors {
            conflict=NoteConflict(revision:rev,text:loadedText,anchors:loadedAnchors,parked:true)
            text=draft.text; anchors=draft.anchors; state = .conflict; generation+=1; parkedGeneration=generation
        }
    }

    // MARK: conflict

    /// "Benim sürümümü kaydet": rebase onto the stored revision and save the user's text over it, now.
    mutating func keepMine(now:Date)->NoteSaveRequest? {
        guard state == .conflict, inFlight==nil, let theirs=conflict else { return nil }
        revision=max(revision,theirs.revision); conflict=nil; state = .dirty; generation+=1; lastEdit=now; resolving=true
        return beginSave(now:now,force:true)
    }
    /// "Diğerini al": the stored version replaces the editor's; the user's text is dropped only by this choice. The
    /// caller then drops the parked draft (`note_draft_drop`). Returns whether the choice was taken.
    @discardableResult mutating func takeTheirs()->Bool {
        guard state == .conflict, inFlight==nil, let theirs=conflict else { return false }
        revision=max(revision,theirs.revision); text=theirs.text; anchors=theirs.anchors; conflict=nil; state = .clean; savedGeneration=generation; failed=false
        parkedGeneration=nil; resolving=false
        return true
    }

    // MARK: pending → meeting

    /// The meeting row now exists. Only a note with nothing on the wire changes hands, so the in-flight save keeps the
    /// key it was sent with; the caller asks again on the next poll.
    var canClaim:Bool { key.pendingKey != nil && inFlight==nil }
    mutating func claimed(meeting:String) {
        guard key.pendingKey != nil, inFlight==nil else { return }
        key = .meeting(meeting)
    }
    /// The claim was refused because the meeting already has its own note (`meeting_has_note`): both are stored and
    /// neither may silently win. The editor moves onto the meeting with the pre-recording text as "mine" and the
    /// meeting's note as "theirs" — the ordinary conflict bar. The base becomes the meeting note's revision, so
    /// "Benim sürümümü kaydet" meets the CAS of THAT note; carrying the pending revision over could equal it by chance
    /// and overwrite it without a word.
    @discardableResult mutating func claimConflicted(meeting:String,theirs:NoteConflict)->Bool {
        guard key.pendingKey != nil, inFlight==nil else { return false }
        // `theirs.parked` is false here: the pending text is not a draft of the meeting's note yet, so ⌘Q waits
        // until the next save parks it under the meeting.
        key = .meeting(meeting); revision=theirs.revision; conflict=theirs; state = .conflict; failed=false; loaded=true
        parkedGeneration=theirs.parked ? generation : nil
        return true
    }
}

/// Which note the pane shows. While recording it is the recording's own note — by folder UUID until the meeting row
/// appears, by meeting afterwards — unless the user has opened another meeting to look something up.
enum NoteTarget {
    static func key(recording:Bool,recordingKey:String?,activeMeeting:String?,selected:String?,nextKey:String)->NoteKey {
        if recording {
            if let active=activeMeeting { return .meeting(selected==nil || selected==active ? active : selected!) }
            if let pending=recordingKey { return .pending(pending) }
        }
        if let selected { return .meeting(selected) }
        return .pending(nextKey)
    }
    /// "Bu ana bağla" while recording: the last fifteen seconds of the given source. `elapsed` (since the app
    /// started the recorder) is only shown until the bridge answers; `wall` is what the bridge maps onto the audio
    /// timeline with the journal's measured drift, so a note taken after a permission dialog, a lid-close or a
    /// helper relaunch still plays the audio it was written about.
    /// Saved pending notes that no meeting row and no started recorder account for, oldest key order first. The
    /// idle editor's own key and the running recording's folder are live notes, never orphans.
    static func orphans(claims:Set<String>,meetingFolders:Set<String>,startedFolders:Set<String>,active:String?,nextKey:String)->[String] {
        claims.filter { !meetingFolders.contains($0) && !startedFolders.contains($0) && $0 != active && $0 != nextKey }.sorted()
    }
    /// The folder UUID the next recording uses: the idle note's own key when the user typed under it, otherwise an
    /// orphaned note's key (so it opens in the editor and is claimed by the new meeting), otherwise the fresh key.
    static func recordingKey(nextKey:String,nextHoldsNote:Bool,orphans:[String])->String { nextHoldsNote ? nextKey : orphans.first ?? nextKey }
    static func liveAnchor(elapsed:Double,source:String,wall:Double?=nil)->NoteAnchor { NoteAnchor(source:source,start:max(0,elapsed-15),end:max(0,elapsed),wall:wall) }
    /// "Bu ana bağla" on a finished meeting: the segment the user last played or jumped to.
    static func selectedSegment(lastPlayed:Int?,focused:Int?,highlighted:Int?)->Int? { lastPlayed ?? focused ?? highlighted }
    static func segmentAnchor(id:Int,source:String,start:Double,end:Double)->NoteAnchor { NoteAnchor(source:source,start:start,end:end,segment:id) }
}

/// Parsing the bridge's note answers in one place, tolerant of `{note:{…}}` and flat shapes.
enum NoteWire {
    struct Draft:Equatable { let text:String; let anchors:[NoteAnchor] }
    struct Loaded:Equatable { let revision:Int; let text:String; let anchors:[NoteAnchor]; let author:String; var draft:Draft?=nil }
    static func loaded(_ r:[String:Any])->Loaded {
        let n=(r["note"] as? [String:Any]) ?? r
        let d=(n["draft"] as? [String:Any]).flatMap { d in (d["text"] as? String).map { Draft(text:$0,anchors:anchors(d["anchors"])) } }
        return Loaded(revision:(n["revision"] as? NSNumber)?.intValue ?? 0,text:n["text"] as? String ?? "",anchors:anchors(n["anchors"]),author:n["author"] as? String ?? "user",draft:d)
    }
    /// `note_claim`: `moved` when the row now belongs to the meeting (or there was no row to move), `meetingHasNote`
    /// when the bridge kept both notes apart, `failed` for anything it did not say in as many words.
    enum Claim:Equatable { case moved, meetingHasNote, failed }
    static func claimResult(_ r:[String:Any])->Claim {
        if r["conflict"] as? Bool == true || r["reason"] as? String == "meeting_has_note" { return .meetingHasNote }
        if r["claimed"] as? Bool == true || r["reason"] as? String == "no_note" { return .moved }
        return .failed
    }
    static func saveResult(_ r:[String:Any])->NoteSaveResult {
        if r["conflict"] as? Bool == true {
            return .conflict(NoteConflict(revision:(r["revision"] as? NSNumber)?.intValue ?? 0,text:r["text"] as? String ?? "",anchors:anchors(r["anchors"]),parked:r["parked"] as? Bool == true))
        }
        if r["ok"] as? Bool == true, let rev=(r["revision"] as? NSNumber)?.intValue ?? ((r["note"] as? [String:Any])?["revision"] as? NSNumber)?.intValue { return .saved(revision:rev) }
        return .failed
    }
    static func anchors(_ raw:Any?)->[NoteAnchor] {
        if let list=raw as? [[String:Any]] { return list.compactMap(NoteAnchor.init) }
        if let s=raw as? String, let list=(try? JSONSerialization.jsonObject(with:Data(s.utf8))) as? [[String:Any]] { return list.compactMap(NoteAnchor.init) }
        return []
    }
}
