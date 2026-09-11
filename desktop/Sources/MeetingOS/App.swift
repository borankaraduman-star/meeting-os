import SwiftUI
import UserNotifications
import UniformTypeIdentifiers
import AppKit
import AVFoundation

struct Meeting: Identifiable {
    let id: String; let title: String; let status: String; let displayStatus:String; let recoveryState:String; let created: String; let capture:[String:Any]; let metadata: [String:Any]
    let segments:Int; let seconds:Double; let speakers:Int; let names:[String]
    /// One honest line when OpenRouter refused this meeting: "Anahtar geçersiz · Ayarlar", "Kredi bitti", "Yeniden denenecek · 14:30".
    let cloudLine:String?
    /// "auth" | "credit" | "unavailable" | "other" — what kind of refusal, for the standing sidebar hint.
    let cloudKind:String?
    init(_ d:[String:Any]) { id=d["id"] as? String ?? ""; title=d["title"] as? String ?? ""; status=d["status"] as? String ?? ""; displayStatus=d["display_status"] as? String ?? status; recoveryState=d["recovery_state"] as? String ?? "unknown"; created=d["created"] as? String ?? ""; metadata=d["metadata"] as? [String:Any] ?? [:]; capture=d["capture"] as? [String:Any] ?? [:]; cloudLine=d["cloud_line"] as? String; cloudKind=d["cloud_kind"] as? String
        let st=d["stats"] as? [String:Any] ?? [:]; segments=st["segments"] as? Int ?? 0; seconds=st["seconds"] as? Double ?? 0; speakers=st["speakers"] as? Int ?? 0; names=st["names"] as? [String] ?? [] }
}
extension Meeting {
    /// Cheap change detector for the sidebar: publishing an identical list every poll re-rendered the whole window.
    var fingerprint:String { "\(id)|\(title)|\(status)|\(displayStatus)|\(recoveryState)|\(segments)|\(Int(seconds))|\(speakers)|\(metadata.count)|\((metadata["keep"] as? Bool) ?? false)|\((metadata["markers"] as? [Any])?.count ?? 0)|\((capture["state"] as? String) ?? "")|\(Int((capture["seconds"] as? Double) ?? 0))|\(cloudLine ?? "")|\((capture["restarts"] as? Int) ?? 0):\((capture["relaunches"] as? Int) ?? 0):\((capture["wakes"] as? Int) ?? 0)" }
    var captureSourcesEmpty:Bool { (capture["sources"] as? [String:Any] ?? [:]).isEmpty }
    /// Sidebar line under the title: what the finished recording holds, or a plain "no speech" for an empty one.
    var sidebarDetail:String {
        guard status=="complete" else { return cloudLine ?? statusLabel(displayStatus) }   // the cloud verdict is more use than "Kurtarılabilir"
        if segments==0 { return "Konuşma bulunmadı" }
        let length=seconds>=60 ? "\(Int(seconds/60)) dk" : "\(Int(seconds)) sn"
        return speakers>0 ? "\(length) · \(speakers) kişi" : length
    }
}
struct Row: Identifiable, Equatable {
    let id:Int; let start:Double; let end:Double; let text:String; let speaker:String; let name:String; let source:String; let flags:[String]; let suggested:String
    init(_ d:[String:Any]) { id=d["id"] as? Int ?? 0; start=d["start"] as? Double ?? 0; end=d["end"] as? Double ?? 0; text=d["text"] as? String ?? ""; speaker=d["speaker"] as? String ?? ""; name=d["speaker_name"] as? String ?? ""; source=d["source"] as? String ?? ""; flags=d["flags"] as? [String] ?? []; suggested=d["suggested"] as? String ?? "" }
    var label:String {
        if !name.isEmpty { return name }
        if source=="mic", speaker=="Ben" { return "Ben (siz)" }   // the bridge's placeholder for this Mac's own voice: never a stranger's name
        if flags.contains("provisional") { return "Geçici konuşmacı" }
        if !suggested.isEmpty { return suggested+"?" }  // borderline voice match awaiting one-click confirmation
        if flags.contains("possible_echo") { return "Hoparlör yankısı" }  // microphone picked up the speakers; not the user talking
        if flags.contains("cloud_transcript"), !speaker.isEmpty, speaker != "unknown" { return speaker }  // cloud path stores human-readable cluster labels
        if let tail=speaker.split(separator:":").last, tail.hasPrefix("S"), let n=Int(tail.dropFirst()) { return "Konuşmacı \(n+1)" }
        return "İsimsiz konuşmacı"
    }
    /// Built once for the process, not once per row: `notices` is read for all 1200+ rows of a long meeting
    /// on every body pass, and a dictionary literal there allocated (and hashed) the whole table each time.
    static let noticeLabels=["cloud_transcript":"Bulut transkript · OpenRouter", "cloud_diarization":"Konuşmacı ayrımı · sağlayıcı", "possible_echo":"Hoparlör yankısı olabilir · mikrofon sistem sesini almış", "coarse_timing":"Yaklaşık konuşma aralığı", "imported_text":"Elle aktarılan metin", "speaker_unverified":"Konuşmacı adı doğrulanmadı", "provisional":"Canlı metin · değişebilir", "short_context_diarization":"Konuşmacı için kısa ses örneği", "speaker_ambiguous":"Konuşmacı belirsiz / sesler çakışıyor", "low_asr_confidence":"Bu bölümü dinleyerek kontrol edin", "possible_non_speech":"Konuşma dışı ses olabilir", "repetition":"Tekrar algılandı", "confidence_unavailable":"Güven ölçümü yok", "baseline_diarization":"Temel konuşmacı ayrımı"]
    var notices:String {
        let labels=Row.noticeLabels
        let shown=flags.contains("cloud_transcript") ? flags.filter { !TranscriptBlocks.meetingWideFlags.contains($0) } : flags
        return shown.filter { $0 != "untimed" }.map { labels[$0] ?? $0 }.joined(separator:" · ")
    }
    var time:String { flags.contains("untimed") ? "" : String(format:"%02d:%02d",Int(start)/60,Int(start)%60) }
}
struct Profile:Identifiable, Equatable { let name:String; let model:String; let samples:Int; var id:String { name+model } }
/// Where the Python side lives. `runtime.json` in a development build names absolute paths (the venv and the
/// checkout); in a downloaded bundle it names RELATIVE ones — "runtime/bin/python3" and "repo" — which are
/// resolved against `Bundle.main.resourceURL`, so the app works from wherever the user dragged it.
struct Runtime:Decodable {
    let python:String; let repo:String
    /// True only in a packaged app: it decides the update channel, the setup card's git rows, the shipped
    /// invite and the PATH the children get. Absent in every runtime.json build-desktop.sh has ever written.
    let bundled:Bool
    /// CFBundleShortVersionString's twin, written by build-bundle.sh so the Python side and the setup card
    /// agree about which package this is.
    let version:String?
    /// Where the packaged app fetches `latest.json` and the next zip (GitHub Releases since 1.2.73); read by the
    /// Python updater, carried here only so the one CodingKeys list stays the complete description of the file.
    let downloadBase:String?
    init(python:String,repo:String,bundled:Bool=false,version:String?=nil,downloadBase:String?=nil) {
        self.python=python; self.repo=repo; self.bundled=bundled; self.version=version; self.downloadBase=downloadBase
    }
    enum Keys:String,CodingKey { case python, repo, bundled, version, download_base }
    init(from decoder:Decoder) throws {
        let c=try decoder.container(keyedBy:Keys.self)
        python=try c.decode(String.self,forKey:.python)
        repo=try c.decode(String.self,forKey:.repo)
        bundled=try c.decodeIfPresent(Bool.self,forKey:.bundled) ?? false
        version=try c.decodeIfPresent(String.self,forKey:.version)
        downloadBase=try c.decodeIfPresent(String.self,forKey:.download_base)
    }
    /// A path that does not begin with "/" is inside the app. Anything absolute is left exactly as it is.
    static func absolute(_ path:String,resources:URL?)->String {
        guard !path.hasPrefix("/"), let resources else { return path }
        return resources.appendingPathComponent(path).path
    }
    func resolved(resources:URL?)->Runtime {
        Runtime(python:Runtime.absolute(python,resources:resources),repo:Runtime.absolute(repo,resources:resources),bundled:bundled,version:version,downloadBase:downloadBase)
    }
    /// `runtime/bin`, the directory the bundled python3 and the bundled ffmpeg share.
    var binDirectory:String { (python as NSString).deletingLastPathComponent }
    /// What every child process (the bridge and every job) gets on top of the app's own environment. Putting
    /// the bundle's own bin directory FIRST on PATH is the whole point: `shutil.which('ffmpeg')`, which every
    /// assembly pass calls, has to find the ffmpeg inside the app on a Mac that has never heard of Homebrew.
    /// A development build changes nothing — the venv's python and the Mac's own ffmpeg are already on PATH.
    func childEnvironment(path:String?)->[String:String] {
        guard bundled, !binDirectory.isEmpty else { return [:] }
        let rest=(path ?? "").isEmpty ? "/usr/bin:/bin:/usr/sbin:/sbin" : path!
        return ["PATH":binDirectory+":"+rest]
    }
    var childEnvironment:[String:String] { childEnvironment(path:ProcessInfo.processInfo.environment["PATH"]) }
}

/// One bridge call. `timeout` is the watchdog: ten seconds is right for the poll and for everything the user
/// is waiting on, and wrong for the hourly housekeeping sweep, whose FLAC archive pass takes seconds per
/// meeting and was being SIGTERMed mid-archive every hour. Callers that know they are slow pass their own.
func invoke(_ runtime:Runtime,_ request:[String:Any],timeout:TimeInterval = 10) throws -> [String:Any] {
    let p=Process(); p.executableURL=URL(fileURLWithPath:runtime.python); p.arguments=["-m","meeting_os.desktop"]; p.currentDirectoryURL=URL(fileURLWithPath:runtime.repo)
    let extra=OpenRouterCredential.environment().merging(runtime.childEnvironment) { _,new in new }
    if !extra.isEmpty { p.environment=ProcessInfo.processInfo.environment.merging(extra) { _,new in new } }
    let input=Pipe(), output=Pipe(); p.standardInput=input; p.standardOutput=output; p.standardError=FileHandle.nullDevice
    try p.run()
    let deadline=DispatchWorkItem { if p.isRunning { kill(-p.processIdentifier,SIGTERM); p.terminate() } }
    DispatchQueue.global().asyncAfter(deadline:.now()+timeout, execute:deadline)
    defer { deadline.cancel() }
    try input.fileHandleForWriting.write(contentsOf:JSONSerialization.data(withJSONObject:request)); try input.fileHandleForWriting.close()
    let data=output.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
    guard let result=try JSONSerialization.jsonObject(with:data) as? [String:Any] else { throw NSError(domain:"MeetingOS",code:1,userInfo:[NSLocalizedDescriptionKey:"Invalid local response"]) }
    if let message=result["error"] as? String { throw NSError(domain:"MeetingOS",code:2,userInfo:[NSLocalizedDescriptionKey:message]) }
    return result
}

@MainActor final class Model:ObservableObject {
    @Published var meetings:[Meeting]=[]; @Published var rows:[Row]=[] { didSet { rebuildBlocks(); shares=TalkShare.compute(rows) } }; @Published var profiles:[Profile]=[]
    @Published var selected:String? { willSet { noteNavChange() } didSet { if selected != oldValue { recordingNavigation.selectionChanged(); error=""; canUndoNaming=false; summaryStale=false; summaryRefreshTask?.cancel(); summaryRefreshTask=nil; pendingSummaryRefresh=false; pendingSummaryMeeting=""; rows=[]; analysis=nil; search=""; pendingEvidence=nil; focusedSegment=nil; wordFix=nil; segmentsHash=""; intelHash=""; renaming=false; renameText="" } } }; @Published var search="" { willSet { noteNavChange() } didSet { guard search != oldValue else { return }; focusedSegment=nil; pendingEvidence=nil; scheduleSearchRebuild() } }; @Published var title=""
    /// Every failure the user is shown lands here, from fifty different call sites. That makes it the one
    /// place the error journal can be fed without threading a report call through all of them: a new,
    /// non-empty banner is one recorded event (throttled, so a poll that fails every two seconds is still one).
    @Published var error="" { didSet { if error != oldValue, !error.isEmpty { report(error) } } }
    /// Journal state for Ayarlar → Sistem → Hatalar. Loaded on launch, hourly, and when the sheet opens.
    @Published var errorEntries:[ErrorEntry]=[]; @Published var errorCounts:[String:Int]=[:]; @Published var errorCrashes=0
    var errorThrottle=ErrorReportThrottle()
    @Published var activity="Hazır · ⌃⌥R ile kayıt başlat"; @Published var recording=false; @Published var busy=false
    @Published var showOpenRouter=false
    @Published var deleteCandidate:Meeting?
    /// Meeting auto-selected on this launch because its processing was interrupted; drives the one-line restore banner.
    @Published var restoredMeeting:String?; var restoredOnLaunch=false
    @Published var storage:StorageReport?
    @Published var transcriptionMode=UserDefaults.standard.string(forKey:CloudTranscription.modeKey) ?? "openrouter" { didSet { UserDefaults.standard.set(transcriptionMode,forKey:CloudTranscription.modeKey) } }
    @Published var cloudModel=UserDefaults.standard.string(forKey:CloudTranscription.modelKey) ?? CloudTranscription.defaultModel { didSet { UserDefaults.standard.set(cloudModel,forKey:CloudTranscription.modelKey) } }
    @Published var cloudModels:[OpenRouterModelOption]=[]
    @Published var vocabulary=""; @Published var showSettings=false; @Published var editRow:Row?; @Published var editName=""; @Published var editText=""; @Published var clean=false
    /// The word the user clicked in the transcript, if any: it moves on a click and on nothing else, so the
    /// paragraph views can take it as a plain parameter without a per-poll redraw.
    @Published var wordFix:WordFix?
    @Published var tab="transcript" { willSet { noteNavChange() } didSet { if tab != "transcript" { pendingEvidence=nil } } }; @Published var analysis:[String:Any]?; @Published var actions:[ActionItem]=[]; @Published var drafts:[DraftItem]=[]
    @Published var memoryQuery=""; @Published var hits:[Evidence]=[]; @Published var answer=""; @Published var answerEvidence:[Evidence]=[]
    let runtime:Runtime; let dataDir=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/MeetingOS")
    @Published var focusedSegment:Int? { willSet { noteNavChange() } didSet { rebuildBlocks() } }
    @Published var pendingEvidence:Evidence? { willSet { noteNavChange() } }
    var recordingNavigation=RecordingNavigation()
    var progressURL:URL?;var jobStarted:Date?
    var resourceStopMessage=""
    var pressureSource:DispatchSourceMemoryPressure?
    var requestedQuit=false
    @Published var jobKind:String?; @Published var jobCanceled=false
    /// Whether the running job was launched throttled (idle retry, or a job started under a live meeting).
    /// Only the ETA reads it: such a job is meant to take longer, so its estimate is allowed a longer cap.
    var jobLowPriority=false
    @Published var job:Process?; var recordingDir:URL?; var timer:Timer?; var player:AVAudioPlayer?; var refreshing=false
    let playback=PlaybackState()   // which span is playing; observed only by the play buttons, not the transcript layout
    init() {
        let resources=Bundle.main.resourceURL
        let url=resources!.appendingPathComponent("runtime.json")
        let declared=(try? JSONDecoder().decode(Runtime.self,from:Data(contentsOf:url))) ?? Runtime(python:"/usr/bin/false",repo:"/tmp")
        runtime=declared.resolved(resources:resources)
        AppDelegate.model=self
        let pressure=DispatchSource.makeMemoryPressureSource(eventMask:[.warning,.critical],queue:.main)
        pressure.setEventHandler { [weak self] in Task { @MainActor in self?.memoryPressureAt=Date(); self?.stopForResources() } }
        pressure.resume();pressureSource=pressure
        timer=Timer.scheduledTimer(withTimeInterval:2,repeats:true) { [weak self] _ in Task { @MainActor in
            guard let self=self else { return }
            self.pollTick+=1
            if RefreshCadence.shouldRefresh(tick:self.pollTick,recording:self.recording,busy:self.busy,active:NSApp.isActive) { await self.refresh() }
        } }
        // Sleep/wake is the one moment a recording can lose minutes without anything else noticing. No timer and
        // no extra polling: the wake notification simply runs the poll that was due anyway, right now.
        let workspace=NSWorkspace.shared.notificationCenter
        workspace.addObserver(forName:NSWorkspace.willSleepNotification,object:nil,queue:.main) { [weak self] _ in Task { @MainActor in
            guard let self=self, self.recordProcess != nil else { return }
            self.sleptAt=Date()
        } }
        workspace.addObserver(forName:NSWorkspace.didWakeNotification,object:nil,queue:.main) { [weak self] _ in Task { @MainActor in
            guard let self=self, self.recordProcess != nil else { return }
            self.sleptAt=nil
            await self.refresh()
        } }
        Task { await loadReportSettings(); await refresh() }
        Task { await loadErrors() }   // macOS wrote a crash report while the app was dead; nothing ever read one
    }
    var meeting:Meeting? { meetings.first { $0.id==selected } }
    @Published var showEchoRows=false { didSet { rebuildBlocks() } }
    @Published var review:[ReviewItem]=[]
    /// Words the user has taught (Düzelt → "Kelime düzelt") plus the ones the app learned from repeated
    /// edits. Loaded on demand from Ayarlar → Sesler ve sözlük; never part of the two-second poll.
    @Published var wordRules:[WordRule]=[]
    /// "ekipten 3 profil, 5 kelime" — how much of what this Mac knows arrived from the team folder. Empty when
    /// nothing did, so a Mac working alone never reads a line about a team it does not have.
    @Published var teamSummary=""
    @Published var scorecard=""
    @Published var markerCount=0
    /// ⌘M while recording: append one line to markers.jsonl in the capture folder; nothing else changes.
    func markMoment(_ kind:String) {
        // `jobStarted` belongs to finalize/analyze jobs and is nil while recording, so ⌘M wrote nothing at all —
        // and wrote against the wrong origin whenever such a job happened to be running. The recording's own start is the origin.
        guard recording, let dir=recordingDir, let started=recordStartedAt else { return }
        let seconds=Date().timeIntervalSince(started)
        let url=dir.appendingPathComponent("markers.jsonl")
        let line=Markers.line(seconds:seconds,kind:kind)+"\n"
        if let handle=try? FileHandle(forWritingTo:url) { handle.seekToEndOfFile();handle.write(Data(line.utf8));try? handle.close() }
        else { try? line.write(to:url,atomically:true,encoding:.utf8) }
        markerCount+=1
        activity="İşaretlendi · \(Marker.labels[kind] ?? "An") · \(String(format:"%02d:%02d",Int(seconds)/60,Int(seconds)%60))"
    }
    @Published var showShare=false
    func loadScorecard() async {
        guard let r=try? await request(["action":"quality_report"]), let i=r["identity"] as? [String:Any] else { scorecard=""; return }
        let ok=i["auto_correct"] as? Int ?? 0, wrong=i["auto_wrong"] as? Int ?? 0, conf=i["suggestion_confirmed"] as? Int ?? 0, rej=i["suggestion_rejected"] as? Int ?? 0, missed=i["missed_known"] as? Int ?? 0, edits=r["text_edits"] as? Int ?? 0
        scorecard="Adlandırma isabeti · otomatik \(ok) doğru / \(wrong) yanlış · öneri \(conf) onay / \(rej) red · \(missed) kaçırılan · \(edits) metin düzeltmesi"
        // Learning curve: the share of voices named without help, this week against the one before.
        let weeks=(r["progress"] as? [[String:Any]] ?? []).filter { ($0["clusters"] as? Int ?? 0)>0 }
        if let last=weeks.last {
            let pct:( [String:Any])->String = { w in (w["auto_share"] as? Double).map { "%\(Int($0*100))" } ?? "—" }
            let prev=weeks.count>1 ? " · önceki hafta \(pct(weeks[weeks.count-2]))" : ""
            let edits=(last["edits_per_1000_words"] as? Double).map { " · 1000 kelimede \(String(format:"%.1f",$0)) düzeltme" } ?? ""
            scorecard+="\nÖğrenme · bu hafta sesleri kendiliğinden tanıma \(pct(last))\(prev)\(edits)"
        }
    }
    @Published var analysisModel=AnalysisModelDefault.current() { didSet { UserDefaults.standard.set(analysisModel,forKey:"cloudAnalysisModel") } }
    /// analyze/prepare/ask run through OpenRouter whenever transcription does; the local Qwen path stays for local mode.
    var cloudAnalysisArguments:[String] { transcriptionMode=="openrouter" ? ["--openrouter-model",analysisModel] : [] }
    /// One line under the title: when, how long, who, what still needs a look. Built from data already loaded.
    var headerStrip:String? {
        guard let m=meeting, m.status=="complete" else { return nil }
        var parts=[MeetingDates.label(m.created)]
        if m.segments>0 { parts.append(m.seconds>=60 ? "\(Int(m.seconds/60)) dk" : "\(Int(m.seconds)) sn"); if m.speakers>0 { parts.append("\(m.speakers) kişi") } } else { parts.append("konuşma yok") }
        return parts.joined(separator:" · ")   // open tasks and review items are counted on the tabs themselves
    }
    var openTaskCount:Int { actions.filter { $0.meeting==selected && !$0.stale && !["done","dismissed"].contains($0.state) }.count }
    func loadReview() async {
        guard let mid=selected else { review=[]; return }
        do { let r=try await request(["action":"review_queue","meeting":mid]); review=(r["items"] as? [[String:Any]] ?? []).map(ReviewItem.init) } catch { review=[] }
    }
    /// Q9: naming one voice re-scores the meeting's other unnamed clusters. Say what that changed, or say nothing.
    func adaptationNote(_ r:[String:Any])->String {
        var parts:[String]=[]
        if let named=r["renamed"] as? Int, named>0 { parts.append("\(named) kişi daha tanındı") }
        if let suggested=r["suggested"] as? Int, suggested>0 { parts.append("\(suggested) kişi daha önerildi") }
        return parts.isEmpty ? "" : " · "+parts.joined(separator:", ")
    }
    func confirmReview(_ item:ReviewItem) async {
        guard let mid=selected, !item.suggested.isEmpty, !item.speakerKey.isEmpty else { return }
        do { let r=try await request(["action":"label_speaker","meeting":mid,"speaker":item.speakerKey,"name":item.suggested,"enroll":true]); activity="“\(item.suggested)” onaylandı · profil güncellendi"+adaptationNote(r); canUndoNaming=true; await refresh(); await loadReview(); refreshSummaryIfNamesDone() }
        catch { self.error=error.localizedDescription }
    }
    /// One pass over every suggested name; a single refresh at the end keeps the transcript from repainting per person.
    func confirmAll(_ items:[ReviewItem]) async {
        guard let mid=selected else { return }
        var named:[String]=[]; var last:[String:Any]=[:]
        for item in items where !item.suggested.isEmpty && !item.speakerKey.isEmpty {
            do { last=try await request(["action":"label_speaker","meeting":mid,"speaker":item.speakerKey,"name":item.suggested,"enroll":true]); named.append(item.suggested) }
            catch { self.error=error.localizedDescription; break }
        }
        // The last call's counts describe the meeting after every confirmation, which is what the user now sees.
        if !named.isEmpty { activity="Onaylandı · "+named.joined(separator:", ")+" · profiller güncellendi"+adaptationNote(last); canUndoNaming=true; undoBatch=named.count }
        await refresh(); await loadReview(); refreshSummaryIfNamesDone()
    }
    /// ⌘Z after a naming: labels, the learned sample and the rejection all go back. Only the newest naming of the open meeting.
    @Published var canUndoNaming=false { didSet { if canUndoNaming { undoBatch=1 } } }   // one naming unless the caller raises it right after
    /// How many namings the last confirmation made: "Tümünü onayla" names N voices, so ⌘Z must undo N.
    var undoBatch=1
    @Published var probeLines:[String]=[]
    @Published var maintenance:[String:Any]?
    func undoNaming() async {
        guard let mid=selected, canUndoNaming, !busy else { return }
        var results:[[String:Any]]=[]
        for _ in 0..<max(1,undoBatch) {
            do { results.append(try await request(["action":"undo_correction","meeting":mid])) }
            catch { if results.isEmpty { self.error=error.localizedDescription; return }; break }   // a half-undone batch stays undone; the offer is spent either way
        }
        canUndoNaming=false; undoBatch=1
        activity=UndoNaming.message(results)
        await refresh(); await loadReview()
    }
    /// The Özet tab is out of date because a name changed, and nothing is being paid to fix it yet: the
    /// tab shows one badge and one button. Set by "Yalnız bu bölüm", which must never buy an analysis by itself.
    @Published var summaryStale=false
    /// Naming five voices used to buy five analyses. The window folds a burst into one; a naming during the
    /// window restarts it. Cancellation is the whole mechanism, so this is a Task and not a Timer.
    var summaryRefreshTask:Task<Void,Never>?
    /// The window fired while a job held the slot: run the analysis when that job ends instead of stacking one.
    var pendingSummaryRefresh=false; var pendingSummaryMeeting=""
    /// Names done → the summary is the next thing people read; refresh it once, quietly, instead of asking them to notice "güncel değil".
    func refreshSummaryIfNamesDone() {
        guard let mid=selected, meeting?.status=="complete", analysis?["stale"] as? Bool == true, !recording, recordProcess==nil, !zoomMeetingOpen else { return }   // recordProcess: the helper still drains after `recording` goes false
        guard !review.contains(where:{ ($0.kind=="unnamed_speaker" || $0.kind=="suggested_name") && !$0.speakerKey.isEmpty }) else { return }
        scheduleSummaryRefresh(mid)
    }
    /// 20 seconds is long enough to hold a person naming the room one voice after another, short enough that
    /// nobody waits for the summary. The status line says what will happen and roughly what it costs.
    func scheduleSummaryRefresh(_ mid:String) {
        summaryRefreshTask?.cancel()
        activity="Özet 20 sn içinde isimlerle yenilenecek (≈1–3 cent)"
        summaryRefreshTask=Task { [weak self] in
            try? await Task.sleep(nanoseconds:20_000_000_000)
            guard !Task.isCancelled, let self else { return }
            self.summaryRefreshTask=nil
            self.runScheduledSummaryRefresh(mid)
        }
    }
    /// The window closed. Everything that made the refresh a good idea has to still hold; when it does not,
    /// the Özet tab keeps the offer instead of spending on a meeting nobody is looking at.
    func runScheduledSummaryRefresh(_ mid:String) {
        guard selected==mid, meeting?.status=="complete" else { return }   // another meeting is open now: never badge it for this one
        guard analysis?["stale"] as? Bool == true else { summaryStale=false; return }
        guard !recording, recordProcess==nil, !zoomMeetingOpen else { summaryStale=true; return }
        if job != nil || busy { pendingSummaryRefresh=true; pendingSummaryMeeting=mid; summaryStale=true; activity="Özet, süren işlem bitince isimlerle yenilenecek"; return }
        summaryStale=false; activity="İsimler tamam · özet isimlerle yenileniyor"; analyzeMeeting(mid)
    }
    var calendarAttendees:[String] { (meeting?.metadata["calendar"] as? [String:Any])?["attendees"] as? [String] ?? [] }
    @Published var readingMode=true
    @Published var showAsides=false
    @Published var hideFillers=UserDefaults.standard.object(forKey:"hideFillers") as? Bool ?? true { didSet { UserDefaults.standard.set(hideFillers,forKey:"hideFillers") } }
    /// The filter itself. Every reader goes through the cached `visibleRows` instead: this walks the whole
    /// transcript twice (echo filter, then the search match) and the view body runs many times per keystroke.
    var filteredRows:[Row] {
        if let id=focusedSegment { return rows.filter { $0.id==id } }
        let visible=CloudTranscription.visibleRows(rows,showEcho:showEchoRows)
        return search.isEmpty ? visible : visible.filter { ($0.text+" "+$0.label).localizedCaseInsensitiveContains(search) }
    }
    /// What the Bölümler list renders: the filter's result, computed once per rebuild alongside the paragraphs.
    @Published private(set) var visibleRows:[Row]=[]
    /// Typing "kar" used to rebuild 1200 paragraphs three times. One rebuild per pause instead; 150 ms is below
    /// the point where the list feels like it lags the keyboard, and above a fast typist's inter-key gap.
    var searchDebounce:Task<Void,Never>?
    func scheduleSearchRebuild() {
        searchDebounce?.cancel(); searchDebounce=nil
        // Clearing the field is not typing: the full transcript comes back at once, with no pause to explain.
        guard !search.isEmpty else { rebuildBlocks(); return }
        searchDebounce=Task { [weak self] in
            try? await Task.sleep(nanoseconds:150_000_000)
            guard !Task.isCancelled, let self else { return }
            self.searchDebounce=nil; self.rebuildBlocks()
        }
    }
    /// Reading-view paragraphs, rebuilt only when their inputs change. The 2-second status poll must not
    /// re-run block building for every published field (a 1500-row day would pin the CPU again).
    @Published private(set) var blocks:[TranscriptBlock]=[]
    private var blocksKey:Int=0
    func rebuildBlocks() {
        var h=Hasher(); h.combine(rows.count); h.combine(rows.last?.id ?? -1); h.combine(showEchoRows); h.combine(search); h.combine(focusedSegment ?? -1); h.combine(rows.map { $0.name+$0.text }.joined().hashValue)
        let key=h.finalize(); if key==blocksKey && !blocks.isEmpty { return }
        blocksKey=key
        let visible=filteredRows   // one pass feeds both the paragraph builder and the Bölümler list
        if visibleRows != visible { visibleRows=visible }
        blocks=TranscriptBlocks.build(visible)
    }
    func request(_ req:[String:Any]) async throws -> [String:Any] { try await Bridge.call(runtime,req) }
    /// For the few actions that are allowed to take minutes (the housekeeping sweep). Off the poll's queue and
    /// off its watchdog; never used for anything the user is standing in front of.
    func requestSlow(_ req:[String:Any],timeout:TimeInterval = 600) async throws -> [String:Any] { try await Bridge.callSlow(runtime,req,timeout:timeout) }
    var jobStopsOnPressure=false
    func stopForResources() {
        guard let process=job,
              ResourceGuard.pressureAction(hasJob:true,stopsOnPressure:jobStopsOnPressure,recording:recording,alreadyStopped:!resourceStopMessage.isEmpty) == .terminateJob else { return }
        resourceStopMessage="Bellek baskısı nedeniyle işlem durduruldu. Kaynak ses korunuyor; ağır uygulamaları kapatıp yeniden deneyin."
        error=resourceStopMessage
        process.terminate()   // `job` is never the recorder (separate slot): pressure never stops a live meeting
    }
    @Published var microphoneHint=""
    func refresh() async {
        if !settingsLoaded { await loadReportSettings() }   // a failed first load must not leave ⌃⌥R refusing for an hour
        if recording || pollTick%3==0 { let hint=MicrophoneHint.current(); if hint != microphoneHint { microphoneHint=hint } }   // IOKit query: every poll while recording, every third otherwise
        if let process=job, let bytes=ResourceGuard.footprint(pid:process.processIdentifier), bytes>ResourceGuard.budget(physical:ProcessInfo.processInfo.physicalMemory) { stopForResources() }
        if job != nil, let started=jobStarted {
            let elapsed=Int(Date().timeIntervalSince(started))
            let progress=progressURL.flatMap { try? Data(contentsOf:$0) }.flatMap { try? JSONDecoder().decode(JobProgress.self,from:$0) }
            let line=(progress?.line(elapsed:Double(elapsed),lowPriority:jobLowPriority) ?? activity)+" · \(elapsed/60) dk \(elapsed%60) sn"; if jobs.jobProgress != line { jobs.jobProgress=line }
        }
        guard !refreshing else { return }; refreshing=true
        let wanted=selected ?? ""
        defer {
            refreshing=false
            // A selection change during an awaited snapshot must load immediately.
            if wanted != (selected ?? "") { Task { await self.refresh() } }
        }
        do {
            let result=try await request(["action":"snapshot","meeting":wanted,"segments_hash":wanted==lastSegmentsMeeting ? segmentsHash : "","signals":pollTick%3==0])   // chunk-level signal analysis every 6 s, not every 2 s
            let nextMeetings=(result["meetings"] as? [[String:Any]] ?? []).map(Meeting.init)
            if nextMeetings.map(\.fingerprint) != meetings.map(\.fingerprint) { meetings=nextMeetings }   // publish only on change
            let nextProfiles=(result["profiles"] as? [[String:Any]] ?? []).map { Profile(name:$0["name"] as? String ?? "",model:$0["model"] as? String ?? "",samples:$0["samples"] as? Int ?? 0) }
            if nextProfiles != profiles { profiles=nextProfiles }
            if recording, let dir=recordingDir, let active=meetings.first(where:{ $0.metadata["capture_dir"] as? String==dir.path }) {
                if let target=recordingNavigation.resolve(active:active.id) { selected=target }
                // Disk is journalled on every chunk, not with the 6-second signal analysis: read it on every poll.
                let lowDisk=CaptureSignalPresentation.lowDisk(active.capture) ?? ""
                if recorder.lowDiskNotice != lowDisk { recorder.lowDiskNotice=lowDisk }
                if active.capture["signals"] != nil {   // polls without signal analysis keep the last reading
                    let label=CaptureSignalPresentation.label(active.capture); if activity != label { activity=label }
                    let dots=["mic":CaptureSignalPresentation.dotState(active.capture,key:"mic"),"system":CaptureSignalPresentation.dotState(active.capture,key:"system")]
                    if recorder.captureDots != dots { recorder.captureDots=dots }
                }
                // One line, once, when the recording had to survive something. The first reading of a meeting
                // only seeds the comparison, so a restored session never announces old history.
                let seen=RecordingContinuity.read(active.capture)
                if let was=continuitySeen, let line=RecordingContinuity.notice(from:was,to:seen) { recorder.recordingNotice=line; activity=line }
                continuitySeen=seen
            }
            // The name is asked for the moment we know it is missing, not at the record button: a Zoom call is
            // the worst place to discover a recording will not start. Once per launch, and only once there is
            // something to file the voice against.
            if settingsLoaded, !namePromptedOnLaunch, !hasUserName, !meetings.isEmpty {
                namePromptedOnLaunch=true; activity=Model.nameRequiredMessage; promptForUserName()
            }
            // The team folder is read once at launch: what a teammate taught or named while this Mac was closed
            // is in place before the first meeting, not an hour later when the housekeeping pass runs.
            if settingsLoaded, !teamSyncedOnLaunch, !recording, job==nil {
                teamSyncedOnLaunch=true; Task { await syncTeamKnowledge() }
            }
            if !restoredOnLaunch {
                restoredOnLaunch=true
                if !recording, job==nil, let restore=RelaunchRestore.pick(meetings:meetings) { selected=restore.id; restoredMeeting=restore.id }
            }
            if selected==nil && !recording { selected=meetings.first?.id }
            if ZoomWatch.shouldScan(tick:pollTick,autoRecord:zoomAutoRecord,zoomRunning:lastZoomState.running) { lastZoomState=await ZoomWatch.stateAsync() }   // the window-list walk runs off the main actor; only the running-app list is read here
            let zoomState=lastZoomState; let zoomNow=zoomState.open
            if zoomNow && !zoomMeetingOpen && !recording && zoomNotify && !zoomAutoRecord && !zoomState.sharing { ZoomNotifier.notifyIfNeeded() }   // never a banner onto a screen that is being shared
            if !zoomNow { ZoomNotifier.reset(); nameRefusalNotified=false }
            if zoomMeetingOpen != zoomNow { zoomMeetingOpen=zoomNow }   // same value would still fire objectWillChange and re-lay out every paragraph
            if screenSharing != zoomState.sharing { screenSharing=zoomState.sharing }
            updateRecorderPanel()
            applyWindowPrivacy()
            applyLivePriority(zoomOpen:zoomState.strict || recordProcess != nil)   // any live recording (Zoom, Meet, in person) gets the same protection
            heartbeatIfDue()
            updateBlockedHint()
            idleRetryIfDue()
            switch zoomAuto.evaluate(zoomOpen:zoomState.strict,meetingLikely:zoomState.running && (recording ? AudioInUse.microphoneBusy() : false),recording:recording,busy:false,enabled:zoomAutoRecord && !requestedQuit) {
            case .start:
                if let line=LaunchOutcome.activity(started:start(),onStart:"Zoom toplantısı açıldı · kayıt kendiliğinden başladı",onRefusal:startRefusal) { activity=line }
                if startRefusal==Model.nameRequiredMessage && !nameRefusalNotified { nameRefusalNotified=true; notifyDone("Kayıt başlamadı",Model.nameRequiredMessage) }   // nobody is looking at the status line during a Zoom call
            case .stop: stop(); activity="Zoom toplantısı kapandı · kayıt bitiriliyor"
            case nil: break
            }
            if recording, let started=recordStartedAt { let s=Int(Date().timeIntervalSince(started)); let t=String(format:"%02d:%02d",s/60,s%60); if recorder.elapsedText != t { recorder.elapsedText=t } }
            if DiscreetMode.mayNotify(recording:recording,meetingOpen:zoomMeetingOpen,sharing:screenSharing), !queuedNotifications.isEmpty { for (t,b) in queuedNotifications { deliver(t,b) }; queuedNotifications.removeAll() }   // meeting-safe mode: notifications wait
            if lastUpdateCheck==nil || Date().timeIntervalSince(lastUpdateCheck!) >= 6*3600 { Task { await checkForUpdates() } }
            if NSApp.isActive, let last=lastUpdateCheck, Date().timeIntervalSince(last) >= 60*60 { Task { await checkForUpdates() } }
            if wanted==selected {
                var changed=false
                if let raw=result["segments"] as? [[String:Any]] { let nextRows=raw.map(Row.init); changed=rows != nextRows; if changed { rows=nextRows } }
                segmentsHash=result["segments_hash"] as? String ?? ""; lastSegmentsMeeting=wanted
                resolvePendingEvidence()
                let intel=result["intel_hash"] as? String ?? ""
                if intel != intelHash || changed || analysis==nil && actions.isEmpty { intelHash=intel; try await refreshIntelligence(wanted); if analysis?["stale"] as? Bool != true { summaryStale=false } else if summaryRefreshTask==nil && !pendingSummaryRefresh { summaryStale=true } }
                if changed, !recording, meeting?.status=="complete" { await loadReview() }
            }
        } catch { self.error=error.localizedDescription }
    }
    /// Recording has its own process slot: a finalize/analyze job from the previous meeting must never block ⌃⌥R.
    /// Returns whether the child actually started: only then may the caller announce the work.
    @discardableResult func launch(_ args:[String], complete:@escaping (Bool)->Void)->Bool {
        let isRecord=JobPriority.isRealtime(args)
        let jobEnvironment=consumeJobEnvironment()   // a refused launch drops them too: they belong to this attempt only
        guard isRecord ? recordProcess==nil : job==nil else { return false }
        let idle=idleRetry; idleRetry=false   // consumed by this launch only
        do {
            try FileManager.default.createDirectory(at:dataDir,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])   // transcripts and receipts live here; an existing folder keeps its mode
            let log=dataDir.appendingPathComponent("last-job.log")
            FileManager.default.createFile(atPath:log.path,contents:nil,attributes:[.posixPermissions:0o600])   // the log can carry job output; never world-readable
            let handle=try FileHandle(forWritingTo:log)
            resourceStopMessage="";jobCanceled=false
            let progress=dataDir.appendingPathComponent("progress/"+UUID().uuidString+".json")
            let zoomOpen=zoomMeetingOpen || recordProcess != nil
            let throttled = !JobPriority.environment(args:args,zoomOpen:zoomOpen,idle:idle).isEmpty
            if !isRecord { jobKind=args.first;jobStopsOnPressure=ResourceGuard.stopsOnPressure(jobArguments:args); progressURL=progress;jobStarted=Date();jobLowPriority=throttled;jobs.jobProgress="İşlem başlatılıyor" }
            let p=Process();p.environment=ProcessInfo.processInfo.environment.merging(["MEETING_OS_PROGRESS_PATH":progress.path]) { _,new in new }.merging(jobEnvironment) { _,new in new }.merging(JobPriority.environment(args:args,zoomOpen:zoomOpen,idle:idle)) { _,new in new }.merging(["MEETING_OS_LOW_PRIORITY_FLAG":lowPriorityFlag.path]) { _,new in new }.merging(OpenRouterCredential.environment()) { _,new in new }.merging(runtime.childEnvironment) { _,new in new };p.qualityOfService=JobPriority.qos(args:args,zoomOpen:zoomOpen,idle:idle); p.executableURL=URL(fileURLWithPath:runtime.python); p.arguments=["-m","meeting_os"]+args; p.currentDirectoryURL=URL(fileURLWithPath:runtime.repo); p.standardOutput=handle; p.standardError=handle
            p.terminationHandler={ [weak self] process in
                try? handle.close()
                let jobError=ErrorPresentation.logSummary(log)
                Task { @MainActor in
                    guard let self=self else { return }
                    if isRecord { self.recordProcess=nil; self.recordStartedAt=nil; try? FileManager.default.removeItem(at:progress) }
                    else { self.job=nil; self.jobKind=nil; self.busy=false; self.jobLowPriority=false; self.jobs.jobProgress=""; self.progressURL=nil; self.jobStarted=nil; JobSleepGuard.end(); try? FileManager.default.removeItem(at:progress) }
                    if process.terminationStatus != 0 && !self.jobCanceled {
                        // Before the banner, so the throttle credits this to `job` rather than to the `ui` echo.
                        self.report(jobError,kind:"job",context:["command":args.first ?? "job","exit":Int(process.terminationStatus)])
                        self.error=self.resourceStopMessage.isEmpty ? jobError : self.resourceStopMessage
                    }
                    complete(process.terminationStatus==0 && self.resourceStopMessage.isEmpty && !self.jobCanceled); await self.refresh()
                    // Quitting is not the moment to start an upload: the queued meetings keep their audio and the
                    // idle queue picks them up on the next launch. Popping here would begin a job we cannot finish.
                    if !isRecord, !self.requestedQuit, let next=self.finalizeQueue.first { self.finalizeQueue.removeFirst(); self.finalizeWithOpenRouter(next,model:self.cloudModel) }   // meetings that ended while a job ran
                    if !isRecord, !self.requestedQuit, self.pendingSummaryRefresh { self.pendingSummaryRefresh=false; self.runScheduledSummaryRefresh(self.pendingSummaryMeeting) }   // a queued finalize took the slot back: this re-arms rather than stacks
                    if self.requestedQuit && self.job==nil && self.recordProcess==nil { NSApp.reply(toApplicationShouldTerminate:true) }
                }
            }
            try p.run(); error=""
            if isRecord { recordProcess=p; recordStartedAt=Date() } else { job=p; busy=true; jobBackgrounded=false; JobSleepGuard.begin() }   // a Mac that idles to sleep mid-transcription wakes up to an unfinished meeting
            return true
        } catch { self.error=error.localizedDescription; if isRecord { recording=false; recordingNavigation.cancel() } else { busy=false; jobKind=nil; JobSleepGuard.end() }; return false }
    }
    /// Returns false when the previous helper is still draining: the caller must not claim a recording started.
    @discardableResult func start()->Bool {
        startRefusal=nil
        // The microphone track is filed under this Mac's owner. Recording without a name means a transcript
        // full of "Ben" that nobody can attribute later, so the name is asked for once, here, and never guessed.
        // The prompt itself belongs to the caller: hands-free Zoom re-evaluates every few seconds and must
        // state the reason without reopening a sheet under the user's hands.
        // "No name" and "the name has not been read yet" look identical from here, and refusing a recording over
        // the second one loses a meeting the user was ready to have. Settings first, then the name.
        guard settingsLoaded else { startRefusal=Model.settingsLoadingMessage; return false }
        guard hasUserName else { startRefusal=Model.nameRequiredMessage; return false }
        // A meeting that dies at minute 40 because the disk filled is worse than one that never started, so the
        // volume is measured here rather than discovered by the helper. Only a genuinely full disk refuses;
        // between 600 MB and 1,5 GB the user is told and still gets the recording.
        let freeBytes=DiskSpace.free(at:dataDir)
        let diskNotice=DiskSpace.startNotice(freeBytes:freeBytes)
        if DiskSpace.refuses(freeBytes:freeBytes) { startRefusal=diskNotice; return false }
        stopPlayback()   // never play audio into the room during a recording
        guard recordProcess==nil else { startRefusal=LaunchOutcome.recordBusy; return false }
        recordingNavigation.begin()
        let dir=dataDir.appendingPathComponent("recordings/"+UUID().uuidString)
        recordingDir=dir; recording=true; markerCount=0; recorder.recordingNotice=""; recorder.lowDiskNotice=diskNotice ?? ""; continuitySeen=nil; sleptAt=nil; activity=diskNotice ?? "Kayıt hazırlanıyor · macOS izinleri açık olmalı"; DisplaySleepGuard.begin(); updateRecorderPanel()
        pendingCalendar=useCalendar ? CalendarContext.current() : nil
        let name=title.isEmpty ? (pendingCalendar?.title ?? Date().formatted(Date.FormatStyle(date:.abbreviated,time:.shortened,locale:Locale(identifier:"tr_TR")))) : title   // "9 Eyl 2026 14:05"
        if title.isEmpty, diskNotice==nil, let cal=pendingCalendar { activity="Takvimden: \(cal.title)"+(cal.attendees.isEmpty ? "" : " · \(cal.attendees.count) katılımcı") }
        recordingTitle=name
        let receipt=dataDir.appendingPathComponent("record-\(UUID().uuidString).json")
        jobTitle=name
        return launch(CloudTranscription.recordArguments(mode:transcriptionMode,directory:dir.path,title:name,receipt:receipt.path)) { [weak self] ok in
            guard let self=self else { return }; self.recording=false; self.recordingNavigation.cancel(); self.recorder.recordingNotice=""; self.continuitySeen=nil; DisplaySleepGuard.end(); RecorderPanel.hide()
            let result=(try? Data(contentsOf:receipt)).flatMap { try? JSONSerialization.jsonObject(with:$0) as? [String:Any] } ?? [:]
            try? FileManager.default.removeItem(at:receipt)
            // The receipt comes first, before the exit status: a supervisor that died still leaves one when audio
            // reached disk, and that meeting must be finalized rather than shown as "Kayıt tamamlanamadı".
            if let mid=RecordingCompletion.retryMeeting(result,capture:dir.path) {
                if self.requestedQuit { self.activity="Kayıt saklandı · Son işlemi Toplantılar listesinden başlatabilirsiniz" }
                else { self.finishRecordedMeeting(mid); if let calm=RecordingCompletion.notice(result) { self.activity=calm } }
            } else if !ok { self.activity="Kayıt tamamlanamadı · Toplantılar listesindeki kayıt durumunu kontrol edin" }
            else if result["status"] as? String == "canceled" { self.activity="Kayıt iptal edildi · Ses alınmadı" }
            else { self.activity="Kayıt saklandı · Son işlem otomatik başlatılamadı" }
        }
    }
    func stop() { guard recording else { return }; recordingNavigation.cancel(); activity="Ses parçaları tamamlanıyor…"; recording=false; stopArmedAt=nil; recordProcess?.interrupt() }
    func finishRecordedMeeting(_ mid:String) {
        if let cal=pendingCalendar { pendingCalendar=nil; Task { _=try? await request(["action":"meeting_context","meeting":mid,"calendar":cal.payload]) } }
        if transcriptionMode=="openrouter" { finalizeWithOpenRouter(mid,model:cloudModel); return }
        activity="Aynı toplantının son transkripti hazırlanıyor…"
        launch(["retry",mid]) { [weak self] ok in
            guard let self=self else { return }
            if ok {
                if self.requestedQuit { self.activity="Transkript hazır" }
                else { self.analyzeAutomatically(mid) }
            }
            else { self.activity=self.jobCanceled ? "İşlem durduruldu · Kaynak kayıt korunuyor" : "Son işlem başarısız · Önceki metin ve ses korunuyor" }
        }
    }
    /// Cloud-only transcription of a stopped recording. Pass a model only for a recording that has not started in the cloud yet.
    func finalizeWithOpenRouter(_ mid:String,model:String?) {
        guard job==nil else { idleRetry=false; if !finalizeQueue.contains(mid) { finalizeQueue.append(mid); activity="Sıradaki toplantı yazıya çevrilecek · önceki iş bitince" }; return }   // a queued meeting is the user's, not the idle queue's
        let result=dataDir.appendingPathComponent("openrouter-\(UUID().uuidString).json")
        let stored=meetings.first(where:{ $0.id==mid })?.metadata["cloud_mode"] != nil
        activity="Yazıya çevriliyor…"
        launch(CloudTranscription.finalizeArguments(meeting:mid,model:stored ? nil : model,output:result.path)) { [weak self] ok in
            guard let self else { return }
            defer { try? FileManager.default.removeItem(at:result) }
            if ok {
                if self.selected==nil || self.selected==mid || (self.meeting?.status=="complete" && !NSApp.isActive) { self.selected=mid } else { self.pendingReady=mid }   // never yank the user away from what they are reading
                let count=(try? Data(contentsOf:result)).flatMap { try? JSONSerialization.jsonObject(with:$0) as? [String:Any] }?["segments"] as? Int ?? 0
                if count==0 { self.activity="Kayıtta konuşma bulunmadı · analiz başlatılmadı" }
                else { self.activity="Yazıya çevrildi · özet hazırlanıyor"; if !self.requestedQuit { self.analyzeAutomatically(mid) } }   // one notification, when the summary is ready too
            }
            else { self.activity=self.jobCanceled ? "İşlem durduruldu · Ses ve biten bölümler duruyor" : "Yazıya çevirme yarım kaldı · Ses ve biten bölümler duruyor; ‘Yazıya çevir’ ile sürdürün" }
        }
    }
    func loadCloudModels() async {
        guard cloudModels.isEmpty else { return }
        do {
            let response=try await request(["action":"openrouter_models"])
            let data=try JSONSerialization.data(withJSONObject:response["models"] ?? [])
            cloudModels=try JSONDecoder().decode([OpenRouterModelOption].self,from:data)
            if !cloudModels.contains(where:{ $0.id==cloudModel }) { cloudModel=(response["diarization_default"] as? String) ?? CloudTranscription.defaultModel }
        } catch { self.error=error.localizedDescription }
    }
    var canCancelJob:Bool { RecoveryPresentation.canCancel(jobKind:jobKind,running:job?.isRunning == true,requested:jobCanceled) }
    func cancelJob() {
        guard canCancelJob else { return }
        jobCanceled=true;activity="İşlem durduruluyor · Kaynak kayıt korunuyor";job?.interrupt()
    }
    func recover() {
        guard job==nil, let m=meeting, RecoveryPresentation.canRetry(status:m.status,hasCapture:!m.captureSourcesEmpty,owner:m.recoveryState) else { return }
        let mid=m.id;activity="Kayıt kontrol ediliyor ve aynı toplantı yeniden işleniyor…"
        launch(["retry",mid]) { [weak self] ok in
            guard let self=self else { return }
            self.activity=ok ? "Toplantı kurtarıldı" : self.jobCanceled ? "İşlem durduruldu · Kaynak kayıt korunuyor" : "Kurtarma tamamlanamadı · Önceki metin korunuyor"
        }
    }
    func saveLabel(enroll:Bool) async {
        guard let row=editRow, let mid=selected else { return }
        guard !enroll || meeting?.metadata["text_only"] as? Bool != true else { return }
        do {
            _=try await request(["action":enroll ? "enroll":"label","meeting":mid,"segment":row.id,"name":editName,"confirmed_clean":clean])
            editRow=nil; await refresh()
        } catch where enroll {
            // A short or unclean segment cannot become a voice sample; the name itself must still land.
            do { _=try await request(["action":"label","meeting":mid,"segment":row.id,"name":editName]); editRow=nil; activity="İsim kaydedildi · bu bölümden ses profili alınamadı (en az 6 sn temiz konuşma gerekir)"; await refresh() }
            catch { self.error=error.localizedDescription }
        } catch { self.error=error.localizedDescription }
    }
    /// Names a provider-diarized speaker cluster for the whole meeting; with enroll, the cluster centroid becomes a voice profile.
    func saveSpeaker(enroll:Bool) async {
        guard let row=editRow, let mid=selected, !row.speaker.isEmpty else { return }
        do {
            let result=try await request(["action":"label_speaker","meeting":mid,"speaker":row.speaker,"name":editName,"enroll":enroll])
            editRow=nil
            if enroll { activity=EnrollNotice.line(result)+adaptationNote(result) } else { activity="Konuşmacı yalnız bu toplantıda adlandırıldı"+adaptationNote(result) }
            canUndoNaming=true
            await refresh(); await loadReview(); refreshSummaryIfNamesDone()
        } catch { self.error=error.localizedDescription }
    }
    /// One piece of a named cluster belongs to someone else: only that piece changes, the cluster keeps its name,
    /// nobody is convicted, and the right person's profile learns from the piece when it is clean enough.
    func saveSegmentOnly(_ target:Row) async {
        guard let mid=selected else { return }
        let name=editName.trimmingCharacters(in:.whitespaces); guard !name.isEmpty else { return }
        do {
            let r=try await request(["action":"label_segment","meeting":mid,"segment":target.id,"name":name])
            editRow=nil
            activity=(r["profile_saved"] as? Bool)==true ? "Yalnız bu bölüm “\(name)” oldu · ses profili bu bölümden öğrendi" : "Yalnız bu bölüm “\(name)” oldu · bölüm kısa ya da karışık olduğu için profil öğrenmedi"
            canUndoNaming=true
            await refresh(); await loadReview()
            // One pinned piece is not a reason to re-buy the summary: the Özet tab offers the refresh instead.
            // Read the flag after the refresh, because it is the refresh that learns the analysis went stale.
            if analysis?["stale"] as? Bool == true { summaryStale=true }
        } catch { self.error=error.localizedDescription }
    }
    /// One click turns a “Sol Üst?” suggestion into the cluster name and, when there is enough speech, a profile sample.
    func confirmSuggestion(_ row:Row) async {
        guard !row.suggested.isEmpty, let mid=selected, !busy else { return }
        do { _=try await request(["action":"label_speaker","meeting":mid,"speaker":row.speaker,"name":row.suggested,"enroll":true]); activity="“\(row.suggested)” onaylandı · profil güncellendi"; canUndoNaming=true; await refresh(); await loadReview(); refreshSummaryIfNamesDone() }
        catch { self.error=error.localizedDescription }
    }
    func saveText() async {
        guard let row=editRow, let mid=selected else { return }
        do { _=try await request(["action":"edit_text","meeting":mid,"segment":row.id,"text":editText]); editRow=nil; await refresh() } catch { self.error=error.localizedDescription }
    }
    func deleteMeeting(_ meeting:Meeting) async {
        // A running job owns the database: say so instead of swallowing the click (the confirm dialog just closed).
        guard !busy else { activity="Şu an bir işlem sürüyor · bitince “\(meeting.title.isEmpty ? "toplantı" : meeting.title)” silinebilir"; return }
        do {
            _=try await request(["action":"delete_meeting","meeting":meeting.id])
            if selected==meeting.id { selected=nil;rows=[] }
            activity="Toplantı silindi · Ses profilleri korundu"
            RemindersBridge.remove(meetingTitle:meeting.title) { [weak self] n in if n>0 { self?.activity="Toplantı silindi · \(n) hatırlatıcı da kaldırıldı · Ses profilleri korundu" } }   // the hand-offs in Reminders go with the meeting
            await refresh()
        } catch { self.error=error.localizedDescription }
    }
    func deleteProfile(_ name:String) async { do { _=try await request(["action":"delete_profile","name":name]); await refresh() } catch { self.error=error.localizedDescription } }
    func export(_ format:String) async {
        guard let mid=selected else { return }; let panel=NSSavePanel(); panel.nameFieldStringValue="Meeting.\(format)"
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { _=try await request(["action":format=="analysis.md" ? "export_analysis":"export","meeting":mid,"path":url.path,"format":format]); activity="Dışa aktarıldı: \(url.lastPathComponent)" } catch { self.error=error.localizedDescription }
    }
    /// Sidebar search: matches title, date and the auto-title words, case- and diacritic-insensitively.
    @Published var filter=""
    var visibleMeetings:[Meeting] {
        let q=filter.trimmingCharacters(in:.whitespaces)
        if q.isEmpty { return meetings }
        return meetings.filter { ($0.title+" "+$0.created+" "+$0.names.joined(separator:" ")+" "+MeetingDates.label($0.created)).range(of:q,options:[.caseInsensitive,.diacriticInsensitive]) != nil }
    }
    /// Sidebar sections in display order; empty groups are omitted.
    var groupedMeetings:[(String,[Meeting])] {
        let now=Date(); let byGroup=Dictionary(grouping:visibleMeetings) { MeetingDates.group($0.created,now:now) }
        return MeetingDates.order.compactMap { g in byGroup[g].map { (g,$0) } }
    }
    /// Bumped by ⌘F / ⌘⇧F; the field that owns the token takes focus.
    @Published var searchFocusToken=0; @Published var memoryFocusToken=0
    func focusTranscriptSearch() { tab="transcript"; searchFocusToken+=1 }
    func focusMemorySearch() { tab="memory"; memoryFocusToken+=1 }
    @Published var cost:[String:Any]?
    @Published var setupChecks:[SetupCheck]=[]
    /// Where the team's knowledge actually goes (Ayarlar → Ekip reads it), whether this Mac is in a team at all
    /// (the welcome screen reads that), and the answer of the last join — which IS the confirmation sheet.
    @Published var teamTarget=TeamTarget.off
    @Published var teamConfigured=false
    @Published var teamJoin:TeamJoinOutcome?
    /// Whether this is a downloaded, self-contained app rather than a checkout. Read by the setup card (no
    /// git rows), the welcome screen and the update channel.
    var bundled:Bool { runtime.bundled }
    /// Set when the invite that shipped inside the bundle could not be applied — then, and only then, the
    /// welcome screen puts the paste field back, because otherwise there is no way in at all.
    @Published var bundleInviteFailed=false
    /// A shipped invite is still on its way in: the welcome screen must not ask for one it already has.
    var bundleInvitePending:Bool { bundled && !bundleInviteFailed && BundleInvite.exists(resources:Bundle.main.resourceURL) }
    @Published var glossaryCount=0; @Published var glossaryFromFile=0; @Published var glossarySample:[String]=[]
    @Published var zoomMeetingOpen=false
    /// Per-second recording state lives on its own object: the panel and the menu bar observe it, the main
    /// window does not, so a ticking clock never re-lays out a 300-paragraph transcript during a meeting.
    let recorder=RecorderState()
    let jobs=JobState()   // "… · 3 dk 12 sn" ticks every poll while a job runs; only the status card and the menu watch it
    /// Read the calendar when a recording starts: the live event names the meeting and its attendees become naming shortcuts.
    @Published var useCalendar=UserDefaults.standard.object(forKey:"useCalendar") as? Bool ?? false {
        didSet {
            UserDefaults.standard.set(useCalendar,forKey:"useCalendar")
            if useCalendar && !CalendarContext.authorized { CalendarContext.requestAccess { [weak self] ok in if !ok { self?.useCalendar=false; self?.error="Takvim erişimi verilmedi · Sistem Ayarları → Gizlilik ve Güvenlik → Takvimler" } } }
        }
    }
    var pendingCalendar:CalendarEvent?
    var pollTick=0
    /// Title of the job being launched, handed to the child in MEETING_OS_TITLE (never on argv).
    var jobTitle=""
    /// The typed archive question and the picked import file: MEETING_OS_QUESTION / MEETING_OS_AUDIO_PATH.
    /// argv is world-readable through `ps`, and both name what this Mac's owner is working on.
    var jobQuestion=""; var jobAudioPath=""
    /// One-shot inputs for the child, consumed by the launch attempt that carries them: a later, unrelated
    /// job must never inherit the previous meeting's title or the last question.
    private func consumeJobEnvironment()->[String:String] {
        defer { jobTitle="";jobQuestion="";jobAudioPath="" }
        return ["MEETING_OS_TITLE":jobTitle,"MEETING_OS_QUESTION":jobQuestion,"MEETING_OS_AUDIO_PATH":jobAudioPath]
    }
    /// Recording lives in its own process slot (see launch); jobs never block it.
    var recordProcess:Process?; var recordStartedAt:Date?; var stopArmedAt:Date?
    var sleptAt:Date?; var continuitySeen:RecordingContinuity.State?
    /// One passive line in the recorder panel when a recording survived a stream rebuild, a helper relaunch or a sleep.
    var finalizeQueue:[String]=[]
    /// A meeting that finished while the user was reading another one; the status line offers to open it.
    @Published var pendingReady:String?
    var lastZoomState:(open:Bool,strict:Bool,sharing:Bool,running:Bool)=(false,false,false,false)
    /// Talk shares depend on rows only; computed once per row change instead of in the Özet body every poll.
    @Published private(set) var shares:[TalkShare]=[]
    @Published var dueSuggestions:[String:String]=[:]
    /// Suggestions whose day has already gone (a meeting analysed weeks after it happened still says "yarın").
    @Published var pastDueSuggestions:Set<String>=[]
    @Published var questions:[QuestionGroup]=[]; @Published var scorePeriod:[String:Any]?; @Published var scoreMeetings:[ScoreMeeting]=[]
    /// How many meetings behind each cross-meeting list have been edited since their analysis ran. Set once per
    /// load next to the list itself — never on a timer — so the header sentence costs nothing to keep honest.
    @Published var decisionStaleMeetings=0; @Published var questionStaleMeetings=0; @Published var waitingStaleMeetings=0
    /// Decisions that still stand and the ones a later meeting took back. The header used to count the rows it had
    /// been handed (matched/total), which disagreed with the karne — that counts live decisions only.
    @Published var decisionLive=0; @Published var decisionSuperseded=0
    /// Poll fingerprints: rows and intelligence are re-fetched only when the Python side reports a change.
    var segmentsHash=""; var lastSegmentsMeeting=""; var intelHash=""
    /// Görünüm: "system" | "light" | "dark", and the accent preset key.
    @Published var appearance=UserDefaults.standard.string(forKey:"appearance") ?? "system" { didSet { UserDefaults.standard.set(appearance,forKey:"appearance") } }
    @Published var accentKey=UserDefaults.standard.string(forKey:"accentKey") ?? "green" { didSet { UserDefaults.standard.set(accentKey,forKey:"accentKey"); MeetingStyle.accent=Accents.color(accentKey) } }
    var colorScheme:ColorScheme? { appearance=="light" ? .light : (appearance=="dark" ? .dark : nil) }
    /// Idle retry of meetings the cloud refused: last question asked, last passive notice, the standing hint.
    var lastIdleRetry:Date?; var memoryPressureAt:Date?
    var lastBlockedNotice:Date? {
        get { UserDefaults.standard.object(forKey:"cloudBlockedNoticeAt") as? Date }
        set { UserDefaults.standard.set(newValue,forKey:"cloudBlockedNoticeAt") }
    }
    @Published var blockedHint=""
    /// Set for the one launch that follows an idle retry, so the job starts at background priority.
    var idleRetry=false
    /// Hourly heartbeat into the shared iCloud folder so a day without a finished meeting still leaves a trace.
    var lastHeartbeat:Date?
    // Cross-meeting PM views (loaded on demand, never while recording)
    @Published var decisions:[DecisionEntry]=[]; @Published var waiting:[WaitingPerson]=[]; @Published var debt:[DebtItem]=[]; @Published var debtSummary=""
    /// Evidence / review navigation: scroll the reading view to the paragraph and flash it, keeping context around it.
    @Published var revealTarget:Int?; @Published var revealToken=0; @Published var highlighted:Int?
    func reveal(segment id:Int) {
        // Every "Bölüme git", every name card and every resolved piece of evidence lands here, so this is
        // the one place a jump into the transcript has to remember where it came from.
        if navEvidenceInFlight { navEvidenceInFlight=false } else { pushNavForJump() }
        tab="transcript"; search=""; focusedSegment=nil; flashReveal(segment:id)
    }
    /// Scroll to a paragraph and flash it. Split out of `reveal` so going back can restore a focused
    /// segment without clearing the filter that focused it in the first place.
    func flashReveal(segment id:Int) {
        revealTarget=id; revealToken+=1; highlighted=id
        let token=revealToken
        DispatchQueue.main.asyncAfter(deadline:.now()+2.5) { [weak self] in if self?.revealToken==token { self?.highlighted=nil } }
    }

    // MARK: Back navigation
    /// Where the user was before each programmatic jump. Pushed by jumps only — a sidebar click, a tab
    /// click and typing in the search field are the user driving the UI, and leave nothing behind.
    /// Never persisted, so every launch starts with no way back and no stale meeting ids.
    @Published private(set) var backStack:[NavPoint]=[]
    /// State before the first mutation of the current run-loop turn; a jump usually writes three or four
    /// properties in a row, and all of them belong to one navigation.
    var navBefore:NavPoint?
    var navPushedThisBatch=false
    var navRestoring=false          // goBack is writing: nothing it touches is a new jump
    var navEvidenceInFlight=false   // the point was pushed when an evidence jump started; its later reveal must not push again
    /// A meeting switch whose jump may still be coming (the week view reveals its paragraph ~1.2 s later).
    /// Remembered, never pushed: on its own, a meeting switch is a sidebar click.
    var navCandidate:(point:NavPoint,at:Date)?

    var currentNavPoint:NavPoint { NavPoint(meeting:selected,tab:tab,focusedSegment:focusedSegment,search:search) }

    /// Called from willSet on everything a NavPoint reads: snapshot the turn's starting point, then judge
    /// the whole turn once it has finished. Nothing is published here, so a keystroke costs one closure.
    func noteNavChange() {
        guard navBefore==nil else { return }
        navBefore=currentNavPoint
        DispatchQueue.main.async { [weak self] in self?.commitNavBatch() }
    }

    /// Classify a finished turn. Only a jump — a cross-meeting result being opened, or evidence on its way
    /// to the transcript — leaves a point behind; the rest of the UI stays out of the history.
    func commitNavBatch() {
        guard let before=navBefore else { return }
        navBefore=nil
        let pushed=navPushedThisBatch; navPushedThisBatch=false
        if navEvidenceInFlight && pendingEvidence==nil { navEvidenceInFlight=false }   // resolved, or given up on, without a reveal
        guard !navRestoring else { navCandidate=nil; return }
        let now=currentNavPoint
        guard before != now else { return }
        if pushed { if before.meeting != now.meeting { navCandidate=nil }; return }
        // An evidence jump lands in two steps: the transcript opens now, its paragraph is revealed once the
        // rows arrive. Push the departure point here and let that second step pass.
        if pendingEvidence != nil { pushNav(before); navEvidenceInFlight=true; navCandidate=nil; return }
        if before.meeting != now.meeting {
            if before.tab != now.tab { pushNav(before); navCandidate=nil }   // a result opening another meeting on a tab of its own
            else { navCandidate=(before,Date()) }
        }
        // Same meeting, only a tab or the search field changed: the user is already where they meant to be.
    }

    func pushNav(_ point:NavPoint) { backStack=NavHistory.pushed(backStack,point) }

    /// Remember where the user is standing, immediately before a programmatic jump moves them.
    func pushNavForJump() {
        guard !navRestoring, !navPushedThisBatch else { return }
        var point=navBefore ?? currentNavPoint
        if navBefore==nil, let candidate=navCandidate, Date().timeIntervalSince(candidate.at)<NavHistory.candidateWindow { point=candidate.point }
        navCandidate=nil
        pushNav(point)
        navPushedThisBatch=true
        if navBefore==nil { navBefore=currentNavPoint; DispatchQueue.main.async { [weak self] in self?.commitNavBatch() } }
    }

    /// Wrap a programmatic jump: the place being left is pushed, then the jump runs.
    func navigate(_ jump:()->Void) { pushNavForJump(); jump() }

    /// Undo the last jump: the meeting, the tab, the search text and the focused paragraph as they were.
    /// Order matters — `selected` clears the search and the focus, and `search` clears the focus again.
    func goBack() {
        let (point,rest)=NavHistory.popped(backStack)
        guard let p=point else { return }
        backStack=rest
        navRestoring=true; navCandidate=nil
        // A meeting deleted since the jump is no longer somewhere to go back to; the rest of the point still is.
        if let meeting=p.meeting, meeting != selected, meetings.contains(where:{ $0.id==meeting }) { selected=meeting }
        tab=p.tab
        if search != p.search { search=p.search }
        focusedSegment=p.focusedSegment
        if let segment=p.focusedSegment { flashReveal(segment:segment) }
        DispatchQueue.main.async { [weak self] in self?.navRestoring=false }
    }
    /// Paragraph that contains a segment (evidence may point at a non-lead row of a block).
    func blockId(containing id:Int)->Int? { blocks.first { $0.rows.contains { $0.id==id } || $0.asides.contains { $0.id==id } }?.id }
    /// Live capture health for the floating panel (mic / system audio), refreshed with every poll while recording.
    /// A job that started before the next Zoom meeting opened is pushed to Darwin background (CPU, I/O and
    /// network throttled) and told to upload one piece at a time; both are undone when the meeting ends.
    var jobBackgrounded=false
    var lowPriorityFlag:URL { dataDir.appendingPathComponent("low-priority.flag") }
    /// Title of the recording in progress, shown on the floating panel.
    @Published var recordingTitle=""
    /// Hands-free Zoom: start when a meeting window has been open ~10 s, stop an auto-started recording 60 s after it closes.
    @Published var zoomAutoRecord=UserDefaults.standard.object(forKey:"zoomAutoRecord") as? Bool ?? false { didSet { UserDefaults.standard.set(zoomAutoRecord,forKey:"zoomAutoRecord") } }
    var zoomAuto=ZoomAutoRecord()
    @Published var showRecorderPanel=UserDefaults.standard.object(forKey:"showRecorderPanel") as? Bool ?? true { didSet { UserDefaults.standard.set(showRecorderPanel,forKey:"showRecorderPanel"); updateRecorderPanel() } }
    /// Göze batma. Default ON: while recording the menu bar item is indistinguishable from an idle one, the
    /// floating panel leaves the screen for as long as the user is sharing it, and the app's own windows are
    /// excluded from screen capture. Stored under `DiscreetMode.key`, so `@AppStorage("discreetMode")` reads the
    /// same value anywhere a view wants it without the Model.
    @Published var discreetMode=DiscreetMode.enabled { didSet { UserDefaults.standard.set(discreetMode,forKey:DiscreetMode.key); applyWindowPrivacy(); updateRecorderPanel() } }
    /// The user is presenting right now (Zoom share toolbar / "screen sharing" window). Drives the panel only —
    /// the recording itself is untouched, and ⌃⌥R / ⌃⌥M keep working with nothing on screen.
    @Published var screenSharing=false
    /// The one place that decides whether the floating panel is on screen. Called on every poll, so the panel
    /// leaves within a tick of the share starting and comes back within a tick of it ending.
    func updateRecorderPanel() {
        if DiscreetMode.panelVisible(recording:recording,panelEnabled:showRecorderPanel,discreet:discreetMode,sharing:screenSharing) { RecorderPanel.show(model:self) } else { RecorderPanel.hide() }
    }
    /// Keeps the app's real windows out of the capture stream while discreet mode is on. The floating panel is
    /// left alone: it sets `.none` for itself and must never be turned back on. Windows are created and recreated
    /// over a session (the main window, sheets), so this is re-applied rather than set once at launch.
    func applyWindowPrivacy() {
        let want=DiscreetMode.windowSharingType(discreet:discreetMode)
        for w in NSApp.windows where !(w is NSPanel) { if w.sharingType != want { w.sharingType=want } }
    }
    @Published var zoomNotify=UserDefaults.standard.object(forKey:"zoomNotify") as? Bool ?? true { didSet { UserDefaults.standard.set(zoomNotify,forKey:"zoomNotify"); if zoomNotify { ZoomNotifier.register() } } }
    @Published var explanation:IdentityExplanation?
    @Published var continuity=Continuity()
    @Published var renaming=false; @Published var renameText=""
    func renameMeeting() async {
        guard let mid=selected else { return }
        do { _=try await request(["action":"rename_meeting","meeting":mid,"title":renameText]); renaming=false; await refresh() } catch { self.error=error.localizedDescription }
    }
    /// Finished work reaches the user even when Zoom or another app is in front.
    /// Meeting-safe: nothing pops while recording or while a Zoom meeting is on screen; it is delivered afterwards, silently.
    func notifyDone(_ title:String,_ body:String) {
        if !DiscreetMode.mayNotify(recording:recording,meetingOpen:zoomMeetingOpen,sharing:screenSharing) { queuedNotifications.append((title,body)); return }
        deliver(title,body)
    }
    private func deliver(_ title:String,_ body:String) {
        let content=UNMutableNotificationContent(); content.title=title; content.body=body; content.interruptionLevel = .passive
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier:"done-"+UUID().uuidString,content:content,trigger:nil))
    }
    var queuedNotifications:[(String,String)]=[]
    struct CleanupPreview:Equatable { let days:Int; let count:Int; let bytes:Int; let titles:[String] }
    @Published var cleanupPreview:CleanupPreview?
    @Published var cleanupDays=30
    func keepMeeting(_ id:String,keep:Bool) async { do { _=try await request(["action":"keep_meeting","meeting":id,"keep":keep]); await refresh() } catch { self.error=error.localizedDescription } }
    /// Meeting → PRD / bug report / customer request / Claude Code prompt, saved where the user chooses. Cloud mode only.
    func exportDocument(kind:String) async {
        guard let mid=selected, transcriptionMode=="openrouter" else { self.error="Belge hazırlama bulut modunda çalışır (Ayarlar → Sistem → Yazıya çevirme)"; return }
        let names=["prd":"prd","bug":"hata-raporu","customer":"musteri-talebi","claude":"claude-code-istemi"]
        let panel=NSSavePanel();panel.nameFieldStringValue="\(names[kind] ?? kind)-\(mid.prefix(6)).md";panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        busy=true; activity="Belge hazırlanıyor (\(analysisModel))…"
        defer { busy=false }
        do { let r=try await request(["action":"document","meeting":mid,"kind":kind,"path":url.path,"openrouter_model":analysisModel]); activity="Belge kaydedildi · \(r["title"] as? String ?? "") · \(r["sources"] as? Int ?? 0) kaynak bölüm" }
        catch { self.error=error.localizedDescription }
    }
    func loadContinuity() async { guard let mid=selected else { continuity=Continuity(); return }; continuity=(try? await request(["action":"continuity","meeting":mid])).map(Continuity.parse) ?? Continuity() }
    func supersede(old:String,new:String) async {
        do { _=try await request(["action":"supersede_task","old":old,"new":new]); activity="Önceki görev kapatıldı; bu görev devamı sayılıyor"; if let mid=selected { try await refreshIntelligence(mid) }; await loadContinuity() } catch { self.error=error.localizedDescription }
    }
    func loadSamples(_ name:String) async -> [VoiceSample] { ((try? await request(["action":"profile_samples","name":name]))?["samples"] as? [[String:Any]] ?? []).map(VoiceSample.init) }
    func deleteSample(_ id:Int) async { do { _=try await request(["action":"delete_sample","sample":id]); await refresh() } catch { self.error=error.localizedDescription } }
    func loadCleanCandidates(_ name:String) async -> [CleanCandidate] { ((try? await request(["action":"clean_candidates","name":name]))?["candidates"] as? [[String:Any]] ?? []).map(CleanCandidate.init) }
    /// Q8: turn one of the person's own long clean turns into a voice sample. The bridge's clean filter (length,
    /// flags, stored vector) is the confirmation here — the picker offers nothing it would refuse.
    func enrollCandidate(_ c:CleanCandidate,name:String) async {
        guard !busy else { return }
        do { _=try await request(["action":"enroll","meeting":c.meeting,"segment":c.id,"name":name,"confirmed_clean":true])
            activity="“\(name)” profiline temiz örnek eklendi · \(Int(c.seconds)) sn · \(c.meetingTitle)"
            await refresh(); await loadMaintenance() }
        catch { self.error=error.localizedDescription }
    }
    func playCandidate(_ c:CleanCandidate) {
        guard let m=meetings.first(where:{ $0.id==c.meeting }) else { error="Bu bölümün toplantısı bulunamadı"; return }
        play(source:c.source,start:c.start,seconds:c.seconds,metadata:m.metadata,key:"cand:\(c.id):\(c.meeting):\(c.start)")
    }
    func renameProfile(_ name:String,to newName:String) async {
        do { let r=try await request(["action":"rename_profile","name":name,"new_name":newName]); activity=(r["merged"] as? Bool)==true ? "“\(name)” → “\(newName)” birleştirildi" : "“\(name)” → “\(newName)” yeniden adlandırıldı"; await refresh() } catch { self.error=error.localizedDescription }
    }
    func explainIdentity(_ row:Row) async {
        guard let mid=selected else { return }
        explanation=(try? await request(["action":"explain_identity","meeting":mid,"speaker":row.speaker])).map(IdentityExplanation.parse)
    }
    func showMainWindow() { NSApp.activate(ignoringOtherApps:true); NSApp.windows.first(where:{ $0.title=="Meeting OS" })?.makeKeyAndOrderFront(nil); applyWindowPrivacy() }
    /// Global hot key dispatch (⌃⌥R / ⌃⌥M) — same guards as the buttons.
    func hotkey(_ id:UInt32) {
        if id==GlobalHotkeys.record {
            if recording {
                let age=Date().timeIntervalSince(recordStartedAt ?? .distantPast)
                if age<3 { return }   // key repeat / double press right after start: ignore
                if age<15 { if let armed=stopArmedAt, Date().timeIntervalSince(armed)<2 { stop() } else { stopArmedAt=Date(); activity="Bitirmek için ⌃⌥R’ye bir kez daha bas" }; return }
                stop()
            } else { beginRecording() }
        }
        else if id==GlobalHotkeys.mark, recording { markMoment("important") }
    }
    @Published var update:UpdateInfo?; @Published var updating=false; @Published var reportSettings=ReportSettings(shareReports:true,shareText:false,autoUpdate:false,reportDir:"")
    /// The person this Mac belongs to (Ayarlar → Genel → Adınız); never a hard-coded name. Empty until they
    /// type it, and an empty name matches nobody — better than filing a teammate's tasks under a stranger.
    var userName:String { reportSettings.userName.trimmingCharacters(in:.whitespacesAndNewlines) }
    var hasUserName:Bool { !userName.isEmpty }
    /// One calm line, in the two places a recording can start from.
    static let nameRequiredMessage="Önce adınızı yazın: kayıtta sizin sesiniz bu adla etiketlenir · Ayarlar → Genel"
    /// Why the last `start()` refused, so the caller does not paper over the reason with a different one.
    var startRefusal:String?
    /// Said instead of "type your name" while the bridge has not answered yet: an unread setting is not a missing one.
    static let settingsLoadingMessage="Ayarlar yükleniyor · bir saniye sonra yeniden deneyin"
    var settingsLoaded=false
    /// Asked once per launch, from the poll, when there are meetings but still no owner name.
    var namePromptedOnLaunch=false
    /// The team folder is pulled once per launch, from the poll, as soon as the settings are known.
    var teamSyncedOnLaunch=false
    /// The owner name has to be known before the first ⌃⌥R, not six hours later when the update poll runs.
    /// Called from `init`'s first task and again by every update check.
    func loadReportSettings() async {
        guard let r=try? await request(["action":"report_settings"]) else { return }
        reportSettings=ReportSettings.parse(r); storedUserName=reportSettings.userName; settingsLoaded=true
    }
    var nameRefusalNotified=false   // hands-free Zoom: say "type your name" once per Zoom session, as a notification
    /// Bumped when a refused recording (or the settings sheet) should put the caret in the name field.
    @Published var userNameFocusToken=0
    /// The name the bridge last confirmed: what the stored microphone rows still carry, and therefore the
    /// `old` side of a rename. Kept apart from `reportSettings.userName`, which changes as the user types.
    var storedUserName=""
    /// Welcome ⏎ and Ayarlar → Genel both land here: write the setting, then re-label the microphone rows of
    /// every past meeting that still carries the previous name (or "Ben", the placeholder used when there was none).
    func saveUserName() async {
        let previous=storedUserName.trimmingCharacters(in:.whitespacesAndNewlines)
        let next=reportSettings.userName.trimmingCharacters(in:.whitespacesAndNewlines)
        if next.isEmpty && !previous.isEmpty { reportSettings.userName=previous; return }   // an empty field never wipes a stored name
        reportSettings.userName=next
        // The bridge relabels earlier meetings itself when the name changes (`report_settings_set` → renamed_meetings);
        // a second explicit rename would only ever find 0 rows and hide the real count.
        let touched=await saveReportSettings()
        guard !next.isEmpty, !NameFold.same(previous,next) else { return }
        activity=touched>0 ? "Adınız \(next) · önceki \(touched) toplantıdaki sesiniz yeniden etiketlendi" : "Adınız \(next) · kayıtlarda sesiniz bu adla etiketlenecek"
        await refresh()
    }
    /// ⌘Q with the settings sheet open used to drop a name that had been typed but never submitted: the field
    /// saves on ⏎ and on `onDisappear`, and neither runs when the process is going away. This is synchronous on
    /// purpose — an async Task would not outlive `applicationShouldTerminate`.
    func saveUserNameOnQuit() {
        guard showSettings, settingsLoaded else { return }
        let typed=reportSettings.userName.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !typed.isEmpty, !NameFold.same(typed,storedUserName) else { return }
        var changes=reportSettings.changes; changes["user_name"]=typed
        _=try? invoke(runtime,["action":"report_settings_set","changes":changes])
        storedUserName=typed
    }
    /// Open the field that is missing and put the caret in it: the welcome screen when there are no meetings
    /// yet, Ayarlar → Genel otherwise.
    func promptForUserName() {
        if !meetings.isEmpty {
            UserDefaults.standard.set("genel",forKey:"settingsSection")
            if !showSettings { Task { await settings() } }
        }
        userNameFocusToken+=1
    }
    /// Every way into a recording goes through here, so the refusal reads the same from the button, the menu
    /// bar, the notification and ⌃⌥R.
    func beginRecording() {
        if let line=LaunchOutcome.activity(started:start(),onStart:LaunchOutcome.recordStarted,onRefusal:startRefusal) { activity=line }
        if startRefusal==Model.nameRequiredMessage { promptForUserName() }   // the caret goes where the answer has to be typed
    }
    var lastUpdateCheck:Date?
    /// Called after the first snapshot and every six hours; a fetch, nothing more.
    func checkForUpdates(force:Bool=false) async {
        if !force, let last=lastUpdateCheck, Date().timeIntervalSince(last) < 60*60 { return }   // on launch, on activation, at most hourly
        lastUpdateCheck=Date()
        if let status=try? await request(["action":"update_status"]), let state=status["state"] as? String {
            let msg=status["message"] as? String ?? "", stamp=status["time"] as? String ?? ""
            let percent=status["percent"] as? Int ?? 0
            if let line=UpdateStatusLine.line(state:state,message:msg,time:stamp,percent:percent), UserDefaults.standard.string(forKey:"lastShownUpdate") != stamp {
                UserDefaults.standard.set(stamp,forKey:"lastShownUpdate"); activity=line
                // A failed update is not a passing sidebar line: nothing else will ever mention it again.
                if state=="failed" { notifyDone("Güncelleme başarısız",msg.isEmpty ? line : msg) }
            }
        }
        if let r=try? await request(["action":"update_check"]) { update=UpdateInfo.parse(r) }
        await loadReportSettings()
        if reportSettings.autoUpdate, update?.canUpdate==true, job==nil, !recording, recordProcess==nil, !zoomMeetingOpen { startUpdate() }
    }
    /// Hands over to the detached updater and quits; the updater rebuilds, re-signs and relaunches.
    func startUpdate() {
        guard job==nil, !recording, !updating else { return }
        if let u=update, u.diverged { activity=u.divergedNotice; return }   // scripts/update.sh would refuse the fast-forward anyway
        if recordProcess != nil { activity="Önceki kayıt kapanıyor · birkaç saniye sonra güncelleyin"; return }   // the updater would wait 60 s on the draining helper and abort
        if zoomMeetingOpen { activity="Zoom toplantısı açıkken güncelleme yapılmaz · toplantı bitince tekrar deneyin"; return }   // a rebuild would steal the meeting's CPU
        updating=true; activity="Güncelleniyor · uygulama kapanıp yeniden açılacak"
        Task {
            do {
                _=try await request(BundleInfo.updateStartRequest())
                if !BundleInfo.bundled { try? await Task.sleep(nanoseconds:600_000_000); NSApp.terminate(nil); return }
                // Bundle channel: the detached worker downloads (minutes for ~1 GB) while the app stays open and shows
                // the percentage; the swap script waits for this pid, so we quit only once the state says `swapping`.
                while true {
                    try? await Task.sleep(nanoseconds:2_000_000_000)
                    guard let status=try? await request(["action":"update_status"]), let state=status["state"] as? String else { continue }
                    let percent=status["percent"] as? Int ?? 0
                    if let line=UpdateStatusLine.line(state:state,message:status["message"] as? String ?? "",time:status["time"] as? String ?? "",percent:percent) { activity=line }
                    if UpdateStatusLine.shouldQuit(state:state) { NSApp.terminate(nil); return }
                    if state=="failed" { updating=false; return }
                }
            } catch { self.error=error.localizedDescription; updating=false }
        }
    }
    /// Returns how many earlier meetings the bridge relabelled when the owner name changed (0 otherwise).
    @discardableResult func saveReportSettings() async -> Int {
        // Settings are only ever pushed on top of what the bridge holds: a sheet opened before `report_settings`
        // landed used to send user_name "" and erase the stored name.
        if !settingsLoaded, let r=try? await request(["action":"report_settings"]) {
            let stored=ReportSettings.parse(r); if reportSettings.userName.isEmpty { reportSettings.userName=stored.userName }; storedUserName=stored.userName; settingsLoaded=true
        }
        do { let r=try await request(["action":"report_settings_set","changes":reportSettings.changes]); reportSettings=ReportSettings.parse(r); storedUserName=reportSettings.userName; return r["renamed_meetings"] as? Int ?? 0 } catch { self.error=error.localizedDescription; return 0 }
    }
    func loadGlossarySummary() async {
        guard let r=try? await request(["action":"glossary_summary"]) else { return }
        glossaryCount=r["count"] as? Int ?? 0; glossaryFromFile=r["from_file"] as? Int ?? 0; glossarySample=r["sample"] as? [String] ?? []
    }
    /// Import a Slack-agent glossary (JSON Lines with a "term" field) into the data folder.
    func importGlossary() async {
        let panel=NSOpenPanel();panel.canChooseDirectories=false;panel.allowsMultipleSelection=false
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"glossary_import","path":url.path]); activity="Sözlük içe aktarıldı · \(r["imported"] as? Int ?? 0) terim, \(r["skipped"] as? Int ?? 0) satır atlandı"; await loadGlossarySummary() }
        catch { self.error=error.localizedDescription }
    }
    /// Re-scan the selected meeting against the glossary; in cloud mode the analysis model reviews each proposal.
    func scanGlossary() async {
        guard let mid=selected, !busy else { return }
        var req:[String:Any]=["action":"glossary_suggest","meeting":mid]
        if transcriptionMode=="openrouter" { req["openrouter_model"]=analysisModel }
        do { let r=try await request(req); let n=(r["suggestions"] as? [[String:Any]])?.count ?? 0; activity="Sözlük taraması bitti · \(n) öneri"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    func applyGlossary(_ item:ReviewItem) async {
        guard let mid=selected, let seg=item.segment else { return }
        do { _=try await request(["action":"glossary_apply","meeting":mid,"segment":seg,"original":item.original,"replacement":item.replacement]); activity="Uygulandı · “\(item.original)” → “\(item.replacement)”"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    /// Apply every model-verified glossary proposal of the selected meeting in one pass; local-only guesses stay for manual review.
    func applyAllGlossary() async {
        guard let mid=selected, !busy else { return }
        do { let r=try await request(["action":"glossary_apply_all","meeting":mid,"verified_only":true]); activity="Sözlük · \(r["applied"] as? Int ?? 0) düzeltme uygulandı, \(r["remaining"] as? Int ?? 0) öneri elle kontrol bekliyor"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    /// Drop one glossary proposal without changing the text.
    func dismissGlossary(_ item:ReviewItem) async {
        guard let mid=selected, let seg=item.segment else { return }
        do { _=try await request(["action":"glossary_dismiss","meeting":mid,"segment":seg,"original":item.original]); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    func settings() async {
        do {
            vocabulary=try await request(["action":"vocabulary"])["text"] as? String ?? ""
            await loadGlossarySummary()
            storage=(try? await request(["action":"storage_report"])).map(StorageReport.parse)   // read-only walk; a failure hides the section only
            cost=try? await request(["action":"cost_report"])
            await loadSetupStatus()
            showSettings=true
        } catch { self.error=error.localizedDescription }
    }
    /// From the storage list: close the sheet first so the sidebar's confirmation dialog can present.
    func requestDelete(meetingID:String) {
        guard let meeting=meetings.first(where:{ $0.id==meetingID }) else { return }
        showSettings=false
        DispatchQueue.main.asyncAfter(deadline:.now()+0.35) { [weak self] in self?.deleteCandidate=meeting }
    }
    func saveVocabulary() async { do { _=try await request(["action":"vocabulary","text":vocabulary]); showSettings=false } catch { self.error=error.localizedDescription } }
    func play(_ row:Row) {
        guard let m=meeting else { return }
        play(source:row.source,start:row.start,seconds:row.end-row.start,metadata:m.metadata,key:"row:\(row.id)")
    }
    /// The same button stops what it started; ⌘. stops from anywhere. Boran, 10 Sep 2026: "play tuşuna basınca stop yok".
    func stopPlayback() { player?.stop(); player=nil; playback.key=nil }
    /// The glyph goes back to ▶ the moment the file ends, even when the span asked for more than the file has.
    private lazy var playbackEnd=PlaybackEnd { [weak self] p in Task { @MainActor in if self?.player===p { self?.stopPlayback() } } }
    /// One span of one meeting's audio. Takes the metadata rather than reading `meeting`, so the settings sheet
    /// can preview a turn from a meeting that is not the open one.
    func play(source:String,start rowStart:Double,seconds:Double,metadata:[String:Any],key:String) {
        guard !recording else { return }   // never play audio into the room during a recording
        if playback.key==key { stopPlayback(); return }
        do {
            var path=(metadata["paths"] as? [String:String])?[source]; var start=rowStart
            if path==nil, let dir=metadata["capture_dir"] as? String {
                let base=URL(fileURLWithPath:dir); let native=base.appendingPathComponent("capture-native.jsonl")
                let journal=FileManager.default.fileExists(atPath:native.path) ? native : base.appendingPathComponent("events.jsonl")
                let lines=try String(contentsOf:journal,encoding:.utf8).split(separator:"\n")
                for line in lines {
                    if let d=try? JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any], d["source"] as? String==source, let a=d["start"] as? Double, let duration=d["duration"] as? Double, rowStart>=a, rowStart<a+duration { path=d["path"] as? String; start=rowStart-a; break }
                }
            }
            guard let path=path else { throw NSError(domain:"MeetingOS",code:1,userInfo:[NSLocalizedDescriptionKey:"Ses dosyası bulunamadı"]) }
            stopPlayback(); let p=try AVAudioPlayer(contentsOf:URL(fileURLWithPath:path)); player=p; p.delegate=playbackEnd; p.currentTime=start; p.play(); playback.key=key
            Task { try? await Task.sleep(for:.seconds(max(0.1,seconds))); if self.player===p { self.stopPlayback() } }
        } catch { stopPlayback(); self.error=error.localizedDescription }
    }
}

func statusLabel(_ status:String)->String {
    ["not_started":"Kayıt başlayamadı", "pending_finalization":"Son işlem bekliyor", "capture_unknown":"Kayıt durumu belirsiz", "capturing":"Kaydediliyor", "complete":"Hazır", "processing":"İşleniyor", "provisional":"Canlı kayıt", "incomplete":"Kurtarılabilir", "failed":"İşlem başarısız", "canceled":"İptal edildi"][status] ?? status
}
@MainActor final class AppDelegate:NSObject,NSApplicationDelegate,UNUserNotificationCenterDelegate {
    static weak var model:Model?
    func applicationDidFinishLaunching(_ notification:Notification) {
        UNUserNotificationCenter.current().delegate=self
        if UserDefaults.standard.object(forKey:"zoomNotify") as? Bool ?? true { ZoomNotifier.register() }
        Self.model?.applyWindowPrivacy()   // the main window exists by now; the poll keeps it that way
    }
    nonisolated func userNotificationCenter(_ center:UNUserNotificationCenter,didReceive response:UNNotificationResponse,withCompletionHandler completionHandler:@escaping ()->Void) {
        let action=response.actionIdentifier
        Task { @MainActor in
            if action==ZoomNotifier.startAction || action==UNNotificationDefaultActionIdentifier, let m=Self.model, !m.recording { m.beginRecording(); m.showMainWindow() }
            completionHandler()
        }
    }
    /// A click on a `meetingos://join?…` invite link, or a double click on a `.meetingos-invite` file. Both
    /// arrive here: an app with an AppKit delegate that implements this never sees SwiftUI's `onOpenURL`, so
    /// this is the app's one and only door for URLs from outside. The transcript's own `meetingos://word`
    /// links never leave the process and never reach it.
    func application(_ application:NSApplication,open urls:[URL]) {
        Self.model?.handleIncoming(urls:urls)
    }
    func applicationShouldTerminate(_ sender:NSApplication) -> NSApplication.TerminateReply {
        Self.model?.saveUserNameOnQuit()
        guard let m=Self.model, m.job != nil || m.recordProcess != nil else { return .terminateNow }
        m.requestedQuit=true
        if m.recording { m.stop() }
        m.activity="İşlem güvenle tamamlandıktan sonra kapanacak…"
        return .terminateLater
    }
}
@main struct MeetingOSApp:App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject var model=Model()
    var body:some Scene {
        Window("Meeting OS",id:"main") { MeetingContent(m:model).preferredColorScheme(model.colorScheme).tint(MeetingStyle.accent).id(model.accentKey).onAppear { GlobalHotkeys.install { id in Task { @MainActor in AppDelegate.model?.hotkey(id) } } } }.windowStyle(.titleBar).defaultSize(width:1100,height:780).commands {
            CommandGroup(replacing:.undoRedo) { Button("Adlandırmayı geri al") { Task { await model.undoNaming() } }.keyboardShortcut("z",modifiers:.command).disabled(!model.canUndoNaming || model.busy) }
            CommandMenu("Toplantı") {
                Button("Toplantıyı sil…") { if let meeting=model.meeting { model.deleteCandidate=meeting } }.keyboardShortcut(.delete,modifiers:.command).disabled(model.meeting==nil || model.recording || model.meeting?.recoveryState=="active" || model.editRow != nil || model.showSettings || model.showShare || model.showOpenRouter || model.wordFix != nil)   // ⌘⌫ stays "delete to line start" inside any text field
            }
            CommandMenu("Git") {
                Button("Geri") { model.goBack() }.keyboardShortcut("[",modifiers:.command).disabled(model.backStack.isEmpty)
                Divider()
                Button("Konuşmada ara") { model.focusTranscriptSearch() }.keyboardShortcut("f",modifiers:.command)
                Button("Hafızada ara") { model.focusMemorySearch() }.keyboardShortcut("f",modifiers:[.command,.shift])
                Divider()
                Button("Transkript") { model.tab="transcript" }.keyboardShortcut("1",modifiers:.command)
                Button("Özet") { model.tab="analysis" }.keyboardShortcut("2",modifiers:.command)
                Button("Görevlerim") { model.tab="actions" }.keyboardShortcut("3",modifiers:.command)
                Button("Kontrol") { model.tab="review" }.keyboardShortcut("4",modifiers:.command)
                Button("Hafıza") { model.tab="memory" }.keyboardShortcut("5",modifiers:.command)
                Divider()
                Button("Dinlemeyi durdur") { model.stopPlayback() }.keyboardShortcut(".",modifiers:.command).disabled(model.editRow != nil || model.showSettings)   // ⌘. stays "cancel" while a sheet is up
            }
        }
        MenuBarExtra { QuickMenu(model:model) } label: {
            MenuBarLabel(model:model,recorder:model.recorder)
        }.menuBarExtraStyle(.menu)
    }
}


/// Recording-time state that changes every second. Observed only where it is shown.
@MainActor final class RecorderState:ObservableObject {
    @Published var elapsedText="00:00"
    @Published var captureDots:[String:String]=[:]
    @Published var recordingNotice=""
    /// "Disk azalıyor · 1,2 GB boş · kayıt 69 dk sonra durabilir". Seeded by ⌃⌥R when the volume is already
    /// tight, then kept honest by the helper's own `low_disk` line on every poll. Empty means there is room.
    @Published var lowDiskNotice=""
}

@MainActor final class JobState:ObservableObject { @Published var jobProgress="" }

struct MenuBarLabel:View {
    @ObservedObject var model:Model
    @ObservedObject var recorder:RecorderState
    var body:some View {
        // Discreet mode draws the idle glyph while recording: no red dot, no elapsed time, no animation, so the
        // menu bar looks the same recorded and not. "Kayıt sürüyor" lives in the menu behind it (QuickMenu).
        let look=DiscreetMode.menuBar(recording:model.recording,discreet:model.discreetMode,zoomOpen:model.zoomMeetingOpen,elapsed:recorder.elapsedText)
        if let text=look.text { Label(text,systemImage:look.glyph) } else { Image(systemName:look.glyph) }
    }
}
