import SwiftUI
import AppKit

struct Evidence:Identifiable {
    let segment:Int; let quote:String; let start:Double; let speaker:String; let meeting:String; let meetingTitle:String
    var id:String { "\(meeting):\(segment):\(quote)" }
    func destination(in rows:[Row])->Row? { rows.first { $0.id==segment } }
    init(_ d:[String:Any]) { segment=d["segment_id"] as? Int ?? d["id"] as? Int ?? 0; quote=d["quote"] as? String ?? d["text"] as? String ?? ""; start=d["start"] as? Double ?? 0; speaker=d["speaker"] as? String ?? d["speaker_name"] as? String ?? ""; meeting=d["meeting"] as? String ?? ""; meetingTitle=d["meeting_title"] as? String ?? "" }
}
struct Insight:Identifiable {
    let text:String; let evidence:[Evidence]; let review:Bool
    var id:String { text }
    init(_ d:[String:Any]) { text=d["text"] as? String ?? ""; evidence=(d["evidence"] as? [[String:Any]] ?? []).map(Evidence.init); review=d["needs_review"] as? Bool ?? false }
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
        actions=(result["tasks"] as? [[String:Any]] ?? []).map(ActionItem.init)
        drafts=(result["drafts"] as? [[String:Any]] ?? []).map(DraftItem.init)
        dueSuggestions=Dictionary(uniqueKeysWithValues:(result["due_suggestions"] as? [[String:Any]] ?? []).compactMap { d in (d["task"] as? String).flatMap { t in (d["suggested"] as? String).map { (t,$0) } } })
    }
    /// Approve (or clear) a calendar date for a task; the transcript's own wording stays as due_text.
    func setDue(_ item:ActionItem,_ iso:String?) async {
        do { _=try await request(["action":"task_set_due","task":item.id,"due_date":iso as Any]); activity=iso==nil ? "Tarih kaldırıldı" : "Vade onaylandı · \(MeetingDates.dayLabel(iso!))"; try await refreshIntelligence(selected ?? "") } catch { self.error=error.localizedDescription }
    }
    func analyzeAutomatically(_ mid:String) {
        if transcriptionMode=="openrouter" { analyzeMeeting(mid); return }   // cloud analysis loads no local model; safe on 16 GB
        if ProcessInfo.processInfo.physicalMemory <= 16*1024*1024*1024 {
            activity="Transkript hazır · Özet ve görevleri Analiz sekmesinden isteğe bağlı hazırlayabilirsiniz."
        } else { analyzeMeeting(mid) }
    }
    func analyzeMeeting(_ mid:String?=nil) {
        guard let mid=mid ?? selected else { return }
        activity=transcriptionMode=="openrouter" ? "Özet, kararlar ve görevler OpenRouter’da hazırlanıyor (\(analysisModel))…" : "Özet, kararlar ve görevler bu Mac’te hazırlanıyor…"
        launch(["analyze",mid]+cloudAnalysisArguments) { [weak self] ok in self?.activity=ok ? "Özet ve görevler hazır · Kaynakları gözden geçirin" : "Analiz tamamlanamadı · Transkript korunuyor"; if ok, !NSApp.isActive { self?.notifyDone("Özet ve görevler hazır","Kararlar, sorular ve görevler kaynaklarıyla birlikte çıkarıldı.") } }
    }
    func resultMeeting(_ url:URL) -> String? {
        guard let data=try? Data(contentsOf:url), let result=try? JSONSerialization.jsonObject(with:data) as? [String:Any] else { return nil }
        return result["meeting"] as? String
    }
    func updateAction(_ item:ActionItem,changes:[String:Any]) async {
        do { _=try await request(["action":"action_update","task":item.id,"changes":changes]); try await refreshIntelligence(selected ?? "") } catch { self.error=error.localizedDescription }
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
        launch(["ask",memoryQuery,"--output",url.path]+cloudAnalysisArguments) { [weak self] ok in
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
    let categories=[("summary","Özet"),("decisions","Kararlar"),("risks","Riskler"),("questions","Açık sorular")]
    var body:some View { ScrollView { VStack(alignment:.leading,spacing:20) {
        HStack { Text("Toplantının özü").font(.system(size:23,weight:.bold,design:.rounded));Spacer();Button(m.analysis == nil ? "Özet ve görevleri hazırla":"Analizi güncelle") { m.analyzeMeeting() }.disabled(m.busy || m.meeting?.status != "complete").accessibilityIdentifier("analyzeButton") }
        Text("Kararlar, açık noktalar ve sonraki adımlar. Her maddeyi kaynak konuşmayla birlikte gözden geçirin.").font(.callout).foregroundStyle(.secondary)
        LazyVGrid(columns:[GridItem(.adaptive(minimum:170),spacing:12)],spacing:12) { SmallMetric(value:"\(m.rows.count)",label:"Konuşma bölümü",icon:"waveform");SmallMetric(value:"\(m.actions.filter { $0.meeting==m.selected && !$0.stale && !["done","dismissed"].contains($0.state) }.count)",label:"Açık görev",icon:"checklist");SmallMetric(value:m.analysis == nil ? "Bekliyor":m.analysis?["stale"] as? Bool == true ? "Güncelle":"Hazır",label:"Toplantı özeti",icon:"text.badge.checkmark") }
        if m.analysis?["stale"] as? Bool == true { Label("Metin veya isimler değişti. Bu analiz güncel değil; yeniden hazırlayın.",systemImage:"exclamationmark.triangle").foregroundStyle(.orange) }
        let shares=TalkShare.compute(m.rows)
        if shares.count>=2 { TalkShareView(shares:shares) }
        if let payload=m.analysis?["payload"] as? [String:Any] {
            ForEach(categories,id:\.0) { key,label in VStack(alignment:.leading,spacing:10) { Text(label).font(.headline);let items=(payload[key] as? [[String:Any]] ?? []).map(Insight.init)
                if items.isEmpty { Text("Kayıtlarda açık bir madde bulunmadı.").foregroundStyle(.secondary) }
                ForEach(items) { item in VStack(alignment:.leading,spacing:5) { Text(item.text).font(.system(size:15,weight:.medium)).lineSpacing(5).textSelection(.enabled);if item.review { Label("Kaynak ses belirsiz; kontrol edin.",systemImage:"exclamationmark.triangle").font(.caption).foregroundStyle(.orange) };if key=="decisions", let prev=m.continuity.historyByDecision[item.text], !prev.isEmpty { VStack(alignment:.leading,spacing:3) { ForEach(prev) { p in Label("Önceki karar · \(p.meetingTitle): \(p.text)",systemImage:"clock.arrow.circlepath").font(.caption).foregroundStyle(.secondary) } } };EvidenceView(m:m,evidence:item.evidence) }.padding(18).frame(maxWidth:.infinity,alignment:.leading).meetingCard() }
            } }
            Text("Görevleri Görevlerim ekranında düzenleyebilir, durumu değiştirebilir ve taslak hazırlatabilirsiniz.").font(.callout)
        } else { ContentUnavailableView("Henüz analiz yok",systemImage:"text.bubble",description:Text(m.transcriptionMode=="openrouter" ? "Transkript hazır olunca özet, kararlar ve görevler OpenRouter’daki \(m.analysisModel) modeliyle çıkarılır; bu Mac’te model yüklenmez." : "Nihai transkript tamamlandıktan sonra özet, kararlar ve görevler yerel olarak çıkarılır.")) }
    }.padding(24).task(id:m.selected) { await m.loadContinuity() } } }
}
struct ActionsView:View {
    @ObservedObject var m:Model
    @State var draftEdit:DraftItem?;@State var draftText=""
    @State var filter="boran";@State var edit:ActionItem?;@State var title="";@State var owner="";@State var due=""
    func matches(_ item:ActionItem,_ f:String)->Bool { f=="all" || (f=="boran" ? item.owner.lowercased(with:Locale(identifier:"tr_TR"))=="boran" : item.meeting==m.selected) }
    var visible:[ActionItem] { m.actions.filter { matches($0,filter) } }
    /// Open tasks behind each segment, so an empty "Boran’ın görevleri" never hides the meeting's tasks.
    func count(_ f:String)->Int { m.actions.filter { matches($0,f) && !["done","dismissed"].contains($0.state) }.count }
    /// First look at a meeting: if nothing is assigned to Boran yet, show the meeting's own tasks instead of an empty list.
    func pickInitialFilter() { if filter=="boran" && count("boran")==0 && count("meeting")>0 { filter="meeting" } }
    func statePicker(_ item:ActionItem)->some View {
        Picker("Durum",selection:Binding(get:{item.state},set:{value in Task { await m.updateAction(item,changes:["state":value]) }})) { Text("Açık").tag("open");Text("Devam ediyor").tag("in_progress");Text("Tamamlandı").tag("done");Text("Kaldırıldı").tag("dismissed") }
            .frame(width:220).accessibilityIdentifier("actionState-\(item.id)")
    }
    func draftButton(_ item:ActionItem)->some View {
        Button(m.drafts.contains { $0.task==item.id && !$0.stale } ? "Taslağı yeniden hazırla":"Taslak hazırla") { m.prepareAction(item,force:m.drafts.contains { $0.task==item.id && !$0.stale }) }
            .disabled(m.busy || item.stale || ["done","dismissed"].contains(item.state))
            .accessibilityIdentifier("prepareDraft-\(item.id)")
    }
    /// Confirmed date, or the parser's proposal with one-tap approval. Never writes a date on its own.
    func dueChip(_ item:ActionItem)->some View {
        HStack(spacing:6) {
            if !item.dueDate.isEmpty {
                Label(MeetingDates.dayLabel(item.dueDate),systemImage:"calendar").font(.caption).foregroundStyle(MeetingDates.isPast(item.dueDate) && !["done","dismissed"].contains(item.state) ? .orange : .secondary)
                Button("Kaldır") { Task { await m.setDue(item,nil) } }.controlSize(.mini).buttonStyle(.plain).foregroundStyle(.secondary)
            } else if let s=m.dueSuggestions[item.id] {
                Label("Öneri: \(MeetingDates.dayLabel(s))",systemImage:"calendar.badge.clock").font(.caption).foregroundStyle(.secondary).help("“\(item.due)” ifadesi toplantı tarihine göre çevrildi; onaylamadan hiçbir yere yazılmaz")
                Button("Onayla") { Task { await m.setDue(item,s) } }.controlSize(.mini).accessibilityIdentifier("approveDue-\(item.id)")
            }
        }
    }
    func reminderButton(_ item:ActionItem)->some View {
        Button("Hatırlatıcılar’a ekle") { m.addReminder(item) }
            .disabled(["done","dismissed"].contains(item.state))
            .help("Görevi Apple Hatırlatıcılar’daki varsayılan listeye ekler; kaynak toplantı ve zaman notu ile")
            .accessibilityIdentifier("addReminder-\(item.id)")
    }
    func handoffButton(_ item:ActionItem)->some View {
        Button("\(item.route) için paket kaydet") { Task { await m.exportHandoff(item) } }
            .disabled(item.stale || ["done","dismissed"].contains(item.state))
            .accessibilityIdentifier("exportHandoff-\(item.id)")
    }
    var body:some View { VStack(alignment:.leading) {
        HStack { Text("Sonraki adımlar").font(.system(size:23,weight:.bold,design:.rounded));Spacer();Text("\(visible.filter { !["done","dismissed"].contains($0.state) }.count) açık · \(visible.count) toplam").font(.callout).foregroundStyle(.secondary) }.padding(.horizontal,24).padding(.top,20)
        HStack { Picker("Görevler",selection:$filter) { Text("Boran’ın görevleri (\(count("boran")))").tag("boran");Text("Bu toplantı (\(count("meeting")))").tag("meeting");Text("Tüm görevler (\(count("all")))").tag("all") }.pickerStyle(.segmented); Button("Sonraki toplantı gündemi…") { Task { await m.exportAgenda() } }.help("Son 5 toplantının açık görev, soru ve kararlarından düzenlenebilir bir gündem taslağı kaydeder; hiçbir yere gönderilmez").accessibilityIdentifier("agendaButton"); Button("Gün sonu özeti…") { Task { await m.exportDigest() } }.accessibilityIdentifier("digestButton"); Button("Brifing…") { Task { await m.exportBrief() } }.help("Sıradaki takvim toplantısının katılımcıları için: verdikleri sözler, açık sorular, kararlar; Markdown olarak kaydeder").accessibilityIdentifier("briefButton"); Button("Hafta özeti…") { Task { await m.exportWeeklyDigest() } }.help("Son 7 günün kararları, kapanan/açık görevleri, riskleri ve cevapsız soruları toplantı toplantı; paydaşa gönderilebilir Markdown").accessibilityIdentifier("weeklyDigestButton").help("Bugün kaydedilen toplantılardan sana düşen görevleri, senden beklenen cevapları ve alınan kararları kaynaklarıyla bir Markdown dosyasına kaydeder; hiçbir yere gönderilmez").accessibilityIdentifier("digestButton") }.padding().task(id:m.selected) { await m.loadContinuity(); pickInitialFilter() }.onChange(of:m.actions.count) { _,_ in pickInitialFilter() }.accessibilityIdentifier("actionsFilterPicker")
        ScrollView { LazyVStack(alignment:.leading,spacing:18) {
            if visible.isEmpty { ContentUnavailableView("Görev bulunamadı",systemImage:"checklist",description:Text("İsimsiz görevler Tüm görevler altında görünür. Sahipliği kaynakla doğrulayarak düzeltebilirsiniz.")) }
            ForEach(visible) { item in VStack(alignment:.leading,spacing:10) {
                HStack(alignment:.top) { Text(item.title).font(.headline).strikethrough(["done","dismissed"].contains(item.state)).textSelection(.enabled);Spacer();TaskStatusBadge(state:item.state) }
                Text("\(item.owner.isEmpty ? "Sahibi belirsiz" : item.owner) · \(item.due.isEmpty ? "Tarih belirtilmedi" : item.due) · \(item.meetingTitle)").font(.caption).foregroundStyle(.secondary)
                if item.stale { Label("Kaynak değişti · Görevi yeniden doğrulayın",systemImage:"exclamationmark.triangle").foregroundStyle(.orange) }
                if let rel=m.continuity.relatedByTask[item.id], let first=rel.first(where:{ $0.supersededBy.isEmpty && $0.state != "dismissed" }) {
                    HStack(spacing:8) {
                        Label("Önceki toplantıda benzer görev · \(first.meetingTitle): “\(first.title)” (\(first.state=="done" ? "tamamlandı" : "açık"))",systemImage:"arrow.triangle.branch").font(.caption).foregroundStyle(.secondary)
                        if first.state != "done" { Button("Aynı görev, eskisini kapat") { Task { await m.supersede(old:first.id,new:item.id) } }.controlSize(.small).help("Eski görev “kaldırıldı” olur ve bu göreve bağlanır; kaynaklar korunur") }
                    }
                }
                ViewThatFits(in:.horizontal) {
                    HStack { statePicker(item);Button("Düzenle") { edit=item;title=item.title;owner=item.owner;due=item.due }.accessibilityIdentifier("editAction-\(item.id)");Spacer() }
                    VStack(alignment:.leading,spacing:8) { statePicker(item);Button("Düzenle") { edit=item;title=item.title;owner=item.owner;due=item.due }.accessibilityIdentifier("editAction-\(item.id)") }
                }
                EvidenceView(m:m,evidence:item.evidence)
                ViewThatFits(in:.horizontal) {
                    HStack { draftButton(item);handoffButton(item);reminderButton(item);dueChip(item) }
                    VStack(alignment:.leading,spacing:8) { draftButton(item);handoffButton(item);reminderButton(item);dueChip(item) }
                }
                ForEach(m.drafts.filter {$0.task==item.id}.prefix(1)) { draft in DisclosureGroup(draft.stale ? "Güncel olmayan taslak":"İncelenecek taslak · gönderilmedi") { VStack(alignment:.leading) { Text(draft.text).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading).padding(.top,8);Button("Taslağı düzenle") { draftEdit=draft;draftText=draft.text }.disabled(draft.stale) } } }
            }.padding(20).meetingCard() }
        }.padding(24) }
    }.sheet(item:$draftEdit) { draft in VStack(alignment:.leading,spacing:16) { Text("Taslağı düzenle").font(.title2.bold());TextEditor(text:$draftText).frame(height:340);HStack { Button("Vazgeç") { draftEdit=nil };Spacer();Button("Kaydet") { Task { do { _=try await m.request(["action":"draft_update","draft":draft.id,"text":draftText]);try await m.refreshIntelligence(m.selected ?? "");draftEdit=nil } catch { m.error=error.localizedDescription } } } } }.padding(24).frame(width:650) }.sheet(item:$edit) { item in VStack(alignment:.leading,spacing:16) { Text("Görevi düzenle").font(.title2.bold());TextField("Görev",text:$title);TextField("Sahibi",text:$owner);TextField("Kaynakta geçen tarih",text:$due);Text("Otomatik çıkarım öneridir. Sahip ve tarihi kaynak konuşmayla doğrulayın.").font(.caption).foregroundStyle(.secondary);HStack { Button("Vazgeç") { edit=nil };Spacer();Button("Kaydet") { Task { await m.updateAction(item,changes:["title":title,"owner":owner,"due_text":due]);edit=nil } }.disabled(title.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty) } }.padding(24).frame(width:500) } }
}
struct MemoryView:View {
    @ObservedObject var m:Model
    @State private var mode="search"
    @FocusState private var queryFocused:Bool
    var memoryQueryField:some View {
        TextField("Örn. onboarding PRD",text:$m.memoryQuery).onSubmit { Task { await m.memorySearch() } }
            .focused($queryFocused).onChange(of:m.memoryFocusToken) { _,_ in queryFocused=true }
            .accessibilityIdentifier("memoryQueryField").accessibilityLabel("Hafızada ara")
    }
    var body:some View { VStack(alignment:.leading,spacing:16) {
        HStack { Label("Toplantı hafızası",systemImage:"sparkle.magnifyingglass").font(.system(size:23,weight:.bold,design:.rounded)); Spacer(); Picker("Görünüm",selection:$mode) { Text("Ara").tag("search"); Text("Kararlar").tag("decisions"); Text("Sorular").tag("questions"); Text("Beklediklerim").tag("waiting"); Text("Karne").tag("scorecard") }.pickerStyle(.segmented).frame(width:460).accessibilityIdentifier("memoryMode") }
        if mode=="decisions" { ScrollView { DecisionLogView(m:m).padding(.bottom,24) } } else if mode=="waiting" { ScrollView { WaitingView(m:m).padding(.bottom,24) } } else if mode=="questions" { ScrollView { QuestionRadarView(m:m).padding(.bottom,24) } } else if mode=="scorecard" { ScrollView { ScorecardView(m:m).padding(.bottom,24) } } else {Text("Anahtar kelimelerle bütün toplantılarda arayın veya kaynaklı bir yanıt hazırlatın.").foregroundStyle(.secondary)
        ViewThatFits(in:.horizontal) {
            HStack { memoryQueryField;Button("Ara") { Task { await m.memorySearch() } }.accessibilityIdentifier("memorySearchButton");Button("Kayıtlardan yanıtla",action:m.askMemory).disabled(m.busy || m.memoryQuery.isEmpty).accessibilityIdentifier("memoryAskButton") }
            VStack(alignment:.leading,spacing:8) { memoryQueryField;HStack { Button("Ara") { Task { await m.memorySearch() } }.accessibilityIdentifier("memorySearchButton");Button("Kayıtlardan yanıtla",action:m.askMemory).disabled(m.busy || m.memoryQuery.isEmpty).accessibilityIdentifier("memoryAskButton") } }
        }
        ScrollView { VStack(alignment:.leading,spacing:18) { if !m.answer.isEmpty { Text(m.answer).textSelection(.enabled);EvidenceView(m:m,evidence:m.answerEvidence);Divider() };EvidenceView(m:m,evidence:m.hits) }.frame(maxWidth:.infinity,alignment:.leading) }
        }
    }.padding(24) }
}
