import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ActionsView:View {
    @ObservedObject var m:Model
    @State var draftEdit:DraftItem?;@State var draftText=""
    /// The choice sticks: changing meetings — or relaunching — must not move the filter under the user.
    @AppStorage(ActionsFilter.key) var stored="mine"
    @State var edit:ActionItem?;@State var title="";@State var owner="";@State var due=""
    var filter:String { ActionsFilter.normalize(stored) }
    /// "Bana ait" compares against the name in Ayarlar → Genel → Adınız through the same fold the bridge uses
    /// (store.fold_name): lowercasing alone left "Ayşe" and "Ayse" — and every unset name — as different people.
    func matches(_ item:ActionItem,_ f:String)->Bool { f=="all" || (f=="mine" ? NameFold.same(item.owner,m.userName) : item.meeting==m.selected) }
    var visible:[ActionItem] { m.actions.filter { matches($0,filter) } }
    /// Open tasks behind each segment, so an empty "Bana ait" never hides the meeting's tasks.
    func count(_ f:String)->Int { m.actions.filter { matches($0,f) && !["done","dismissed"].contains($0.state) }.count }
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
    func handoffButton(_ item:ActionItem)->some View {
        Button("\(item.route) için paket kaydet") { Task { await m.exportHandoff(item) } }
            .disabled(item.stale || ["done","dismissed"].contains(item.state))
            .accessibilityIdentifier("exportHandoff-\(item.id)")
    }
    var body:some View { VStack(alignment:.leading) {
        HStack { Text("Görevlerim").font(.system(size:23,weight:.bold,design:.rounded));Spacer();Text("\(visible.filter { !["done","dismissed"].contains($0.state) }.count) açık · \(visible.count) toplam").font(.callout).foregroundStyle(.secondary) }.padding(.horizontal,24).padding(.top,20)
        // Pinned above the list: the filter never scrolls away with the tasks it filters.
        HStack { Picker("Görevler",selection:Binding(get:{ filter },set:{ stored=$0 })) { Text("Bana ait (\(count("mine")))").tag("mine");Text("Bu toplantı (\(count("meeting")))").tag("meeting");Text("Tüm görevler (\(count("all")))").tag("all") }.pickerStyle(.segmented); Spacer(minLength:8); Menu("Dışa aktar") { Button("Brifing…") { Task { await m.exportBrief() } }; Button("Sonraki toplantı gündemi…") { Task { await m.exportAgenda() } }; Divider(); Button("Gün sonu özeti…") { Task { await m.exportDigest() } }; Button("Hafta özeti…") { Task { await m.exportWeeklyDigest() } } }.fixedSize().help("Markdown olarak kaydeder; hiçbir yere gönderilmez").accessibilityIdentifier("actionsExportMenu") }.padding().task(id:m.selected) { await m.loadContinuity() }.accessibilityIdentifier("actionsFilterPicker")
        ScrollView { LazyVStack(alignment:.leading,spacing:18) {
            if visible.isEmpty {
                ContentUnavailableView { Label("Görev bulunamadı",systemImage:"checklist") } description: {
                    Text(ActionsFilter.emptyMessage(filter:filter,meetingOpen:count("meeting")))
                } actions: {
                    if ActionsFilter.offersMeetingSwitch(filter:filter,meetingOpen:count("meeting")) {
                        Button("Bu toplantı") { stored="meeting" }.buttonStyle(.link).accessibilityIdentifier("showMeetingTasksButton")
                    }
                }
            }
            ForEach(visible) { item in VStack(alignment:.leading,spacing:10) {
                HStack(alignment:.top) { Text(item.title).font(.headline).strikethrough(["done","dismissed"].contains(item.state)).textSelection(.enabled);Spacer() }   // the state picker below already says the state
                Text("\(item.owner.isEmpty ? "Sahibi belirsiz" : item.owner) · \(item.due.isEmpty ? "Tarih belirtilmedi" : item.due) · \(item.meetingTitle)").font(.caption).foregroundStyle(.secondary)
                if item.stale { Label("Kaynak değişti · Görevi yeniden doğrulayın",systemImage:"exclamationmark.triangle").foregroundStyle(.orange) }
                if let rel=m.continuity.relatedByTask[item.id], let first=rel.first(where:{ $0.supersededBy.isEmpty && $0.state != "dismissed" }) {
                    HStack(spacing:8) {
                        Label("Önceki toplantıda benzer görev · \(first.meetingTitle): “\(first.title)” (\(first.state=="done" ? "tamamlandı" : "açık"))",systemImage:"arrow.triangle.branch").font(.caption).foregroundStyle(.secondary)
                        if first.state != "done" { Button("Aynı görev, eskisini kapat") { Task { await m.supersede(old:first.id,new:item.id) } }.controlSize(.small).help("Eski görev “kaldırıldı” olur ve bu göreve bağlanır; kaynaklar korunur") }
                    }
                }
                HStack(spacing:10) {
                    statePicker(item); dueChip(item); Spacer(minLength:6)
                    Menu {
                        Button("Düzenle…") { edit=item;title=item.title;owner=item.owner;due=item.due }
                        Button("Hatırlatıcılar’a ekle") { m.addReminder(item) }.disabled(["done","dismissed"].contains(item.state)).help("Görevi Apple Hatırlatıcılar’daki varsayılan listeye ekler; kaynak toplantı ve zaman notu ile").accessibilityIdentifier("addReminder-\(item.id)")
                        Button(m.drafts.contains { $0.task==item.id && !$0.stale } ? "Taslağı yeniden hazırla" : "Taslak hazırla") { m.prepareAction(item,force:m.drafts.contains { $0.task==item.id && !$0.stale }) }.disabled(m.busy || item.stale || ["done","dismissed"].contains(item.state))
                        Button("\(item.route) için paket kaydet…") { Task { await m.exportHandoff(item) } }.disabled(item.stale || ["done","dismissed"].contains(item.state))
                    } label: { Image(systemName:"ellipsis.circle") }.menuStyle(.borderlessButton).fixedSize().accessibilityIdentifier("taskMenu-\(item.id)")
                }
                EvidenceView(m:m,evidence:item.evidence)
                ForEach(m.drafts.filter {$0.task==item.id}.prefix(1)) { draft in DisclosureGroup(draft.stale ? "Güncel olmayan taslak":"İncelenecek taslak · gönderilmedi") { VStack(alignment:.leading) { Text(draft.text).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading).padding(.top,8);Button("Taslağı düzenle") { draftEdit=draft;draftText=draft.text }.disabled(draft.stale) } } }
            }.padding(20).meetingCard() }
        }.padding(24) }
    }.sheet(item:$draftEdit) { draft in VStack(alignment:.leading,spacing:16) { Text("Taslağı düzenle").font(.title2.bold());TextEditor(text:$draftText).frame(height:340);HStack { Button("Vazgeç") { draftEdit=nil };Spacer();Button("Kaydet") { Task { do { _=try await m.request(["action":"draft_update","draft":draft.id,"text":draftText]);try await m.refreshIntelligence(m.selected ?? "");draftEdit=nil } catch { m.error=error.localizedDescription } } } } }.padding(24).frame(width:650) }.sheet(item:$edit) { item in VStack(alignment:.leading,spacing:16) { Text("Görevi düzenle").font(.title2.bold());TextField("Görev",text:$title);TextField("Sahibi",text:$owner);TextField("Kaynakta geçen tarih",text:$due);Text("Otomatik çıkarım öneridir. Sahip ve tarihi kaynak konuşmayla doğrulayın.").font(.caption).foregroundStyle(.secondary);HStack { Button("Vazgeç") { edit=nil };Spacer();Button("Kaydet") { Task { await m.updateAction(item,changes:["title":title,"owner":owner,"due_text":due]);edit=nil } }.disabled(title.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty) } }.padding(24).frame(width:500) } }
}
