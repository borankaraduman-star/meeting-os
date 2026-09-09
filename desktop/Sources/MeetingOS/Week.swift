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

struct QuestionGroup: Identifiable {
    let id:String; let text:String; let count:Int; let meetings:[(title:String,created:String,meeting:String)]; let evidence:Evidence?; let answeredBy:String?; let answeredMeeting:String?
    init(_ d:[String:Any],index:Int) {
        text=d["text"] as? String ?? ""; count=d["count"] as? Int ?? 1; id="q\(index)"
        meetings=(d["meetings"] as? [[String:Any]] ?? []).map { ($0["title"] as? String ?? "", $0["created"] as? String ?? "", $0["meeting"] as? String ?? "") }
        let first=meetings.first
        evidence=(d["evidence"] as? [String:Any]).map { Evidence($0.merging(["meeting":first?.meeting ?? "","meeting_title":first?.title ?? ""]) { _,new in new }) }
        let a=d["answered_by"] as? [String:Any]; answeredBy=a?["text"] as? String; answeredMeeting=a?["title"] as? String
    }
}
struct ScoreMeeting: Identifiable {
    let id:String; let title:String; let created:String; let minutes:Double; let speakers:[(label:String,percent:Int,minutes:Double)]; let decisions:Int; let actions:Int; let questions:Int; let cost:Double
    init(_ d:[String:Any]) {
        id=d["meeting"] as? String ?? UUID().uuidString; title=d["title"] as? String ?? ""; created=d["created"] as? String ?? ""; minutes=d["minutes"] as? Double ?? 0
        speakers=(d["speakers"] as? [[String:Any]] ?? []).map { ($0["label"] as? String ?? "", $0["percent"] as? Int ?? 0, $0["minutes"] as? Double ?? 0) }
        let c=d["counts"] as? [String:Any] ?? [:]; decisions=c["decisions"] as? Int ?? 0; actions=c["actions"] as? Int ?? 0; questions=c["questions"] as? Int ?? 0; cost=d["cost"] as? Double ?? 0
    }
}

struct QuestionRadarView:View {
    @ObservedObject var m:Model
    @State private var query=""
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                TextField("Sorularda ara",text:$query).textFieldStyle(.roundedBorder).onSubmit { Task { await m.loadQuestions(query:query) } }
                Button("Ara") { Task { await m.loadQuestions(query:query) } }
                Spacer(); Text("\(m.questions.count) soru grubu").font(.caption).foregroundStyle(.secondary)
            }
            Text("Toplantılarda açık kalan sorular; birden çok toplantıda tekrar edenler üstte. “Muhtemelen cevaplandı” yalnız ipucudur, kontrol edin.").font(.callout).foregroundStyle(.secondary)
            if m.questions.isEmpty { ContentUnavailableView("Cevapsız soru yok",systemImage:"questionmark.circle",description:Text("Özet çıkarılmış toplantıların açık soruları burada toplanır.")) }
            ForEach(m.questions) { q in
                VStack(alignment:.leading,spacing:6) {
                    HStack(spacing:8) {
                        if q.count>1 { Text("\(q.count) toplantıdır").font(.caption2.weight(.semibold)).padding(.horizontal,7).padding(.vertical,2).background(Color.orange.opacity(0.15),in:Capsule()).foregroundStyle(.orange) }
                        Text(q.meetings.map { $0.title }.prefix(2).joined(separator:" · ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        Spacer()
                        if let mid=q.meetings.first?.meeting, !mid.isEmpty { Button("Toplantıyı aç") { m.selected=mid; m.tab="analysis" }.controlSize(.small) }
                    }
                    Text(q.text).font(.system(size:15,weight:.medium)).lineSpacing(4).textSelection(.enabled)
                    if let a=q.answeredBy { Label("Muhtemelen cevaplandı · \(q.answeredMeeting ?? ""): \(a)",systemImage:"checkmark.circle").font(.caption).foregroundStyle(MeetingStyle.accent).lineLimit(2) }
                    if let e=q.evidence { EvidenceView(m:m,evidence:[e]) }
                }.padding(16).frame(maxWidth:.infinity,alignment:.leading).meetingCard()
            }
        }.task { if m.questions.isEmpty { await m.loadQuestions(query:"") } }
    }
}

struct ScorecardView:View {
    @ObservedObject var m:Model
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            HStack { Text("Son 7 gün").font(.headline); Spacer(); Button("Yenile") { Task { await m.loadPeriodScorecard() } }.controlSize(.small) }
            if let p=m.scorePeriod {
                LazyVGrid(columns:[GridItem(.adaptive(minimum:150),spacing:12)],spacing:12) {
                    SmallMetric(value:String(format:"%.1f sa",p["hours"] as? Double ?? 0),label:"\(p["meetings"] as? Int ?? 0) toplantı",icon:"clock")
                    SmallMetric(value:"\(p["decisions"] as? Int ?? 0)",label:"karar",icon:"checkmark.seal")
                    SmallMetric(value:"\(p["tasks"] as? Int ?? 0)",label:"görev",icon:"checklist")
                    SmallMetric(value:"\(p["questions"] as? Int ?? 0)",label:"açık soru",icon:"questionmark.circle")
                    SmallMetric(value:String(format:"$%.2f",p["cost"] as? Double ?? 0),label:"transkript ücreti",icon:"cloud")
                }
                if let sp=p["speakers"] as? [[String:Any]], !sp.isEmpty {
                    Text("En çok konuşanlar (adı bilinenler)").font(.caption).foregroundStyle(.secondary)
                    ForEach(Array(sp.prefix(6).enumerated()),id:\.offset) { _,s in HStack { Text(s["name"] as? String ?? ""); Spacer(); Text(String(format:"%.0f dk · %d toplantı",s["minutes"] as? Double ?? 0,s["meetings"] as? Int ?? 0)).font(.caption.monospacedDigit()).foregroundStyle(.secondary) } }
                }
            }
            Text("Toplantılar").font(.headline).padding(.top,6)
            Text("Yalnız kaydedilen toplantılar sayılır; ad verilmemiş konuşmacılar “Konuşmacı n” olarak görünür.").font(.caption).foregroundStyle(.secondary)
            ForEach(m.scoreMeetings) { s in
                VStack(alignment:.leading,spacing:5) {
                    HStack { Text(s.title).font(.system(size:14,weight:.medium)).lineLimit(1); Spacer(); Text(MeetingDates.label(s.created)).font(.caption.monospacedDigit()).foregroundStyle(.secondary); Button("Aç") { m.selected=s.id; m.tab="analysis" }.controlSize(.mini) }
                    HStack(spacing:10) {
                        Text(String(format:"%.0f dk",s.minutes)).font(.caption.monospacedDigit())
                        Text("\(s.decisions) karar · \(s.actions) görev · \(s.questions) soru").font(.caption).foregroundStyle(.secondary)
                        if s.cost>0 { Text(String(format:"$%.3f",s.cost)).font(.caption.monospacedDigit()).foregroundStyle(.secondary) }
                        Spacer()
                        Text(s.speakers.prefix(4).map { "\($0.label) %\($0.percent)" }.joined(separator:" · ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                }.padding(12).frame(maxWidth:.infinity,alignment:.leading).meetingCard()
            }
        }.task { if m.scoreMeetings.isEmpty { await m.loadPeriodScorecard() } }
    }
}
