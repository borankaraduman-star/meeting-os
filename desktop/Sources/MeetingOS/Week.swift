import SwiftUI

/// Cross-meeting views fed by the Python side: decision log, waiting-on board, weekly review debt.
struct DecisionEntry: Identifiable {
    let id:String; let meeting:String; let title:String; let created:String; let text:String; let evidence:Evidence?; let previous:[(title:String,created:String,text:String)]
    init(_ d:[String:Any],index:Int) {
        let mid=d["meeting"] as? String ?? "", ttl=d["title"] as? String ?? ""
        meeting=mid; title=ttl; created=d["created"] as? String ?? ""; text=d["text"] as? String ?? ""
        id="\(mid):\(index)"
        evidence=(d["evidence"] as? [String:Any]).map { Evidence($0.merging(["meeting":mid,"meeting_title":ttl]) { _,new in new }) }
        previous=(d["previous"] as? [[String:Any]] ?? []).map { ($0["title"] as? String ?? "", $0["created"] as? String ?? "", $0["text"] as? String ?? "") }
    }
}
struct WaitingItem: Identifiable {
    let id:String; let title:String; let meetingTitle:String; let meeting:String; let age:Int; let quote:String; let repeatCount:Int; let due:String
    init(_ d:[String:Any]) { id=d["task"] as? String ?? UUID().uuidString; title=d["title"] as? String ?? ""; meetingTitle=d["meeting_title"] as? String ?? ""; meeting=d["meeting"] as? String ?? ""; age=d["age_days"] as? Int ?? 0; quote=d["quote"] as? String ?? ""; repeatCount=d["meetings"] as? Int ?? (d["repeat"] as? Bool == true ? 2 : 1); due=d["due_text"] as? String ?? "" }
}
struct WaitingPerson: Identifiable {
    let id:String; let items:[WaitingItem]; let reminder:String
    init(_ d:[String:Any]) { id=d["owner"] as? String ?? "?"; items=(d["items"] as? [[String:Any]] ?? []).map(WaitingItem.init); reminder=d["reminder_text"] as? String ?? "" }
}
struct DebtItem: Identifiable {
    let id:String; let meeting:String; let meetingTitle:String; let created:String; let item:ReviewItem
    init(_ d:[String:Any]) { item=ReviewItem(d); meeting=d["meeting"] as? String ?? ""; meetingTitle=d["meeting_title"] as? String ?? ""; created=d["created"] as? String ?? ""; id=meeting+":"+item.id }
}

struct DecisionLogView:View {
    @ObservedObject var m:Model
    @State private var query=""
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                TextField("Kararlarda ara",text:$query).textFieldStyle(.roundedBorder).onSubmit { Task { await m.loadDecisions(query:query) } }.accessibilityIdentifier("decisionQuery")
                Button("Ara") { Task { await m.loadDecisions(query:query) } }
                Spacer()
                Text("\(m.decisions.count) karar").font(.caption).foregroundStyle(.secondary)
                Button("Markdown…") { Task { await m.exportDecisions(query:query) } }.disabled(m.decisions.isEmpty)
            }
            if m.decisions.isEmpty { ContentUnavailableView("Karar bulunamadı",systemImage:"checkmark.seal",description:Text("Özet çıkarılmış toplantıların kararları burada tek listede görünür.")) }
            ForEach(m.decisions) { d in
                VStack(alignment:.leading,spacing:6) {
                    HStack { Text(d.title).font(.caption.weight(.medium)).lineLimit(1); Text(MeetingDates.label(d.created)).font(.caption.monospacedDigit()).foregroundStyle(.secondary); Spacer(); Button("Toplantıyı aç") { m.selected=d.meeting; m.tab="analysis" }.controlSize(.small) }
                    Text(d.text).font(.system(size:15,weight:.medium)).lineSpacing(4).textSelection(.enabled)
                    if let e=d.evidence { EvidenceView(m:m,evidence:[e]) }
                    ForEach(Array(d.previous.enumerated()),id:\.offset) { _,p in Label("Önceki · \(p.title) · \(MeetingDates.label(p.created)): \(p.text)",systemImage:"clock.arrow.circlepath").font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                }.padding(16).frame(maxWidth:.infinity,alignment:.leading).meetingCard()
            }
        }.task { if m.decisions.isEmpty { await m.loadDecisions(query:"") } }
    }
}

struct WaitingView:View {
    @ObservedObject var m:Model
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            HStack { Text("Başkalarının verdiği sözler, kişiye göre. Sahibi belirsiz görevler burada değil, Kontrol’de.").font(.callout).foregroundStyle(.secondary); Spacer(); Button("Yenile") { Task { await m.loadWaiting() } }.controlSize(.small) }
            if m.waiting.isEmpty { ContentUnavailableView("Kimseden bir şey beklemiyorsun",systemImage:"person.2",description:Text("Sahibi başkası olan açık görev yok.")) }
            ForEach(m.waiting) { p in
                VStack(alignment:.leading,spacing:8) {
                    HStack { Text(p.id).font(.headline); Text("\(p.items.count) söz").font(.caption).foregroundStyle(.secondary); Spacer()
                        Button("Hatırlatma metnini kopyala") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(p.reminder,forType:.string); m.activity="Hatırlatma metni panoya kopyalandı · \(p.id)" }.controlSize(.small).accessibilityIdentifier("copyReminder-\(p.id)") }
                    ForEach(p.items) { it in
                        VStack(alignment:.leading,spacing:3) {
                            HStack(spacing:8) { Text(it.title).font(.system(size:14,weight:.medium)); Spacer(); if it.repeatCount>1 { Text("\(it.repeatCount) toplantıdır").font(.caption2).padding(.horizontal,6).padding(.vertical,2).background(Color.orange.opacity(0.15),in:Capsule()).foregroundStyle(.orange) }; Text("\(it.age) gündür açık").font(.caption.monospacedDigit()).foregroundStyle(it.age>=14 ? .orange : .secondary) }
                            HStack(spacing:6) { Text(it.meetingTitle).font(.caption).foregroundStyle(.secondary).lineLimit(1); if !it.due.isEmpty { Text("· \(it.due)").font(.caption).foregroundStyle(.secondary) }; Spacer(); Button("Aç") { m.selected=it.meeting; m.tab="actions" }.controlSize(.mini) }
                            if !it.quote.isEmpty { Text("“\(Fillers.clean(it.quote))”").font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                        }.padding(.vertical,4)
                    }
                }.padding(16).frame(maxWidth:.infinity,alignment:.leading).meetingCard()
            }
        }.task { if m.waiting.isEmpty { await m.loadWaiting() } }
    }
}

struct ReviewDebtView:View {
    @ObservedObject var m:Model
    @State private var expanded=false
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            HStack(spacing:8) {
                Image(systemName:"calendar.badge.exclamationmark").foregroundStyle(MeetingStyle.accent)
                Text(m.debt.isEmpty ? "Son 7 günde bekleyen kontrol maddesi yok" : "Son 7 gün · \(m.debt.count) madde: "+m.debtSummary).font(.callout)
                Spacer()
                if !m.debt.isEmpty { Button(expanded ? "Gizle" : "Tümünü göster") { expanded.toggle() }.controlSize(.small).accessibilityIdentifier("toggleDebt") }
                Button("Yenile") { Task { await m.loadReviewDebt() } }.controlSize(.small)
            }
            if expanded {
                ForEach(m.debt) { d in
                    HStack(spacing:8) {
                        Text(d.item.title).font(.caption.weight(.medium)); Text(d.meetingTitle).font(.caption).foregroundStyle(.secondary).lineLimit(1); Text(MeetingDates.label(d.created)).font(.caption.monospacedDigit()).foregroundStyle(.secondary); Spacer()
                        Button("Aç") { m.selected=d.meeting; if let seg=d.item.segment { DispatchQueue.main.asyncAfter(deadline:.now()+1.2) { m.reveal(segment:seg) } } }.controlSize(.mini)
                    }
                }
            }
        }.padding(14).meetingCard().task { if m.debt.isEmpty { await m.loadReviewDebt() } }
    }
}
