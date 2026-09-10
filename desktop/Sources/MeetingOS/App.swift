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
        if flags.contains("provisional") { return "Geçici konuşmacı" }
        if !suggested.isEmpty { return suggested+"?" }  // borderline voice match awaiting one-click confirmation
        if flags.contains("possible_echo") { return "Hoparlör yankısı" }  // microphone picked up the speakers; not the user talking
        if flags.contains("cloud_transcript"), !speaker.isEmpty, speaker != "unknown" { return speaker }  // cloud path stores human-readable cluster labels
        if let tail=speaker.split(separator:":").last, tail.hasPrefix("S"), let n=Int(tail.dropFirst()) { return "Konuşmacı \(n+1)" }
        return "İsimsiz konuşmacı"
    }
    var notices:String {
        let labels=["cloud_transcript":"Bulut transkript · OpenRouter", "cloud_diarization":"Konuşmacı ayrımı · sağlayıcı", "possible_echo":"Hoparlör yankısı olabilir · mikrofon sistem sesini almış", "coarse_timing":"Yaklaşık konuşma aralığı", "imported_text":"Elle aktarılan metin", "speaker_unverified":"Konuşmacı adı doğrulanmadı", "provisional":"Canlı metin · değişebilir", "short_context_diarization":"Konuşmacı için kısa ses örneği", "speaker_ambiguous":"Konuşmacı belirsiz / sesler çakışıyor", "low_asr_confidence":"Bu bölümü dinleyerek kontrol edin", "possible_non_speech":"Konuşma dışı ses olabilir", "repetition":"Tekrar algılandı", "confidence_unavailable":"Güven ölçümü yok", "baseline_diarization":"Temel konuşmacı ayrımı"]
        let shown=flags.contains("cloud_transcript") ? flags.filter { !TranscriptBlocks.meetingWideFlags.contains($0) } : flags
        return shown.filter { $0 != "untimed" }.map { labels[$0] ?? $0 }.joined(separator:" · ")
    }
    var time:String { flags.contains("untimed") ? "" : String(format:"%02d:%02d",Int(start)/60,Int(start)%60) }
}
struct Profile:Identifiable, Equatable { let name:String; let model:String; let samples:Int; var id:String { name+model } }
struct Runtime:Decodable { let python:String; let repo:String }

func invoke(_ runtime:Runtime,_ request:[String:Any]) throws -> [String:Any] {
    let p=Process(); p.executableURL=URL(fileURLWithPath:runtime.python); p.arguments=["-m","meeting_os.desktop"]; p.currentDirectoryURL=URL(fileURLWithPath:runtime.repo)
    let key=OpenRouterCredential.environment(); if !key.isEmpty { p.environment=ProcessInfo.processInfo.environment.merging(key) { _,new in new } }
    let input=Pipe(), output=Pipe(); p.standardInput=input; p.standardOutput=output; p.standardError=FileHandle.nullDevice
    try p.run()
    let deadline=DispatchWorkItem { if p.isRunning { kill(-p.processIdentifier,SIGTERM); p.terminate() } }
    DispatchQueue.global().asyncAfter(deadline:.now()+10, execute:deadline)
    defer { deadline.cancel() }
    try input.fileHandleForWriting.write(contentsOf:JSONSerialization.data(withJSONObject:request)); try input.fileHandleForWriting.close()
    let data=output.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
    guard let result=try JSONSerialization.jsonObject(with:data) as? [String:Any] else { throw NSError(domain:"MeetingOS",code:1,userInfo:[NSLocalizedDescriptionKey:"Invalid local response"]) }
    if let message=result["error"] as? String { throw NSError(domain:"MeetingOS",code:2,userInfo:[NSLocalizedDescriptionKey:message]) }
    return result
}

@MainActor final class Model:ObservableObject {
    @Published var meetings:[Meeting]=[]; @Published var rows:[Row]=[] { didSet { rebuildBlocks(); shares=TalkShare.compute(rows) } }; @Published var profiles:[Profile]=[]
    @Published var selected:String? { didSet { if selected != oldValue { recordingNavigation.selectionChanged(); error=""; canUndoNaming=false; rows=[]; analysis=nil; search=""; pendingEvidence=nil; focusedSegment=nil; segmentsHash=""; intelHash=""; renaming=false; renameText="" } } }; @Published var search="" { didSet { focusedSegment=nil; pendingEvidence=nil; rebuildBlocks() } }; @Published var title=""; @Published var error=""
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
    @Published var tab="transcript" { didSet { if tab != "transcript" { pendingEvidence=nil } } }; @Published var analysis:[String:Any]?; @Published var actions:[ActionItem]=[]; @Published var drafts:[DraftItem]=[]
    @Published var memoryQuery=""; @Published var hits:[Evidence]=[]; @Published var answer=""; @Published var answerEvidence:[Evidence]=[]
    let runtime:Runtime; let dataDir=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/MeetingOS")
    @Published var focusedSegment:Int? { didSet { rebuildBlocks() } }
    @Published var pendingEvidence:Evidence?
    var recordingNavigation=RecordingNavigation()
    var progressURL:URL?;var jobStarted:Date?
    var resourceStopMessage=""
    var pressureSource:DispatchSourceMemoryPressure?
    var requestedQuit=false
    @Published var jobKind:String?; @Published var jobCanceled=false
    @Published var job:Process?; var recordingDir:URL?; var timer:Timer?; var player:AVAudioPlayer?; var refreshing=false
    init() {
        let url=Bundle.main.resourceURL!.appendingPathComponent("runtime.json")
        runtime=(try? JSONDecoder().decode(Runtime.self,from:Data(contentsOf:url))) ?? Runtime(python:"/usr/bin/false",repo:"/tmp")
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
        Task { await refresh() }
    }
    var meeting:Meeting? { meetings.first { $0.id==selected } }
    @Published var showEchoRows=false { didSet { rebuildBlocks() } }
    @Published var review:[ReviewItem]=[]
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
    @Published var analysisModel=UserDefaults.standard.string(forKey:"cloudAnalysisModel") ?? "openai/gpt-4.1-mini" { didSet { UserDefaults.standard.set(analysisModel,forKey:"cloudAnalysisModel") } }
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
    /// Names done → the summary is the next thing people read; refresh it once, quietly, instead of asking them to notice "güncel değil".
    func refreshSummaryIfNamesDone() {
        guard let mid=selected, meeting?.status=="complete", analysis?["stale"] as? Bool == true, !busy, !recording, recordProcess==nil, !zoomMeetingOpen else { return }   // recordProcess: the helper still drains after `recording` goes false
        guard !review.contains(where:{ ($0.kind=="unnamed_speaker" || $0.kind=="suggested_name") && !$0.speakerKey.isEmpty }) else { return }
        activity="İsimler tamam · özet isimlerle yenileniyor"; analyzeMeeting(mid)
    }
    var calendarAttendees:[String] { (meeting?.metadata["calendar"] as? [String:Any])?["attendees"] as? [String] ?? [] }
    @Published var readingMode=true
    @Published var showAsides=false
    @Published var hideFillers=UserDefaults.standard.object(forKey:"hideFillers") as? Bool ?? true { didSet { UserDefaults.standard.set(hideFillers,forKey:"hideFillers") } }
    var filteredRows:[Row] {
        if let id=focusedSegment { return rows.filter { $0.id==id } }
        let visible=CloudTranscription.visibleRows(rows,showEcho:showEchoRows)
        return search.isEmpty ? visible : visible.filter { ($0.text+" "+$0.label).localizedCaseInsensitiveContains(search) }
    }
    /// Reading-view paragraphs, rebuilt only when their inputs change. The 2-second status poll must not
    /// re-run block building for every published field (a 1500-row day would pin the CPU again).
    @Published private(set) var blocks:[TranscriptBlock]=[]
    private var blocksKey:Int=0
    func rebuildBlocks() {
        var h=Hasher(); h.combine(rows.count); h.combine(rows.last?.id ?? -1); h.combine(showEchoRows); h.combine(search); h.combine(focusedSegment ?? -1); h.combine(rows.map { $0.name+$0.text }.joined().hashValue)
        let key=h.finalize(); if key==blocksKey && !blocks.isEmpty { return }
        blocksKey=key; blocks=TranscriptBlocks.build(filteredRows)
    }
    func request(_ req:[String:Any]) async throws -> [String:Any] { try await Bridge.call(runtime,req) }
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
        if recording || pollTick%3==0 { let hint=MicrophoneHint.current(); if hint != microphoneHint { microphoneHint=hint } }   // IOKit query: every poll while recording, every third otherwise
        if let process=job, let bytes=ResourceGuard.footprint(pid:process.processIdentifier), bytes>ResourceGuard.budget(physical:ProcessInfo.processInfo.physicalMemory) { stopForResources() }
        if job != nil, let started=jobStarted {
            let elapsed=Int(Date().timeIntervalSince(started))
            let progress=progressURL.flatMap { try? Data(contentsOf:$0) }.flatMap { try? JSONDecoder().decode(JobProgress.self,from:$0) }
            let line=(progress?.label ?? activity)+" · \(elapsed/60) dk \(elapsed%60) sn"; if jobs.jobProgress != line { jobs.jobProgress=line }
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
            if !restoredOnLaunch {
                restoredOnLaunch=true
                if !recording, job==nil, let restore=RelaunchRestore.pick(meetings:meetings) { selected=restore.id; restoredMeeting=restore.id }
            }
            if selected==nil && !recording { selected=meetings.first?.id }
            if ZoomWatch.shouldScan(tick:pollTick,autoRecord:zoomAutoRecord,zoomRunning:lastZoomState.running) { lastZoomState=ZoomWatch.state() }   // a full window-list walk on the main actor: only hands-free recording needs it every poll
            let zoomState=lastZoomState; let zoomNow=zoomState.open
            if zoomNow && !zoomMeetingOpen && !recording && zoomNotify && !zoomAutoRecord { ZoomNotifier.notifyIfNeeded() }
            if !zoomNow { ZoomNotifier.reset() }
            if zoomMeetingOpen != zoomNow { zoomMeetingOpen=zoomNow }   // same value would still fire objectWillChange and re-lay out every paragraph
            applyLivePriority(zoomOpen:zoomState.strict || recordProcess != nil)   // any live recording (Zoom, Meet, in person) gets the same protection
            heartbeatIfDue()
            updateBlockedHint()
            idleRetryIfDue()
            switch zoomAuto.evaluate(zoomOpen:zoomState.strict,meetingLikely:zoomState.running && (recording ? AudioInUse.microphoneBusy() : false),recording:recording,busy:false,enabled:zoomAutoRecord && !requestedQuit) {
            case .start: if let line=LaunchOutcome.activity(started:start(),onStart:"Zoom toplantısı açıldı · kayıt kendiliğinden başladı",onRefusal:LaunchOutcome.recordBusy) { activity=line }
            case .stop: stop(); activity="Zoom toplantısı kapandı · kayıt bitiriliyor"
            case nil: break
            }
            if recording, let started=recordStartedAt { let s=Int(Date().timeIntervalSince(started)); let t=String(format:"%02d:%02d",s/60,s%60); if recorder.elapsedText != t { recorder.elapsedText=t } }
            if !recording && !zoomMeetingOpen && !queuedNotifications.isEmpty { for (t,b) in queuedNotifications { deliver(t,b) }; queuedNotifications.removeAll() }   // meeting-safe mode: notifications wait
            if lastUpdateCheck==nil || Date().timeIntervalSince(lastUpdateCheck!) >= 6*3600 { Task { await checkForUpdates() } }
            if NSApp.isActive, let last=lastUpdateCheck, Date().timeIntervalSince(last) >= 60*60 { Task { await checkForUpdates() } }
            if wanted==selected {
                var changed=false
                if let raw=result["segments"] as? [[String:Any]] { let nextRows=raw.map(Row.init); changed=rows != nextRows; if changed { rows=nextRows } }
                segmentsHash=result["segments_hash"] as? String ?? ""; lastSegmentsMeeting=wanted
                resolvePendingEvidence()
                let intel=result["intel_hash"] as? String ?? ""
                if intel != intelHash || changed || analysis==nil && actions.isEmpty { intelHash=intel; try await refreshIntelligence(wanted) }
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
            if !isRecord { jobKind=args.first;jobStopsOnPressure=ResourceGuard.stopsOnPressure(jobArguments:args); progressURL=progress;jobStarted=Date();jobs.jobProgress="İşlem başlatılıyor" }
            let p=Process();p.environment=ProcessInfo.processInfo.environment.merging(["MEETING_OS_PROGRESS_PATH":progress.path]) { _,new in new }.merging(jobEnvironment) { _,new in new }.merging(JobPriority.environment(args:args,zoomOpen:zoomMeetingOpen || recordProcess != nil,idle:idle)) { _,new in new }.merging(["MEETING_OS_LOW_PRIORITY_FLAG":lowPriorityFlag.path]) { _,new in new }.merging(OpenRouterCredential.environment()) { _,new in new };p.qualityOfService=JobPriority.qos(args:args,zoomOpen:zoomMeetingOpen || recordProcess != nil,idle:idle); p.executableURL=URL(fileURLWithPath:runtime.python); p.arguments=["-m","meeting_os"]+args; p.currentDirectoryURL=URL(fileURLWithPath:runtime.repo); p.standardOutput=handle; p.standardError=handle
            p.terminationHandler={ [weak self] process in
                try? handle.close()
                let jobError=ErrorPresentation.logSummary(log)
                Task { @MainActor in
                    guard let self=self else { return }
                    if isRecord { self.recordProcess=nil; self.recordStartedAt=nil; try? FileManager.default.removeItem(at:progress) }
                    else { self.job=nil; self.jobKind=nil; self.busy=false; self.jobs.jobProgress=""; self.progressURL=nil; self.jobStarted=nil; try? FileManager.default.removeItem(at:progress) }
                    if process.terminationStatus != 0 && !self.jobCanceled { self.error=self.resourceStopMessage.isEmpty ? jobError : self.resourceStopMessage }
                    complete(process.terminationStatus==0 && self.resourceStopMessage.isEmpty && !self.jobCanceled); await self.refresh()
                    // Quitting is not the moment to start an upload: the queued meetings keep their audio and the
                    // idle queue picks them up on the next launch. Popping here would begin a job we cannot finish.
                    if !isRecord, !self.requestedQuit, let next=self.finalizeQueue.first { self.finalizeQueue.removeFirst(); self.finalizeWithOpenRouter(next,model:self.cloudModel) }   // meetings that ended while a job ran
                    if self.requestedQuit && self.job==nil && self.recordProcess==nil { NSApp.reply(toApplicationShouldTerminate:true) }
                }
            }
            try p.run(); error=""
            if isRecord { recordProcess=p; recordStartedAt=Date() } else { job=p; busy=true; jobBackgrounded=false }
            return true
        } catch { self.error=error.localizedDescription; if isRecord { recording=false; recordingNavigation.cancel() } else { busy=false; jobKind=nil }; return false }
    }
    /// Returns false when the previous helper is still draining: the caller must not claim a recording started.
    @discardableResult func start()->Bool {
        guard recordProcess==nil else { return false }
        recordingNavigation.begin()
        let dir=dataDir.appendingPathComponent("recordings/"+UUID().uuidString)
        recordingDir=dir; recording=true; markerCount=0; recorder.recordingNotice=""; continuitySeen=nil; sleptAt=nil; activity="Kayıt hazırlanıyor · macOS izinleri açık olmalı"; DisplaySleepGuard.begin(); if showRecorderPanel { RecorderPanel.show(model:self) }
        pendingCalendar=useCalendar ? CalendarContext.current() : nil
        let name=title.isEmpty ? (pendingCalendar?.title ?? Date().formatted(Date.FormatStyle(date:.abbreviated,time:.shortened,locale:Locale(identifier:"tr_TR")))) : title   // "9 Eyl 2026 14:05"
        if title.isEmpty, let cal=pendingCalendar { activity="Takvimden: \(cal.title)"+(cal.attendees.isEmpty ? "" : " · \(cal.attendees.count) katılımcı") }
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
            if enroll { activity=((result["profile_saved"] as? Bool)==true ? "Konuşmacı adlandırıldı · Ses profili kaydedildi, sonraki toplantılarda otomatik tanınır" : "Konuşmacı adlandırıldı · Yeterli temiz ses olmadığı için profil kaydedilmedi")+adaptationNote(result) } else { activity="Konuşmacı yalnız bu toplantıda adlandırıldı"+adaptationNote(result) }
            canUndoNaming=true
            await refresh(); await loadReview(); refreshSummaryIfNamesDone()
        } catch { self.error=error.localizedDescription }
    }
    /// One click turns a “Sol Üst?” suggestion into the cluster name and, when there is enough speech, a profile sample.
    func confirmSuggestion(_ row:Row) async {
        guard !row.suggested.isEmpty, let mid=selected, !busy else { return }
        do { _=try await request(["action":"label_speaker","meeting":mid,"speaker":row.speaker,"name":row.suggested,"enroll":true]); activity="“\(row.suggested)” onaylandı · profil güncellendi"; await refresh() }
        catch { self.error=error.localizedDescription }
    }
    func saveText() async {
        guard let row=editRow, let mid=selected else { return }
        do { _=try await request(["action":"edit_text","meeting":mid,"segment":row.id,"text":editText]); editRow=nil; await refresh() } catch { self.error=error.localizedDescription }
    }
    func deleteMeeting(_ meeting:Meeting) async {
        guard !busy else { return }
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
    var lastZoomState:(open:Bool,strict:Bool,running:Bool)=(false,false,false)
    /// Talk shares depend on rows only; computed once per row change instead of in the Özet body every poll.
    @Published private(set) var shares:[TalkShare]=[]
    @Published var dueSuggestions:[String:String]=[:]
    @Published var questions:[QuestionGroup]=[]; @Published var scorePeriod:[String:Any]?; @Published var scoreMeetings:[ScoreMeeting]=[]
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
        tab="transcript"; search=""; focusedSegment=nil; revealTarget=id; revealToken+=1; highlighted=id
        let token=revealToken
        DispatchQueue.main.asyncAfter(deadline:.now()+2.5) { [weak self] in if self?.revealToken==token { self?.highlighted=nil } }
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
    @Published var showRecorderPanel=UserDefaults.standard.object(forKey:"showRecorderPanel") as? Bool ?? true { didSet { UserDefaults.standard.set(showRecorderPanel,forKey:"showRecorderPanel"); if !showRecorderPanel { RecorderPanel.hide() } else if recording { RecorderPanel.show(model:self) } } }
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
        if recording || zoomMeetingOpen { queuedNotifications.append((title,body)); return }
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
        play(source:c.source,start:c.start,seconds:c.seconds,metadata:m.metadata)
    }
    func renameProfile(_ name:String,to newName:String) async {
        do { let r=try await request(["action":"rename_profile","name":name,"new_name":newName]); activity=(r["merged"] as? Bool)==true ? "“\(name)” → “\(newName)” birleştirildi" : "“\(name)” → “\(newName)” yeniden adlandırıldı"; await refresh() } catch { self.error=error.localizedDescription }
    }
    func explainIdentity(_ row:Row) async {
        guard let mid=selected else { return }
        explanation=(try? await request(["action":"explain_identity","meeting":mid,"speaker":row.speaker])).map(IdentityExplanation.parse)
    }
    func showMainWindow() { NSApp.activate(ignoringOtherApps:true); NSApp.windows.first(where:{ $0.title=="Meeting OS" })?.makeKeyAndOrderFront(nil) }
    /// Global hot key dispatch (⌃⌥R / ⌃⌥M) — same guards as the buttons.
    func hotkey(_ id:UInt32) {
        if id==GlobalHotkeys.record {
            if recording {
                let age=Date().timeIntervalSince(recordStartedAt ?? .distantPast)
                if age<3 { return }   // key repeat / double press right after start: ignore
                if age<15 { if let armed=stopArmedAt, Date().timeIntervalSince(armed)<2 { stop() } else { stopArmedAt=Date(); activity="Bitirmek için ⌃⌥R’ye bir kez daha bas" }; return }
                stop()
            } else if let line=LaunchOutcome.activity(started:start(),onStart:LaunchOutcome.recordStarted,onRefusal:LaunchOutcome.recordBusy) { activity=line }
        }
        else if id==GlobalHotkeys.mark, recording { markMoment("important") }
    }
    @Published var update:UpdateInfo?; @Published var updating=false; @Published var reportSettings=ReportSettings(shareReports:true,shareText:false,autoUpdate:false,reportDir:"")
    /// The person this Mac belongs to (Ayarlar → Genel → Adınız); never a hard-coded name.
    var userName:String { let n=reportSettings.userName.trimmingCharacters(in:.whitespacesAndNewlines); return n.isEmpty ? "Boran" : n }
    var lastUpdateCheck:Date?
    /// Called after the first snapshot and every six hours; a fetch, nothing more.
    func checkForUpdates(force:Bool=false) async {
        if !force, let last=lastUpdateCheck, Date().timeIntervalSince(last) < 60*60 { return }   // on launch, on activation, at most hourly
        lastUpdateCheck=Date()
        if let status=try? await request(["action":"update_status"]), let state=status["state"] as? String, let msg=status["message"] as? String, state != "running", UserDefaults.standard.string(forKey:"lastShownUpdate") != (status["time"] as? String ?? "") {
            UserDefaults.standard.set(status["time"] as? String ?? "",forKey:"lastShownUpdate"); activity=(state=="done" ? "Güncelleme tamam · " : "Güncelleme başarısız · ")+msg
        }
        if let r=try? await request(["action":"update_check"]) { update=UpdateInfo.parse(r) }
        if let r=try? await request(["action":"report_settings"]) { reportSettings=ReportSettings.parse(r) }
        if reportSettings.autoUpdate, update?.available==true, job==nil, !recording, recordProcess==nil, !zoomMeetingOpen { startUpdate() }
    }
    /// Hands over to the detached updater and quits; the updater rebuilds, re-signs and relaunches.
    func startUpdate() {
        guard job==nil, !recording, !updating else { return }
        if recordProcess != nil { activity="Önceki kayıt kapanıyor · birkaç saniye sonra güncelleyin"; return }   // the updater would wait 60 s on the draining helper and abort
        if zoomMeetingOpen { activity="Zoom toplantısı açıkken güncelleme yapılmaz · toplantı bitince tekrar deneyin"; return }   // a rebuild would steal the meeting's CPU
        updating=true; activity="Güncelleniyor · uygulama kapanıp yeniden açılacak"
        Task { do { _=try await request(["action":"update_start"]); try? await Task.sleep(nanoseconds:600_000_000); NSApp.terminate(nil) } catch { self.error=error.localizedDescription; updating=false } }
    }
    func saveReportSettings() async {
        do { let r=try await request(["action":"report_settings_set","changes":reportSettings.changes]); reportSettings=ReportSettings.parse(r) } catch { self.error=error.localizedDescription }
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
        play(source:row.source,start:row.start,seconds:row.end-row.start,metadata:m.metadata)
    }
    /// One span of one meeting's audio. Takes the metadata rather than reading `meeting`, so the settings sheet
    /// can preview a turn from a meeting that is not the open one.
    func play(source:String,start rowStart:Double,seconds:Double,metadata:[String:Any]) {
        guard !recording else { return }   // never play audio into the room during a recording
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
            player?.stop(); let p=try AVAudioPlayer(contentsOf:URL(fileURLWithPath:path)); player=p; p.currentTime=start; p.play()
            Task { try? await Task.sleep(for:.seconds(max(0.1,seconds))); if self.player===p { p.stop() } }
        } catch { self.error=error.localizedDescription }
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
    }
    nonisolated func userNotificationCenter(_ center:UNUserNotificationCenter,didReceive response:UNNotificationResponse,withCompletionHandler completionHandler:@escaping ()->Void) {
        let action=response.actionIdentifier
        Task { @MainActor in
            if action==ZoomNotifier.startAction || action==UNNotificationDefaultActionIdentifier, let m=Self.model, !m.recording, !m.busy { m.start(); m.showMainWindow() }
            completionHandler()
        }
    }
    func applicationShouldTerminate(_ sender:NSApplication) -> NSApplication.TerminateReply {
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
            CommandMenu("Git") {
                Button("Konuşmada ara") { model.focusTranscriptSearch() }.keyboardShortcut("f",modifiers:.command)
                Button("Hafızada ara") { model.focusMemorySearch() }.keyboardShortcut("f",modifiers:[.command,.shift])
                Divider()
                Button("Transkript") { model.tab="transcript" }.keyboardShortcut("1",modifiers:.command)
                Button("Özet") { model.tab="analysis" }.keyboardShortcut("2",modifiers:.command)
                Button("Görevlerim") { model.tab="actions" }.keyboardShortcut("3",modifiers:.command)
                Button("Kontrol") { model.tab="review" }.keyboardShortcut("4",modifiers:.command)
                Button("Hafıza") { model.tab="memory" }.keyboardShortcut("5",modifiers:.command)
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
}

@MainActor final class JobState:ObservableObject { @Published var jobProgress="" }

struct MenuBarLabel:View {
    @ObservedObject var model:Model
    @ObservedObject var recorder:RecorderState
    var body:some View {
        if model.recording { Label(recorder.elapsedText,systemImage:"record.circle.fill") } else { Image(systemName:model.zoomMeetingOpen ? "video.badge.waveform" : "waveform") }
    }
}
