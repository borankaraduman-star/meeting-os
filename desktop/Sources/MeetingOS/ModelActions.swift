import SwiftUI
import AppKit
import UniformTypeIdentifiers
import UserNotifications

/// Model behaviour that is not the poll loop: exports, cross-meeting loaders, housekeeping, naming.
extension Model {
    /// Draft agenda for the next meeting from recent open tasks, questions and decisions; saved where the user chooses.
    /// Brief for the next calendar meeting (or the selected meeting's attendees): each person's open promises, questions and decisions.
    func exportBrief() async {
        var title=""; var attendees:[String]=[]
        if useCalendar, let e=CalendarContext.upcoming() { title=e.title; attendees=e.attendees }
        if attendees.isEmpty { attendees=calendarAttendees; if title.isEmpty { title=meeting?.title ?? "" } }
        guard !attendees.isEmpty else { error=useCalendar ? "Yakın takvim etkinliğinde katılımcı adı yok; brifing için katılımcılı bir etkinlik gerekir." : "Brifing için takvim bağlamını açın (Ayarlar → Genel) ya da katılımcılı bir toplantı seçin."; return }
        let panel=NSSavePanel(); panel.nameFieldStringValue="brifing-\(title.isEmpty ? "toplanti" : String(title.prefix(30))).md"; panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"brief","title":title,"attendees":attendees,"path":url.path]); activity="Brifing kaydedildi · \(r["people"] as? Int ?? 0) kişi, \(r["owed"] as? Int ?? 0) açık söz, \(r["questions"] as? Int ?? 0) soru" }
        catch { self.error=error.localizedDescription }
    }

    func exportAgenda() async {
        let panel=NSSavePanel();panel.nameFieldStringValue="sonraki-toplanti-gundemi.md";panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"agenda","path":url.path,"limit":5]); activity="Gündem taslağı kaydedildi · \(r["open_tasks"] as? Int ?? 0) açık görev, \(r["questions"] as? Int ?? 0) soru, \(r["decisions"] as? Int ?? 0) karar" }
        catch { self.error=error.localizedDescription }
    }

    /// End-of-day personal digest: today's tasks, expected answers and decisions that concern the user, with sources; saved where the user chooses.
    func exportDigest() async {
        let formatter=DateFormatter();formatter.dateFormat="yyyy-MM-dd"
        let panel=NSSavePanel();panel.nameFieldStringValue="gun-sonu-ozeti-\(formatter.string(from:Date())).md";panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"digest","path":url.path]); activity="Gün sonu özeti kaydedildi · \(r["meetings"] as? Int ?? 0) toplantı, \(r["tasks"] as? Int ?? 0) söz, \(r["questions"] as? Int ?? 0) soru, \(r["decisions"] as? Int ?? 0) karar" }
        catch { self.error=error.localizedDescription }
    }

    func exportWeeklyDigest() async {
        let f=DateFormatter(); f.dateFormat="yyyy-MM-dd"; let to=Date(); let from=Calendar.current.date(byAdding:.day,value:-6,to:to) ?? to
        let panel=NSSavePanel(); panel.nameFieldStringValue="hafta-ozeti-\(f.string(from:to)).md"; panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"digest","path":url.path,"from":f.string(from:from),"to":f.string(from:to)]); activity="Hafta özeti kaydedildi · \(r["meetings"] as? Int ?? 0) toplantı, \(r["decisions"] as? Int ?? 0) karar, \(r["tasks"] as? Int ?? 0) söz" }
        catch { self.error=error.localizedDescription }
    }

    func loadDecisions(query:String) async {
        guard !recording else { return }
        if let r=try? await request(["action":"decision_log","query":query,"limit":200]) {
            decisions=(r["decisions"] as? [[String:Any]] ?? []).enumerated().map { DecisionEntry($0.element,index:$0.offset) }
            decisionStaleMeetings=r["stale_meetings"] as? Int ?? Set(decisions.filter { $0.stale }.map { $0.meeting }).count
            decisionLive=r["live"] as? Int ?? decisions.filter { !$0.superseded }.count
            decisionSuperseded=r["superseded"] as? Int ?? decisions.filter { $0.superseded }.count
        }
    }

    func exportDecisions(query:String) async {
        let panel=NSSavePanel(); panel.nameFieldStringValue="karar-defteri.md"; panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"decision_log_export","path":url.path,"query":query]); activity="Karar defteri kaydedildi · \(r["decisions"] as? Int ?? 0) karar" } catch { self.error=error.localizedDescription }
    }

    func loadWaiting() async {
        guard !recording else { return }
        if let r=try? await request(["action":"waiting_board"]) {
            waiting=(r["people"] as? [[String:Any]] ?? []).map(WaitingPerson.init)
            waitingStaleMeetings=r["stale_meetings"] as? Int ?? Set(waiting.flatMap { $0.items }.filter { $0.stale }.map { $0.meeting }).count
        }
    }

    func loadReviewDebt() async {
        guard !recording else { return }
        if let r=try? await request(["action":"review_debt","days":7]) {
            debt=(r["items"] as? [[String:Any]] ?? []).map(DebtItem.init)
            let counts=r["counts"] as? [String:Int] ?? [:]
            let names=["unnamed_speaker":"isimsiz konuşmacı","suggested_name":"isim onayı","glossary":"sözlük","task_owner":"sahipsiz görev","short_match":"kısa eşleşme","ambiguous":"çakışma","marker":"işaret","word":"kelime"]
            debtSummary=counts.sorted { $0.value>$1.value }.map { "\($0.value) \(names[$0.key] ?? $0.key)" }.joined(separator:", ")
        }
    }

    func loadQuestions(query:String) async {
        guard !recording else { return }
        if let r=try? await request(["action":"question_radar","query":query,"limit":100]) {
            questions=(r["groups"] as? [[String:Any]] ?? []).enumerated().map { QuestionGroup($0.element,index:$0.offset) }
            questionStaleMeetings=r["stale_meetings"] as? Int ?? questions.filter { $0.stale }.count
        }
    }

    func loadPeriodScorecard() async {
        guard !recording else { return }
        if let r=try? await request(["action":"scorecard"]) { scorePeriod=r["period"] as? [String:Any]; scoreMeetings=(r["meetings"] as? [[String:Any]] ?? []).map(ScoreMeeting.init) }
    }

    /// One search field for the whole Hafıza tab: the active segment decides what it queries.
    func runMemoryQuery(mode:String) async {
        switch mode { case "decisions": await loadDecisions(query:memoryQuery); case "questions": await loadQuestions(query:memoryQuery); case "waiting": await loadWaiting(); default: if !memoryQuery.isEmpty { await memorySearch() } }
    }

    /// `recording` goes false the moment ⌃⌥R is pressed, but the helper keeps writing for another 15–30 s.
    /// Housekeeping must wait for the process to be gone, not for the flag — that drain is the recording.
    func heartbeatIfDue() {
        guard !recording, recordProcess==nil, job==nil, lastHeartbeat.map({ Date().timeIntervalSince($0) >= 3600 }) ?? true else { return }
        lastHeartbeat=Date()
        Task {
            // P0-3: the bundle's own CFBundleShortVersionString under `app.version` is what the Python side prefers;
            // no `commit` is sent, so the bridge falls back to the checkout's git hash for that.
            _=try? await request(["action":"heartbeat","app":["version":UpdateInfo.appVersion,"bridge":BridgeStats.shared.snapshot]])
            // Not on the poll's bridge: the archive pass is seconds per meeting and the ten-second watchdog was
            // SIGTERMing it every hour, so a library that had fallen behind could never catch up.
            if !recording, recordProcess==nil, job==nil, let r=try? await requestSlow(["action":"storage_housekeeping"]) {
                let archived=r["archived_bytes"] as? Int ?? 0, removed=r["removed_bytes"] as? Int ?? 0
                // One retention setting deletes a whole week of recordings on the same day; the warning comes first,
                // while marking a meeting "Sesi koru" (or widening the setting) can still save it.
                // Said once per countdown step (3 → 2 → 1 → 0 days), not every hour: the status line belongs to what the user just did.
                if let w=r["retention_warning"] as? [String:Any], let line=w["line"] as? String {
                    let key="retentionWarned:\(w["days_left"] as? Int ?? -1):\(w["meetings"] as? Int ?? 0)"
                    if !UserDefaults.standard.bool(forKey:key) { UserDefaults.standard.set(true,forKey:key); activity=line }
                }
                else if archived+removed>0 { activity="Depolama · \(StorageReport.format(bytes:archived)) sıkıştırıldı, \(StorageReport.format(bytes:removed)) eski ses silindi" }
            }
        }
    }

    /// A wrong key or an empty balance is the user's to fix, so the hint stands whatever the retry toggle says —
    /// and says so once a day at most, passively, never while a meeting is on.
    func updateBlockedHint() {
        let blocked=meetings.filter { ["auth","credit"].contains($0.cloudKind ?? "") }.map { ["kind":$0.cloudKind ?? ""] }
        let hint=IdleRetry.blockedHint(blocked) ?? ""
        if blockedHint != hint { blockedHint=hint }
        guard !hint.isEmpty, IdleRetry.shouldNotifyBlocked(count:blocked.count,last:lastBlockedNotice) else { return }
        lastBlockedNotice=Date(); notifyDone("Bulut yazıya çevirme bekliyor",hint)
    }

    /// One bridge call per ten idle minutes, on the existing poll: which meeting did OpenRouter refuse, and
    /// may we try it again now? The first candidate goes through the ordinary finalize path at background
    /// priority; key/credit failures only raise a standing hint, because retrying them would change nothing.
    func idleRetryIfDue() {
        guard IdleRetry.shouldAsk(enabled:reportSettings.autoRetry,recording:recording || recordProcess != nil,hasJob:job != nil,queued:!finalizeQueue.isEmpty,
                                  zoomOpen:zoomMeetingOpen,pressureAt:memoryPressureAt,last:lastIdleRetry) else { return }
        lastIdleRetry=Date()
        Task { [weak self] in
            guard let self, let r=try? await self.request(["action":"retry_candidates"]) else { return }
            // The answer may be seconds old: everything is checked again before a process is started.
            guard self.reportSettings.autoRetry, !self.recording, self.recordProcess==nil, self.job==nil, self.finalizeQueue.isEmpty, !self.zoomMeetingOpen,
                  let first=(r["candidates"] as? [[String:Any]])?.first, let mid=first["meeting"] as? String else { return }
            self.idleRetry=true
            self.activity="Boşta yeniden deneniyor · “\((first["title"] as? String ?? "").prefix(40))”"
            self.finalizeWithOpenRouter(mid,model:self.cloudModel)
        }
    }

    func applyLivePriority(zoomOpen:Bool) {
        guard let p=job, jobKind != "record" else { if jobBackgrounded { jobBackgrounded=false; try? FileManager.default.removeItem(at:lowPriorityFlag) }; return }
        guard zoomOpen != jobBackgrounded else { return }
        jobBackgrounded=zoomOpen
        setpriority(PRIO_DARWIN_PROCESS,id_t(p.processIdentifier),zoomOpen ? PRIO_DARWIN_BG : 0)   // 0 = PRIO_DARWIN_NORMAL (not exported to Swift)
        if zoomOpen { try? Data().write(to:lowPriorityFlag); activity=recording ? "Kayıt sürüyor · arka plan işi yavaşlatıldı, tek yükleyici" : "Zoom toplantısı açıldı · arka plan işi yavaşlatıldı, tek yükleyici" }
        else { try? FileManager.default.removeItem(at:lowPriorityFlag) }   // silent: the recording's own completion line is what the user should read
    }

    /// One-shot self-test through the bridge (helper --self-test, ffmpeg, sqlite quick_check, disk, key…). Never while recording.
    func runProbe() async {
        guard !recording, !busy else { return }
        probeLines=["Öz-test çalışıyor…"]
        do { let r=try await request(["action":"probe"])
            let items=r["items"] as? [[String:Any]] ?? []
            probeLines=[r["summary"] as? String ?? ""]+items.map { i in
                let ok=i["ok"] as? Bool ?? false; let fix=(i["fix"] as? String).map { " → "+$0 } ?? ""
                return (ok ? "✔ " : ((i["level"] as? String)=="warning" ? "! " : "✘ "))+(i["detail"] as? String ?? "")+(ok ? "" : fix) } }
        catch { probeLines=["Öz-test çalıştırılamadı: \(error.localizedDescription)"] }
    }
    func loadMaintenance() async { maintenance=try? await request(["action":"maintenance"]) }
    func deleteWeakSample(_ id:Int) async {
        do { _=try await request(["action":"delete_sample","sample":id]); activity="Zayıf ses örneği silindi"; await loadMaintenance(); await refresh() } catch { self.error=error.localizedDescription }
    }
    // MARK: - Kelimeyi bir kez düzelt, uygulama öğrensin
    /// One sentence for both entry points, so the promise reads the same wherever the word was taught.
    static func wordLearnedLine(original:String,replacement:String,fixes:Int)->String {
        "“\(original)” → “\(replacement)” · bu toplantıda \(fixes) yerde düzeltildi · öğrenildi; sonraki kayıtlarda aynı yazım düzeltilir, yakınları Kontrol'e önerilir"
    }
    /// Teach one word from the segment editor: every occurrence in this meeting is fixed now, and the rule
    /// is remembered so near-miss spellings in later meetings correct themselves.
    func learnWord(original:String,replacement:String) async {
        guard let mid=selected else { return }
        let from=original.trimmingCharacters(in:.whitespacesAndNewlines), to=replacement.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !from.isEmpty, !to.isEmpty, from != to else { return }
        do { let r=try await request(["action":"learn_word","meeting":mid,"original":from,"replacement":to])
            editRow=nil
            activity=Model.wordLearnedLine(original:from,replacement:to,fixes:r["fixes"] as? Int ?? r["segments"] as? Int ?? 0)
            await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    /// The same teaching, started from a Kontrol item rather than the segment editor.
    func applyWord(_ item:ReviewItem) async {
        guard let mid=selected, !item.original.isEmpty, !item.replacement.isEmpty else { return }
        do { let r=try await request(["action":"word_apply","meeting":mid,"original":item.original,"replacement":item.replacement])
            activity=Model.wordLearnedLine(original:item.original,replacement:item.replacement,fixes:r["fixes"] as? Int ?? r["segments"] as? Int ?? 0)
            await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    /// "Bu doğru": the suspicious word was spelled right all along; drop the item without touching the text.
    func dismissWord(_ item:ReviewItem) async {
        guard let mid=selected, !item.original.isEmpty else { return }
        do { _=try await request(["action":"word_dismiss","meeting":mid,"original":item.original]); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    /// Ayarlar → Sesler ve sözlük opens the learned-word list; nothing loads it on the poll.
    func loadWordRules() async {
        guard let r=try? await request(["action":"word_rules"]) else { return }
        wordRules=(r["rules"] as? [[String:Any]] ?? []).map(WordRule.init)
    }
    func forgetWord(_ original:String) async {
        guard !original.isEmpty else { return }
        do { let r=try await request(["action":"forget_word","original":original])
            let segments=r["segments"] as? Int ?? 0, meetings=r["meetings"] as? Int ?? 0, kept=r["kept"] as? Int ?? 0
            // A segment the user edited after the word was taught keeps their sentence; saying how many were
            // left is the difference between "everything is back" and a silent hole in the undo.
            let undone=segments>0 ? " · \(meetings) toplantıda \(segments) bölüm geri alındı" : ""
            let left=kept>0 ? " · \(kept) bölüm elle düzenlendiği için bırakıldı" : ""
            activity="“\(original)” unutuldu · artık kendiliğinden düzeltilmez"+undone+left
            await loadWordRules()
            if segments>0 { await refresh() } }
        catch { self.error=error.localizedDescription }
    }
    func rejectRule(_ original:String) async {
        guard !original.isEmpty else { return }
        do { _=try await request(["action":"reject_rule","original":original]); activity="Kural kapatıldı · “\(original)” artık kendiliğinden düzeltilmez"; await loadMaintenance() } catch { self.error=error.localizedDescription }
    }
    func loadSetupStatus() async {
        var checks=SetupStatus.permissionChecks(calendarWanted:useCalendar)
        let settings=await UNUserNotificationCenter.current().notificationSettings()
        checks.append(SetupStatus.notificationCheck(settings))
        if let r=try? await request(["action":"setup_status"]) { checks+=SetupStatus.serviceChecks(r,repo:runtime.repo,divergedNotice:update?.divergedNotice ?? "") }
        setupChecks=checks
    }

    /// Send one task to Apple Reminders; asks for reminders access on first use.
    func addReminder(_ item:ActionItem) {
        let go={ [weak self] in
            guard let self=self else { return }
            do { try RemindersBridge.add(title:item.title,meetingTitle:item.meetingTitle,owner:item.owner,due:item.due,dueDate:item.dueDate.isEmpty ? nil : item.dueDate); self.activity="Hatırlatıcılar’a eklendi · “\(item.title.prefix(60))”"+(item.dueDate.isEmpty ? "" : " · \(MeetingDates.dayLabel(item.dueDate)) 09:00") }
            catch { self.error="Hatırlatıcı eklenemedi: \(error.localizedDescription)" }
        }
        if RemindersBridge.authorized { go() }
        else { RemindersBridge.requestAccess { [weak self] ok in if ok { go() } else { self?.error="Hatırlatıcılar erişimi verilmedi · Sistem Ayarları → Gizlilik ve Güvenlik → Hatırlatıcılar" } } }
    }

    /// Name a diarized cluster straight from Kontrol (calendar attendee chip). Enrolls like a confirmed suggestion.
    func nameSpeaker(_ speakerKey:String,_ name:String) async {
        guard let mid=selected, !speakerKey.isEmpty, !name.isEmpty else { return }
        do { let r=try await request(["action":"label_speaker","meeting":mid,"speaker":speakerKey,"name":name,"enroll":true]); activity="“\(name)” adlandırıldı · profil güncellendi"+adaptationNote(r); canUndoNaming=true; await refresh(); await loadReview(); refreshSummaryIfNamesDone() }
        catch { self.error=error.localizedDescription }
    }

    func compactStorage() async {
        do { let r=try await request(["action":"storage_compact"]); let ab=r["archived_bytes"] as? Int ?? 0; activity="Sesler sıkıştırıldı · parçalardan \(StorageReport.format(bytes:r["bytes"] as? Int ?? 0)), FLAC’ten \(StorageReport.format(bytes:ab)) boşaldı (\(r["archived_meetings"] as? Int ?? 0) toplantı)"; storage=(try? await request(["action":"storage_report"])).map(StorageReport.parse) }
        catch { self.error=error.localizedDescription }
    }

    func exportDiagnostics() async {
        let panel=NSSavePanel();panel.nameFieldStringValue="MeetingOS-tanilama-\(UUID().uuidString.prefix(8)).json"
        guard panel.runModal() == .OK, let url=panel.url else { return }
        var payload:[String:Any]=["action":"diagnostics","path":url.path]
        if let progress=progressURL { payload["progress"]=progress.path }
        do { _=try await request(payload);activity="Tanılama raporu kaydedildi · Toplantı içeriği dahil değil" }
        catch { self.error=error.localizedDescription }
    }

    /// Dry run first; nothing is removed until the confirmation button calls with dryRun=false.
    func previewCleanup() async {
        do { let r=try await request(["action":"storage_cleanup","days":cleanupDays,"dry_run":true]); let list=r["meetings"] as? [[String:Any]] ?? []
            cleanupPreview=CleanupPreview(days:cleanupDays,count:list.count,bytes:r["bytes"] as? Int ?? 0,titles:list.prefix(6).compactMap { $0["title"] as? String }) }
        catch { self.error=error.localizedDescription }
    }

    func runCleanup() async {
        do { let r=try await request(["action":"storage_cleanup","days":cleanupDays,"dry_run":false]); activity="Eski sesler temizlendi · \((r["meetings"] as? [[String:Any]])?.count ?? 0) toplantı, \(StorageReport.format(bytes:r["bytes"] as? Int ?? 0)) boşaldı · transkriptler duruyor"; cleanupPreview=nil; storage=(try? await request(["action":"storage_report"])).map(StorageReport.parse) }
        catch { self.error=error.localizedDescription }
    }
}

/// One learned word: what the user (or the app, after repeated edits) decided the right spelling is.
struct WordRule:Identifiable, Equatable {
    let original:String; let replacement:String; let source:String; let count:Int; let meetings:Int; let created:String; let vocabularyAdded:Bool
    var id:String { original }
    init(_ d:[String:Any]) {
        original=d["original"] as? String ?? ""; replacement=d["replacement"] as? String ?? ""
        source=d["source"] as? String ?? ""; count=d["count"] as? Int ?? 0; meetings=d["meetings"] as? Int ?? 0
        created=d["created"] as? String ?? ""; vocabularyAdded=d["vocabulary_added"] as? Bool ?? false
    }
    /// "taught" is a word the user corrected by hand; "learned" is one the app inferred from repeats.
    var sourceLabel:String { source=="taught" ? "öğretildi" : "öğrenildi" }
    var line:String { "“\(original)” → “\(replacement)” · \(sourceLabel) · \(meetings) toplantı" }
}
