import SwiftUI

/// One row of the critical review queue: why this spot deserves a listen, and the one action that fixes it.
struct ReviewItem:Identifiable, Equatable {
    let id:String; let segment:Int?; let start:Double?; let speaker:String; let text:String; let kind:String; let severity:Int; let reason:String; let suggested:String; let speakerKey:String; let task:String; let original:String; let replacement:String; let verified:Bool; let count:Int
    /// What the queue recognises this item by on the next visit, and the version of the source it came from.
    /// An answer is stored against the pair: answered for this version → gone for good; the transcript or the
    /// analysis changes → it is a new question and is asked again.
    let key:String; let sourceVersion:String
    init(_ d:[String:Any]) {
        segment=d["segment_id"] as? Int; start=d["start"] as? Double; speaker=d["speaker"] as? String ?? ""; text=d["text"] as? String ?? ""; kind=d["kind"] as? String ?? ""
        severity=d["severity"] as? Int ?? 3; reason=d["reason"] as? String ?? ""; suggested=d["suggested"] as? String ?? ""; speakerKey=d["speaker_key"] as? String ?? ""; task=d["task"] as? String ?? ""
        original=d["original"] as? String ?? ""; replacement=d["replacement"] as? String ?? ""; verified=d["verified"] as? Bool ?? false
        count=d["count"] as? Int ?? 0
        sourceVersion=d["source_version"] as? String ?? ""
        let bridged=d["key"] as? String ?? ""
        key=bridged.isEmpty ? kind+":"+(segment.map(String.init) ?? task) : bridged
        id=kind+":"+(segment.map(String.init) ?? task)+(original.isEmpty ? "" : ":"+original)
    }
    var title:String {
        switch kind {
        case "suggested_name": return "İsim onayı bekliyor"
        case "unnamed_speaker": return "İsimsiz konuşmacı"
        case "ambiguous": return "Çakışan konuşma"
        case "short_match": return "Kısa sesle tanındı"
        case "task_owner": return "Görev sahibi belirsiz"
        case "task_review": return "Görev kontrol bekliyor"
        case "marker": return "İşaretlediğiniz an"
        case "glossary": return "Sözlük düzeltmesi"
        case "word": return "Kelime: “\(original)” muhtemelen “\(replacement)”"
        default: return "Kontrol edin"
        }
    }
    var time:String { start.map { String(format:"%02d:%02d",Int($0)/60,Int($0)%60) } ?? "" }
}

/// The pure part of resolving a Kontrol item.
enum ReviewUX {
    static let results:[(code:String,label:String)]=[("correct","Doğru"),("corrected","Düzelt…"),("skipped","Geç")]
    static func label(_ code:String)->String { results.first { $0.code==code }?.label ?? code }
    /// Every item can be answered once it knows what it is; an item with no key is not a question yet.
    static func resolvable(_ item:ReviewItem)->Bool { !item.key.isEmpty }
    /// "Geç" is a deferral, not an approval, and the help text has to say so — a queue shrunk by skipping
    /// has not got better.
    static func help(_ code:String)->String {
        switch code {
        case "correct": return "Bu madde doğru · bu sürüm için bir daha sorulmaz"
        case "corrected": return "Düzelttim · kaynak değişirse yeniden değerlendirilir"
        default: return "Şimdilik geç · onay değildir, yalnız bu sürümde gizlenir"
        }
    }
}

struct ReviewView:View {
    @ObservedObject var model:Model
    /// Glossary items the analysis model accepted (their reason carries the model's note, not the local-only hint).
    private var verifiedGlossary:Int { model.review.filter { $0.kind=="glossary" && $0.verified }.count }
    @State private var showScorecard=false
    @State private var showMaintenance=false
    var body:some View {
        ScrollView { VStack(alignment:.leading,spacing:14) {
            HStack {
                Text("Kontrol").font(.system(size:23,weight:.bold,design:.rounded))
                Spacer()
                Text("\(model.review.count) madde").font(.caption).foregroundStyle(.secondary)
                Menu {
                    Button("Sözlükle tara") { Task { await model.scanGlossary() } }.disabled(model.busy || model.selected==nil).accessibilityIdentifier("scanGlossaryButton")
                    Divider()
                    Toggle("Son 7 gün karnesi",isOn:$showScorecard).accessibilityIdentifier("scorecardToggle")
                    Toggle("Haftalık bakım",isOn:$showMaintenance).accessibilityIdentifier("maintenanceToggle")
                } label: { Image(systemName:"ellipsis.circle") }.menuStyle(.borderlessButton).fixedSize()
                    .help("Sözlükle tara: transkripti proje sözlüğüyle karşılaştırır. Karne ve bakım panellerini buradan açıp kapatırsınız.")
                    .accessibilityIdentifier("reviewMenu")
            }
            Text("Bütün metni okumak yerine yalnız şüpheli yerleri dinleyip düzeltin. Her madde neden şüpheli bulunduğunu söyler.").font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
            ReviewDebtView(m:model)
            if showScorecard { VStack(alignment:.leading,spacing:8) { Label("Son 7 gün karnesi · toplantı saati, karar, görev, konuşma payı",systemImage:"chart.bar").font(.callout); ScorecardView(m:model) }.accessibilityIdentifier("scorecardGroup") }
            if showMaintenance { VStack(alignment:.leading,spacing:8) { Label("Haftalık bakım · profiller, öğrenilen kurallar, disk",systemImage:"wrench.and.screwdriver").font(.callout); MaintenanceView(m:model) }.accessibilityIdentifier("maintenanceGroup") }
            if verifiedGlossary>0 {
                HStack(spacing:10) {
                    Label("\(verifiedGlossary) sözlük düzeltmesi analiz modelince doğrulandı",systemImage:"character.book.closed").font(.callout)
                    Spacer()
                    Button("Doğrulananları uygula (\(verifiedGlossary))") { Task { await model.applyAllGlossary() } }.buttonStyle(.borderedProminent).disabled(model.busy).help("Yalnız modelin kabul ettiği öneriler uygulanır; yerel eşlemeler tek tek kontrol için kalır").accessibilityIdentifier("applyAllGlossaryButton")
                }.padding(14).meetingCard()
            }
            if !model.scorecard.isEmpty { Label(model.scorecard,systemImage:"chart.bar").font(.caption).foregroundStyle(.secondary).help("Düzeltmelerinizden biriken yerel kalite seti; model eğitilmez, iyileşme ölçülür") }
            if model.review.isEmpty {
                CenteredNotice(icon:"checkmark.seal",title:"Kontrol gerektiren bir şey yok",detail:"Konuşmacı adları, çakışan konuşmalar ve görev sahipleri için şüpheli bir bölüm bulunmadı.")
                    .inlineNoticeArea()
            }
            ForEach(model.review) { item in
                VStack(alignment:.leading,spacing:8) {
                    HStack(spacing:8) {
                        Image(systemName:item.kind=="marker" ? "bookmark.fill" : (item.severity==1 ? "exclamationmark.circle.fill" : (item.severity==2 ? "questionmark.circle" : "ear"))).foregroundStyle(item.kind=="marker" ? MeetingStyle.accent : (item.severity==1 ? .orange : .secondary))
                        Text(item.title).font(.headline)
                        if !item.time.isEmpty { Text(item.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary) }
                        if !item.speaker.isEmpty { Text("· "+item.speaker).font(.caption).foregroundStyle(.secondary) }
                        if item.kind=="word", item.count>0 { Text("· bu toplantıda \(item.count) yerde").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("wordCount-\(item.segment.map(String.init) ?? item.original)") }
                        Spacer()
                    }
                    Text(item.reason).font(.callout)
                    if !item.text.isEmpty { Text("“"+item.text+"”").font(.system(size:14)).foregroundStyle(.secondary).lineLimit(3) }
                    HStack(spacing:10) {
                        if let seg=item.segment {
                            Button("Bölüme git") { model.reveal(segment:seg) }.accessibilityIdentifier("reviewGo-\(item.id)")
                            if model.rows.contains(where:{ $0.id==seg }) { Button { if let row=model.rows.first(where:{ $0.id==seg }) { model.play(row) } } label: { PlayGlyph(playback:model.playback,key:"row:\(seg)",text:"Dinle") } }
                        }
                        if item.kind=="suggested_name", !item.suggested.isEmpty {
                            Button("“\(item.suggested)” olarak onayla") { Task { await model.confirmReview(item) } }.buttonStyle(.borderedProminent).disabled(model.busy).accessibilityIdentifier("reviewConfirm-\(item.id)")
                        }
                        if item.kind=="unnamed_speaker" || item.kind=="short_match" || item.kind=="suggested_name", let seg=item.segment, let row=model.rows.first(where:{ $0.id==seg }) {
                            Button("Adlandır…") { model.editRow=row;model.editName=row.name;model.editText=row.text;model.clean=false }
                        }
                        if item.kind=="task_owner" || item.kind=="task_review" { Button("Görevlerim’de aç") { model.navigate { model.tab="actions" } } }
                        if item.kind=="word" {
                            // One click teaches the word: this meeting is fixed everywhere and later meetings correct near misses on their own.
                            Button("Düzelt ve öğret") { Task { await model.applyWord(item) } }.buttonStyle(.borderedProminent).disabled(model.busy).help("Bu toplantıdaki bütün geçişleri düzeltir ve kelimeyi öğrenir").accessibilityIdentifier("wordApply-\(item.segment.map(String.init) ?? item.original)")
                            Button("Bu doğru") { Task { await model.dismissWord(item) } }.disabled(model.busy).help("Kelime doğru yazılmış; madde listeden kalkar, metin değişmez").accessibilityIdentifier("wordDismiss-\(item.segment.map(String.init) ?? item.original)")
                        }
                    }.font(.callout)
                    if (item.kind=="unnamed_speaker" || item.kind=="short_match"), !item.speakerKey.isEmpty, !model.calendarAttendees.isEmpty {
                        VStack(alignment:.leading,spacing:5) {
                            Text("Takvimdeki katılımcılardan seç").font(.caption).foregroundStyle(.secondary)
                            FlowChips(items:model.calendarAttendees) { name in Task { await model.nameSpeaker(item.speakerKey,name) } }
                        }
                    }
                    HStack(spacing:0) {
                        if item.kind=="glossary" {
                            Button("Uygula: “\(item.replacement)”") { Task { await model.applyGlossary(item) } }.buttonStyle(.borderedProminent).disabled(model.busy).accessibilityIdentifier("applyGlossary-\(item.id)")
                            Button("Yoksay") { Task { await model.dismissGlossary(item) } }.disabled(model.busy).help("Öneriyi listeden kaldırır; metin değişmez").accessibilityIdentifier("dismissGlossary-\(item.id)")
                        }
                    }.font(.callout)
                    // Every item can be closed, whatever its kind: the answer is kept against the version of
                    // the source it came from, so it never comes back on its own — and comes back in full if
                    // the transcript or the analysis changes underneath it.
                    if ReviewUX.resolvable(item) {
                        HStack(spacing:10) {
                            ForEach(ReviewUX.results,id:\.code) { result in
                                Button(result.label) { Task { await model.resolveReview(item,result:result.code) } }
                                    .disabled(model.busy).help(ReviewUX.help(result.code))
                                    .accessibilityIdentifier("reviewResolve-\(result.code)-\(item.id)")
                            }
                            Spacer(minLength:0)
                        }.font(.callout).padding(.top,2)
                    }
                }.padding(18).meetingCard()
            }
        }.padding(24).readingColumn() }
        .task(id:model.selected) { await model.loadReview(); await model.loadScorecard() }
    }
}
