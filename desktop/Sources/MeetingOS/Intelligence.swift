import SwiftUI
import AppKit

struct Evidence:Identifiable {
    let segment:Int; let quote:String; let start:Double; let speaker:String; let meeting:String; let meetingTitle:String
    var id:String { "\(meeting):\(segment):\(quote)" }
    func destination(in rows:[Row])->Row? { rows.first { $0.id==segment } }
    init(_ d:[String:Any]) { segment=d["segment_id"] as? Int ?? d["id"] as? Int ?? 0; quote=d["quote"] as? String ?? d["text"] as? String ?? ""; start=d["start"] as? Double ?? 0; speaker=d["speaker"] as? String ?? d["speaker_name"] as? String ?? ""; meeting=d["meeting"] as? String ?? ""; meetingTitle=d["meeting_title"] as? String ?? "" }
}
struct Insight:Identifiable {
    let text:String; let evidence:[Evidence]; let review:Bool; let superseded:Bool
    var id:String { text }
    init(_ d:[String:Any]) { text=d["text"] as? String ?? ""; evidence=(d["evidence"] as? [[String:Any]] ?? []).map(Evidence.init); review=d["needs_review"] as? Bool ?? false; superseded=d["superseded"] as? Bool ?? false }
}
struct ActionItem:Identifiable {
    let id:String; let title:String; let owner:String; let due:String; let state:String; let meeting:String; let meetingTitle:String; let stale:Bool; let route:String; let evidence:[Evidence]; let dueDate:String
    init(_ d:[String:Any]) { id=d["id"] as? String ?? ""; title=d["title"] as? String ?? ""; owner=d["owner"] as? String ?? ""; due=d["due_text"] as? String ?? ""; state=d["state"] as? String ?? "open"; meeting=d["meeting"] as? String ?? ""; meetingTitle=d["meeting_title"] as? String ?? ""; stale=d["stale"] as? Bool ?? false; route=d["route"] as? String ?? ""; dueDate=(d["payload"] as? [String:Any])?["due_date"] as? String ?? ""; evidence=((d["payload"] as? [String:Any])?["evidence"] as? [[String:Any]] ?? []).map { Evidence($0.merging(["meeting":d["meeting"] as? String ?? "", "meeting_title":d["meeting_title"] as? String ?? ""]) { _,new in new }) } }
}
struct DraftItem:Identifiable { let id:String; let task:String; let text:String; let stale:Bool
    init(_ d:[String:Any]) { id=d["id"] as? String ?? ""; task=d["task"] as? String ?? ""; text=d["text"] as? String ?? ""; stale=d["stale"] as? Bool ?? false }
}

extension Model {
    func refreshIntelligence(_ mid:String) async throws {
        let result=try await request(["action":"intelligence","meeting":mid])
        guard mid==(selected ?? "") else { return }
        analysis=result["analysis"] as? [String:Any]
        // A task retired by a newer analysis of the same meeting (state "superseded") is history, not a to-do.
        actions=(result["tasks"] as? [[String:Any]] ?? []).map(ActionItem.init).filter { $0.state != "superseded" }
        drafts=(result["drafts"] as? [[String:Any]] ?? []).map(DraftItem.init)
        let suggestions=result["due_suggestions"] as? [[String:Any]] ?? []
        dueSuggestions=Dictionary(uniqueKeysWithValues:suggestions.compactMap { d in (d["task"] as? String).flatMap { t in (d["suggested"] as? String).map { (t,$0) } } })
        pastDueSuggestions=Set(suggestions.filter { $0["past"] as? Bool == true }.compactMap { $0["task"] as? String })
    }
    /// Approve (or clear) a calendar date for a task; the transcript's own wording stays as due_text.
    func setDue(_ item:ActionItem,_ iso:String?) async {
        do { _=try await request(["action":"task_set_due","task":item.id,"due_date":iso as Any]); activity=iso==nil ? "Tarih kaldırıldı" : "Vade onaylandı · \(MeetingDates.dayLabel(iso!))"; try await refreshIntelligence(selected ?? "") } catch { self.error=error.localizedDescription }
    }
    func analyzeAutomatically(_ mid:String) {
        if transcriptionMode=="openrouter" { analyzeMeeting(mid); return }   // cloud analysis loads no local model; safe on 16 GB
        if ProcessInfo.processInfo.physicalMemory <= 16*1024*1024*1024 {
            activity="Transkript hazır · Özet sekmesinden özet ve görevleri hazırlayabilirsiniz."
        } else { analyzeMeeting(mid) }
    }
    func analyzeMeeting(_ mid:String?=nil) {
        guard let mid=mid ?? selected else { return }
        summaryRefreshTask?.cancel(); summaryRefreshTask=nil; pendingSummaryRefresh=false   // this run is the refresh a pending window was waiting for
        let started=launch(["analyze",mid]+cloudAnalysisArguments) { [weak self] ok in guard let self else { return }; if ok { self.summaryStale=false }; self.activity=ok ? "Toplantı hazır" : "Özet çıkarılamadı · Transkript duruyor"; if ok, !NSApp.isActive { let waiting=self.review.filter { $0.kind=="unnamed_speaker" || $0.kind=="suggested_name" }.count; self.notifyDone("Toplantı hazır",waiting>0 ? "\(waiting) isim bekliyor · aç ve onayla." : "Özet, kararlar ve görevler kaynaklarıyla hazır.") } }
        if let line=LaunchOutcome.activity(started:started,onStart:"Özet hazırlanıyor…") { activity=line }   // a job already runs: the previous line still describes it
    }
    func resultMeeting(_ url:URL) -> String? {
        guard let data=try? Data(contentsOf:url), let result=try? JSONSerialization.jsonObject(with:data) as? [String:Any] else { return nil }
        return result["meeting"] as? String
    }
    func updateAction(_ item:ActionItem,changes:[String:Any],reason:TaskEditReason = .unsaid) async {
        var body:[String:Any]=["action":"action_update","task":item.id,"changes":changes]
        if let reason=reason.payload { body["reason"]=reason }   // absent, not empty: "unknown" is a real answer
        do { _=try await request(body); try await refreshIntelligence(selected ?? "") } catch { self.error=error.localizedDescription }
    }
    func prepareAction(_ item:ActionItem,force:Bool=false) {
        activity="Görev için yerel taslak hazırlanıyor…"
        launch(["prepare",item.id]+(force ? ["--force"]:[])+cloudAnalysisArguments) { [weak self] ok in self?.activity=ok ? "Taslak hazır · Henüz hiçbir yere gönderilmedi" : "Taslak hazırlanamadı" }
    }
    func exportHandoff(_ item:ActionItem) async {
        let panel=NSSavePanel();panel.nameFieldStringValue="Görev-\(item.id).md"
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { _=try await request(["action":"handoff","task":item.id,"path":url.path]); activity="Görev paketi kaydedildi · Gönderim yapılmadı" } catch { self.error=error.localizedDescription }
    }
    func memorySearch() async {
        do { let result=try await request(["action":"search_memory","query":memoryQuery]); hits=(result["hits"] as? [[String:Any]] ?? []).map(Evidence.init) } catch { self.error=error.localizedDescription }
    }
    func askMemory() {
        guard !memoryQuery.trimmingCharacters(in:.whitespaces).isEmpty else { return }
        let url=dataDir.appendingPathComponent("answer-\(UUID().uuidString).json")
        activity="Toplantı kayıtlarında yanıt aranıyor…";answer="";answerEvidence=[]
        jobQuestion=memoryQuery   // never on argv: the question names what this Mac's owner is looking for
        launch(["ask","--output",url.path]+cloudAnalysisArguments) { [weak self] ok in
            defer { try? FileManager.default.removeItem(at:url) }   // the receipt quotes the transcript verbatim; it lives only as long as this read
            guard let self=self else { return }
            if ok, let data=try? Data(contentsOf:url), let result=try? JSONSerialization.jsonObject(with:data) as? [String:Any] { self.answer=result["answer"] as? String ?? ""; self.answerEvidence=(result["evidence"] as? [[String:Any]] ?? []).map(Evidence.init); self.activity="Arşiv yanıtı hazır · Kaynaklarla birlikte kontrol edin" }
        }
    }
    func openEvidence(_ e:Evidence) {
        // The library cache may lag behind search results. Resolve against the
        // target snapshot; an empty/missing source is reported by the resolver.
        if !e.meeting.isEmpty { selected=e.meeting }
        tab="transcript"; search=""; error=""; pendingEvidence=e
        if !rows.isEmpty { resolvePendingEvidence() }
        else { Task { await refresh() } }
    }
    func resolvePendingEvidence() {
        guard let e=pendingEvidence else { return }
        guard e.meeting.isEmpty || e.meeting==selected else { pendingEvidence=nil; return }
        if e.destination(in:rows)==nil && ["processing","provisional"].contains(meeting?.status ?? "") { return }
        pendingEvidence=nil
        if let row=e.destination(in:rows) {
            reveal(segment:row.id)
            if !row.text.contains(e.quote) { error="Kaynak metin değişmiş. Güncel konuşma bölümü gösteriliyor." }
        } else {
            focusedSegment=nil
            error="Kaynak konuşma bulunamadı. Tüm transkript gösteriliyor; analiz güncel olmayabilir."
        }
    }
}

struct EvidenceView:View {
    @ObservedObject var m:Model; let evidence:[Evidence]
    var body:some View { ForEach(evidence) { e in Button { m.openEvidence(e) } label:{ HStack(alignment:.top,spacing:10) { Image(systemName:"quote.opening").foregroundStyle(MeetingStyle.accent);VStack(alignment:.leading,spacing:5) { HStack { Text(e.meetingTitle.isEmpty ? e.speaker:e.meetingTitle).fontWeight(.medium).lineLimit(1);Spacer();Text("\(Int(e.start)/60):\(String(format:"%02d",Int(e.start)%60))").monospacedDigit();Image(systemName:"arrow.up.right").font(.system(size:9)) };Text(Fillers.clean(e.quote)).lineLimit(3).multilineTextAlignment(.leading).lineSpacing(3) } }.font(.caption).foregroundStyle(.secondary).padding(11).frame(maxWidth:.infinity,alignment:.leading).background(MeetingStyle.accent.opacity(0.065),in:RoundedRectangle(cornerRadius:9)).contentShape(Rectangle()) }.buttonStyle(.plain).help("Kaynak konuşmayı göster veya dinle").padding(.top,3) } }
}
struct AnalysisView:View {
    @ObservedObject var m:Model
    /// Which items show their evidence. It lives here, not on the Model: nothing else needs to know,
    /// and a meeting change wipes it (`.task(id:)` below).
    @State private var expanded:Set<String>=[]
    @AppStorage("summaryTalkShareOpen") private var showTalkShare=true   // who spoke how much is worth seeing at a glance; folding it is the user's choice and is remembered
    /// Boran, 11 Sep 2026: "özetler çok çok özet, bir şeyleri kaçırıyor" — the per-chunk bullets a long meeting was
    /// condensed from are kept in `section_summaries`; this switch shows them instead of the condensed list.
    @AppStorage("summaryDetailed") private var detailed=false
    func summaryItems(_ payload:[String:Any])->[[String:Any]] {
        let short=payload["summary"] as? [[String:Any]] ?? []
        let long=payload["section_summaries"] as? [[String:Any]] ?? []
        return detailed && long.count>short.count ? long:short
    }
    let categories=[("summary","Özet"),("decisions","Kararlar"),("risks","Riskler"),("questions","Açık sorular")]
    var stale:Bool { m.analysis?["stale"] as? Bool == true }
    var body:some View { ScrollView { VStack(alignment:.leading,spacing:16) {
        HStack(alignment:.firstTextBaseline) {
            Text("Özet").font(.system(size:23,weight:.bold,design:.rounded))
            Spacer()
            if m.analysis != nil {
                Menu("Dışa aktar") {
                    Button("Panoya kopyala (Markdown)") { Task { await m.copySummary() } }
                    Button("Dosyaya kaydet…") { Task { await m.saveSummary() } }
                    Divider()
                    Button("Paylaşım önizlemesi… (maskeleme, yalnız kararlar)") { m.showShare=true }
                }.fixedSize().accessibilityIdentifier("summaryExportMenu")
            }
            Button(m.analysis == nil ? "Özet ve görevleri hazırla":"Özeti güncelle") { m.analyzeMeeting() }.disabled(m.busy || m.meeting?.status != "complete").accessibilityIdentifier("analyzeButton")
        }
        Text(SummaryUX.statsLine(segments:m.rows.count,openTasks:m.openTaskCount,hasSummary:m.analysis != nil,stale:stale)).font(.callout).foregroundStyle(.secondary).accessibilityIdentifier("summaryStats")
        if stale { Label("Metin veya isimler değişti; bu özet güncel değil.",systemImage:"exclamationmark.triangle").font(.callout).foregroundStyle(.orange) }
        if m.summaryStale, m.meeting?.status=="complete" {
            HStack(spacing:8) {
                Image(systemName:"person.crop.circle.badge.exclamationmark").foregroundStyle(.orange)
                Text("İsim değişti · yeni isimlerle özet ≈1–3 cent.").font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                Button("Özeti yenile") { m.analyzeMeeting() }.controlSize(.small).disabled(m.busy).accessibilityIdentifier("refreshStaleSummary")
                Spacer(minLength:0)
            }.padding(.vertical,9).padding(.horizontal,12).meetingCard().accessibilityIdentifier("summaryStaleCard")
        }
        if m.shares.count>=2 {
            DisclosureGroup(isExpanded:$showTalkShare) { TalkShareBars(shares:m.shares).padding(.top,8) }
            label:{ HStack(spacing:8) { Text("Konuşma payı").font(.subheadline.weight(.medium));Text("\(m.shares.count) konuşmacı").font(.caption).foregroundStyle(.secondary) }.contentShape(Rectangle()) }
                .accessibilityIdentifier("talkShareDisclosure")
        }
        if let payload=m.analysis?["payload"] as? [String:Any] {
            let long=(payload["section_summaries"] as? [[String:Any]] ?? []).count, short=(payload["summary"] as? [[String:Any]] ?? []).count
            if long>short {
                Toggle(isOn:$detailed) { Text(detailed ? "Ayrıntılı özet (\(long) madde) · kısa özet için kapatın":"Ayrıntılı özet (\(long) madde)").font(.callout) }
                    .toggleStyle(.switch).controlSize(.small).accessibilityIdentifier("summaryDetailedToggle")
            }
            ForEach(categories,id:\.0) { key,label in
                SummarySection(m:m,section:key,label:label,items:(key=="summary" ? summaryItems(payload):(payload[key] as? [[String:Any]] ?? [])).map(Insight.init),expanded:$expanded).padding(.top,6)
            }
            Text("Görevleri Görevlerim ekranında düzenleyebilir, durumu değiştirebilir ve taslak hazırlatabilirsiniz.").font(.callout).foregroundStyle(.secondary).padding(.top,6)
        } else {
            CenteredNotice(icon:"text.bubble",title:"Henüz özet yok",detail:m.transcriptionMode=="openrouter" ? "Transkript hazır olunca özet, kararlar ve görevler OpenRouter’daki \(m.analysisModel) modeliyle çıkarılır; bu Mac’te model yüklenmez." : "Nihai transkript tamamlandıktan sonra özet, kararlar ve görevler yerel olarak çıkarılır.")
                .inlineNoticeArea()
        }
    }.padding(24).readingColumn()
        .task(id:m.selected) { expanded=[];await m.loadContinuity() } } }
}
