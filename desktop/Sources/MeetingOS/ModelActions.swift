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
    /// Record one failure in the local error journal. Called by the `error` setter for everything the user is
    /// shown, and directly (with a kind) by the places that know better — a job's exit code, a crash sweep.
    /// Deliberately fire-and-forget and deliberately silent: a journal write that fails must not set the very
    /// banner that would try to journal it again.
    func report(_ message:String,kind:String="ui",context:[String:Any]=[:]) {
        let text=String(message.prefix(300)).trimmingCharacters(in:.whitespacesAndNewlines)
        guard !text.isEmpty, errorThrottle.admit(text) else { return }
        var fields=context; fields["app_version"]=UpdateInfo.appVersion
        Task { _=try? await request(["action":"error_report","kind":kind,"message":text,"context":fields]) }
    }
    /// Read the journal back for Ayarlar → Sistem → Hatalar. The bridge sweeps crash reports and the updater's
    /// last verdict on the way, so launch and the hourly beat need no separate call.
    func loadErrors() async {
        guard let r=try? await request(["action":"errors_list","limit":5]) else { return }
        errorEntries=(r["errors"] as? [[String:Any]] ?? []).enumerated().map { ErrorEntry($0.element,index:$0.offset) }
        let summary=r["summary"] as? [String:Any] ?? [:]
        errorCounts=(summary["last_24h"] as? [String:Int]) ?? [:]
        errorCrashes=summary["crashes_24h"] as? Int ?? 0
    }
    func clearErrors() async {
        _=try? await request(["action":"errors_clear"])
        await loadErrors(); activity="Hata günlüğü temizlendi"
    }
    func heartbeatIfDue() {
        guard !recording, recordProcess==nil, job==nil, lastHeartbeat.map({ Date().timeIntervalSince($0) >= 3600 }) ?? true else { return }
        lastHeartbeat=Date()
        Task {
            // P0-3: the bundle's own CFBundleShortVersionString under `app.version` is what the Python side prefers;
            // no `commit` is sent, so the bridge falls back to the checkout's git hash for that.
            await loadErrors()   // crash reports and update failures are swept before the heartbeat reports them
            _=try? await request(["action":"heartbeat","app":["version":UpdateInfo.appVersion,"bridge":BridgeStats.shared.snapshot]])
            // Not on the poll's bridge: the archive pass is seconds per meeting and the ten-second watchdog was
            // SIGTERMing it every hour, so a library that had fallen behind could never catch up.
            if !recording, recordProcess==nil, job==nil, let r=try? await requestSlow(["action":"storage_housekeeping"]) {
                let archived=r["archived_bytes"] as? Int ?? 0, removed=r["removed_bytes"] as? Int ?? 0
                // One retention setting deletes a whole week of recordings on the same day; the warning comes first,
                // while marking a meeting "Sesi koru" (or widening the setting) can still save it.
                // Said once per countdown step (3 → 2 → 1 → 0 days), not every hour: the status line belongs to what the user just did.
                // The text horizon goes first when both are counting down: losing the audio is losing a recording,
                // losing the text is losing the meeting, and only one of the two can be said in one line.
                if let w=r["text_retention_warning"] as? [String:Any], let line=w["line"] as? String {
                    let key="textRetentionWarned:\(w["days_left"] as? Int ?? -1):\(w["meetings"] as? Int ?? 0)"
                    if !UserDefaults.standard.bool(forKey:key) { UserDefaults.standard.set(true,forKey:key); activity=line }
                }
                else if let w=r["retention_warning"] as? [String:Any], let line=w["line"] as? String {
                    let key="retentionWarned:\(w["days_left"] as? Int ?? -1):\(w["meetings"] as? Int ?? 0)"
                    if !UserDefaults.standard.bool(forKey:key) { UserDefaults.standard.set(true,forKey:key); activity=line }
                }
                else if let gone=r["removed_text_meetings"] as? Int, gone>0 { activity="Depolama · metin saklama süresi doldu, \(gone) toplantı tümüyle silindi" }
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
    // MARK: - Transkriptte kelimeye tıklayarak düzelt
    /// "Yalnız burada": the word was right everywhere else, so nothing is learned — only this segment's text
    /// is rewritten, through the same `edit_text` the segment editor uses.
    func fixWordHere(_ fix:WordFix,replacement:String) async {
        let to=replacement.trimmingCharacters(in:.whitespacesAndNewlines)
        guard let mid=selected, !busy, !to.isEmpty, to != fix.original, let row=rows.first(where:{ $0.id==fix.segmentID }) else { wordFix=nil; return }
        let live=WordClick.tokens(row.text); guard fix.index<live.count, live[fix.index].core==fix.original else { activity="Bu bölüm değişti; kelimeye yeniden tıklayın"; wordFix=nil; return }
        let text=WordClick.replacing(row.text,index:fix.index,with:to)
        wordFix=nil
        guard text != row.text else { return }
        do { _=try await request(["action":"edit_text","meeting":mid,"segment":fix.segmentID,"text":text])
            activity="“\(fix.original)” → “\(to)” · yalnız bu bölümde"
            await refresh() }
        catch { self.error=error.localizedDescription }
    }
    /// "Düzelt ve öğret": the same teaching the segment editor does, started from the word itself.
    func learnClickedWord(_ fix:WordFix,replacement:String) async {
        guard !busy else { return }
        wordFix=nil
        await learnWord(original:fix.original,replacement:replacement)
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
        teamSummary=(r["team"] as? [String:Any])?["line"] as? String ?? ""
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
    /// A teammate's word, off (or back on) on this Mac only. Their shared file is not touched: the user is
    /// saying "not here", not "unteach it for everyone" — so there is a way back, unlike Unut.
    func toggleTeamWord(_ rule:WordRule,enabled:Bool) async {
        guard !rule.original.isEmpty, !rule.host.isEmpty else { return }
        do { _=try await request(["action":"team_word_toggle","original":rule.original,"host":rule.host,"enabled":enabled])
            activity=enabled ? "“\(rule.original)” yeniden açıldı · \(rule.host)" : "“\(rule.original)” bu Mac’te kapatıldı · \(rule.host) paylaşmaya devam ediyor"
            await loadWordRules() }
        catch { self.error=error.localizedDescription }
    }
    /// Once per launch: publish what this Mac learned into the team folder and read back what the others learned
    /// while it was closed. Quiet — nothing on screen unless it actually brought something in.
    func syncTeamKnowledge() async {
        guard let r=try? await requestSlow(["action":"team_sync"]) else { return }
        let words=(r["words"] as? [String:Any])?["imported"] as? Int ?? 0
        let people=(r["profiles"] as? [String:Any])?["imported"] as? Int ?? 0
        if words+people>0 { activity="Ekip klasöründen alındı · \(words) kelime, \(people) ses örneği"; await loadWordRules(); await loadMaintenance() }
    }
    func rejectRule(_ original:String) async {
        guard !original.isEmpty else { return }
        do { _=try await request(["action":"reject_rule","original":original]); activity="Kural kapatıldı · “\(original)” artık kendiliğinden düzeltilmez"; await loadMaintenance() } catch { self.error=error.localizedDescription }
    }
    /// `quick`: no git fetch inside the bridge (Settings opens; the hourly update check already ran and its
    /// answer is merged in below), so the card never waits on the network.
    func loadSetupStatus(quick:Bool=false) async {
        var checks=SetupStatus.permissionChecks(calendarWanted:useCalendar)
        let settings=await UNUserNotificationCenter.current().notificationSettings()
        checks.append(SetupStatus.notificationCheck(settings))
        var answer:[String:Any]?
        if var r=try? await request(quick ? ["action":"setup_status","quick":true] : ["action":"setup_status"]) {
            if quick, let u=update {
                r["update_behind"]=u.behind; r["update_diverged"]=u.diverged; r["update_ahead"]=u.ahead
                r["update_hint"]=u.hint; r["update_error"]=u.error
            }
            answer=r
            checks+=SetupStatus.serviceChecks(r,repo:runtime.repo,divergedNotice:update?.divergedNotice ?? "",bundled:runtime.bundled,bundleVersion:runtime.version ?? "")
            // The same answer, read once more as the one line Ayarlar → Ekip opens with — and as the flag that
            // decides whether the three share switches mean anything at all.
            teamTarget=TeamInvite.target(r,home:NSHomeDirectory())
            teamConfigured=teamTarget.kind == .cloud
        }
        setupChecks=checks
        if let answer { await importBundleInviteIfNeeded(answer) }
    }
    /// First launch of a downloaded package, on a Mac with neither a key nor a team: the invite that was built
    /// into it is applied once, silently, so the teammate meets the name field and the permission buttons and
    /// nothing else. The flag is written BEFORE the join so a join that comes back with an error cannot loop
    /// through `joinTeam` → `loadSetupStatus` → here forever.
    func importBundleInviteIfNeeded(_ r:[String:Any]) async {
        let hasKey=(r["api_key"] as? Bool ?? false) || (r["api_key_keychain"] as? Bool ?? false)
        let hasTeam=TeamInvite.target(r).sharing
        guard BundleInvite.shouldImportInvite(bundled:runtime.bundled,hasKey:hasKey,hasTeam:hasTeam,
                                              alreadyImported:UserDefaults.standard.bool(forKey:BundleInvite.importedKey)) else { return }
        guard let text=BundleInvite.text(resources:Bundle.main.resourceURL) else { bundleInviteFailed=true; return }
        UserDefaults.standard.set(true,forKey:BundleInvite.importedKey)
        await joinTeam(text)   // the same path a pasted link takes: it refreshes the setup card itself
        if teamJoin?.ok != true { bundleInviteFailed=true }
    }

    // MARK: - Ekip daveti
    /// Whether this Mac is in a team at all. One tiny bridge call with no database behind it, so the welcome
    /// screen can ask it on a Mac that has never recorded anything.
    func loadTeamStatus() async {
        guard let r=try? await request(["action":"team_status"]) else { return }
        teamConfigured=r["configured"] as? Bool ?? false
    }
    /// The invite, on the pasteboard. With `includeKey` the teammate never meets the OpenRouter key step —
    /// which also means the link now carries a password that pays Boran's bill, so the confirmation says so.
    /// Boran, 11 Sep 2026: "özet ve kararları dışa aktaramıyorum" — the Özet tab gets its own two-click export:
    /// the same Markdown the share preview builds (summary, decisions, risks, questions, tasks with their quotes),
    /// no transcript, no masking, straight to the clipboard or a file.
    func summaryMarkdown()->[String:Any] { guard let mid=selected else { return [:] }; return ["action":"share_preview","meeting":mid,"kinds":["summary"],"mask_names":false,"only_decisions":false] }
    func copySummary() async {
        let req=summaryMarkdown(); guard !req.isEmpty else { return }
        do {
            let r=try await request(req); let text=r["text"] as? String ?? ""
            guard !text.isEmpty else { self.error="Kopyalanacak özet yok"; return }
            NSPasteboard.general.clearContents(); NSPasteboard.general.setString(text,forType:.string)
            activity="Özet panoya kopyalandı (Markdown) · \(text.count) karakter"
        } catch { self.error=error.localizedDescription }
    }
    func saveSummary() async {
        guard let mid=selected else { return }
        let panel=NSSavePanel(); let base=(meeting?.title ?? "Toplantı").replacingOccurrences(of:"/",with:"-").replacingOccurrences(of:":",with:"-")
        panel.nameFieldStringValue="\(base) · özet.md"; panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do {
            _=try await request(["action":"share_export","meeting":mid,"path":url.path,"kinds":["summary"],"mask_names":false,"only_decisions":false])
            activity="Özet kaydedildi · \(url.lastPathComponent)"
        } catch { self.error=error.localizedDescription }
    }
    func copyInviteLink(includeKey:Bool,personalKey:String="") async {
        do {
            let r=try await request(["action":"team_invite","include_key":includeKey,"key":personalKey.trimmingCharacters(in:.whitespacesAndNewlines)])
            if let message=r["error"] as? String { self.error=message; return }
            let link=r["url"] as? String ?? ""
            guard !link.isEmpty else { self.error="Davet bağlantısı oluşturulamadı"; return }
            NSPasteboard.general.clearContents(); NSPasteboard.general.setString(link,forType:.string)
            activity=(r["with_key"] as? Bool)==true
                ? "Davet bağlantısı kopyalandı · OpenRouter anahtarınız da içinde: yalnız güvendiğiniz kişiye gönderin"
                : "Davet bağlantısı kopyalandı · ekip \(r["team_id_short"] as? String ?? "")"
        } catch { self.error=error.localizedDescription }
    }
    /// The same invite as a file, for the chat apps that swallow a custom scheme. Written where the user says.
    func saveInviteFile(includeKey:Bool,personalKey:String="") async {
        do {
            let r=try await request(["action":"team_invite","include_key":includeKey,"key":personalKey.trimmingCharacters(in:.whitespacesAndNewlines)])
            if let message=r["error"] as? String { self.error=message; return }
            let text=r["text"] as? String ?? ""
            guard !text.isEmpty else { self.error="Davet dosyası oluşturulamadı"; return }
            let panel=NSSavePanel(); panel.nameFieldStringValue=TeamInvite.fileName
            if let type=UTType(TeamInvite.uti) ?? UTType(filenameExtension:TeamInvite.fileExtension) { panel.allowedContentTypes=[type] }
            guard panel.runModal() == .OK, let url=panel.url else { return }
            try text.write(to:url,atomically:true,encoding:.utf8)
            activity="Davet dosyası kaydedildi · "+url.lastPathComponent
        } catch { self.error=error.localizedDescription }
    }
    /// The whole join: a link, the text of an invite file, or a bare token — the bridge decides which. The
    /// answer becomes the confirmation sheet, and the setup card is refreshed so the team row stops lying.
    func joinTeam(_ invite:String) async {
        guard let payload=TeamInvite.payload(invite) else { return }
        do {
            let r=try await request(["action":"team_join","invite":payload])
            teamJoin=TeamInvite.outcome(r)
            await loadSetupStatus()
            if teamJoin?.ok==true { await syncTeamKnowledge() }   // the mirror is filled; this is what puts it in the database
        } catch { teamJoin=TeamJoinOutcome(ok:false,line:error.localizedDescription) }
    }
    /// A `meetingos://join?…` click or a `.meetingos-invite` double click, from the AppKit delegate.
    func handleIncoming(urls:[URL]) {
        for url in urls {
            if TeamInvite.isJoinURL(url) {
                showMainWindow(); Task { await joinTeam(url.absoluteString) }; return
            }
            if TeamInvite.isInviteFile(url), let text=try? String(contentsOf:url,encoding:.utf8) {
                showMainWindow(); Task { await joinTeam(text) }; return
            }
        }
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
        do { _=try await request(payload);activity="Tanılama raporu kaydedildi · Hata günlüğü dahil, toplantı içeriği değil" }
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
    /// Team rows only: the Mac that taught the word, whether this Mac applies it, and whether the user
    /// switched it off here. Two Macs can teach the same word, so the host is part of the identity.
    let host:String; let enabled:Bool; let active:Bool
    var id:String { source+":"+host+":"+original }
    init(_ d:[String:Any]) {
        original=d["original"] as? String ?? ""; replacement=d["replacement"] as? String ?? ""
        source=d["source"] as? String ?? ""; count=d["count"] as? Int ?? 0; meetings=d["meetings"] as? Int ?? 0
        created=d["created"] as? String ?? ""; vocabularyAdded=d["vocabulary_added"] as? Bool ?? false
        host=d["host"] as? String ?? ""; enabled=d["enabled"] as? Bool ?? true; active=d["active"] as? Bool ?? true
    }
    var isTeam:Bool { source=="team" }
    /// "taught" is a word the user corrected by hand; "learned" is one the app inferred from repeats;
    /// "team" is one a teammate taught on their Mac and shared through the team folder.
    var sourceLabel:String { source=="taught" ? "öğretildi" : (isTeam ? "ekipten" : "öğrenildi") }
    var line:String { isTeam ? "“\(original)” → “\(replacement)” · ekipten" : "“\(original)” → “\(replacement)” · \(sourceLabel) · \(meetings) toplantı" }
    /// Why a team row is listed but not applied: switched off here, or beaten by this Mac's own word.
    var teamNote:String { !isTeam ? "" : (!enabled ? "bu Mac’te kapalı" : (active ? "" : "bu Mac’in kendi yazımı öncelikli")) }
}

/// One place in the app a jump can send the user back to: which meeting was open, which tab, what the
/// transcript was filtered down to. Cheap to copy and compared by value, so a jump that changes nothing
/// leaves nothing behind.
struct NavPoint:Equatable {
    var meeting:String?
    var tab:String
    var focusedSegment:Int?
    var search:String
}

/// Back-stack arithmetic, kept pure so the interesting part (what is pushed, what is dropped) is testable
/// without a Model, a window or a run loop.
enum NavHistory {
    /// A back button is a way out of the last few jumps, not a session history.
    static let cap=20
    /// How long a meeting switch waits for the jump that belongs to it: the week view opens a meeting and
    /// reveals its paragraph ~1.2 s later, and both are one navigation to the user.
    static let candidateWindow:TimeInterval=3

    static func pushed(_ stack:[NavPoint],_ point:NavPoint)->[NavPoint] {
        if stack.last==point { return stack }   // one entry per place, however the jump was spelled
        var next=stack
        next.append(point)
        if next.count>cap { next.removeFirst(next.count-cap) }
        return next
    }

    static func popped(_ stack:[NavPoint])->(point:NavPoint?,rest:[NavPoint]) {
        var rest=stack
        let point=rest.popLast()
        return (point,rest)
    }
}

/// Only visible when a jump left somewhere to go back to: an always-present arrow that does nothing most
/// of the time would be worse than no arrow at all.
struct BackButton:View {
    @ObservedObject var model:Model
    var body:some View {
        if !model.backStack.isEmpty {
            Button { model.goBack() } label: { Label("Geri",systemImage:"chevron.left").font(.callout) }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .help("Geri (⌘[)")
                .accessibilityIdentifier("backButton")
                .accessibilityLabel("Geri")
        }
    }
}
