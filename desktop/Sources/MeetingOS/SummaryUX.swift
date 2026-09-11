import SwiftUI

/// One state chip on a summary item. The old page spent a whole extra line on each of these.
struct SummaryChip:Identifiable, Equatable {
    let text:String; let icon:String
    var id:String { text }
}

/// The pure decisions behind the Özet page: the single compact line under the title, the chips that
/// replaced the extra lines under every item, and the key an expanded item is remembered by.
enum SummaryUX {
    /// "335 bölüm · 8 açık görev · özet hazır". Counts that are zero drop out; the summary state always shows.
    static func statsLine(segments:Int,openTasks:Int,hasSummary:Bool,stale:Bool)->String {
        var parts:[String]=[]
        if segments>0 { parts.append("\(segments) bölüm") }
        if openTasks>0 { parts.append("\(openTasks) açık görev") }
        parts.append(!hasSummary ? "özet bekliyor" : stale ? "özet güncel değil" : "özet hazır")
        return parts.joined(separator:" · ")
    }
    /// A superseded item is history: the review warning would only add noise next to "geri alındı".
    /// What the user decided outranks both — an item they approved or reworded says so first.
    static func chips(review:Bool,superseded:Bool,confirmed:Bool=false,edited:Bool=false)->[SummaryChip] {
        var mine:[SummaryChip]=[]
        if confirmed { mine.append(SummaryChip(text:"doğru",icon:"checkmark.seal")) }
        if edited { mine.append(SummaryChip(text:"düzeltildi",icon:"pencil")) }
        if superseded { return mine+[SummaryChip(text:"geri alındı",icon:"arrow.uturn.backward")] }
        return mine+(review ? [SummaryChip(text:"kontrol",icon:"exclamationmark.triangle")]:[])
    }
    /// Two sections can carry the same sentence, so an expanded item is keyed by its section too.
    static func key(_ section:String,_ item:String)->String { "\(section)|\(item)" }

    // MARK: - Kullanıcı kararı (Düzelt · Kaldır · Doğru)

    /// The reasons a removal may carry, in the order the menu offers them. Optional on purpose: "Kaldır"
    /// alone must never be recorded as "the model was factually wrong".
    static let removeReasons:[(code:String,label:String)]=[("wrong","Yanlış"),("duplicate","Tekrar"),("too_detailed","Gereksiz ayrıntı")]
    static func reasonLabel(_ code:String)->String { removeReasons.first { $0.code==code }?.label ?? "" }
    /// What a section actually renders: the items the user removed are folded away behind one line.
    static func visible(_ items:[Insight],showRemoved:Bool)->[Insight] { showRemoved ? items:items.filter { !$0.removed } }
    static func removedCount(_ items:[Insight])->Int { items.filter(\.removed).count }
    /// "2 madde kaldırıldı · göster" — small, always there, never a silent deletion.
    static func removedLine(_ count:Int,shown:Bool)->String { count<=0 ? "":"\(count) madde kaldırıldı · "+(shown ? "gizle":"göster") }
    /// "1 değişiklik eşleşmedi" — a correction whose item this analysis no longer contains.
    static func unmatchedLine(_ count:Int)->String { count<=0 ? "":"\(count) değişikliğiniz bu analizde eşleşmedi" }
    /// The decisions of one section only; `section_summaries` items are shown under "Özet" like the rest.
    static func unmatched(_ all:[InsightUnmatched],section:String)->[InsightUnmatched] { all.filter { $0.section==section } }
    /// The "Doğru" entry is a switch, and its title has to say which way pressing it goes.
    static func confirmTitle(_ confirmed:Bool)->String { confirmed ? "Doğru işaretini kaldır":"Doğru" }
    /// ⌘↩ saves an inline correction; an unchanged or empty field saves nothing.
    static func editable(_ draft:String,original:String)->Bool {
        let trimmed=draft.trimmingCharacters(in:.whitespacesAndNewlines)
        return !trimmed.isEmpty && trimmed != original.trimmingCharacters(in:.whitespacesAndNewlines)
    }
}

struct SummaryChipView:View {
    let chip:SummaryChip
    var body:some View {
        Label(chip.text,systemImage:chip.icon).font(.caption2.weight(.medium)).foregroundStyle(.secondary)
            .padding(.horizontal,7).padding(.vertical,2).background(.primary.opacity(0.06),in:Capsule()).fixedSize()
    }
}

/// One summary item: a bullet and its sentence, nothing else. The quotes that back it up stay folded
/// away until this line is clicked — the reasoning is one click deep, not in everyone's way.
struct InsightRow:View {
    @ObservedObject var m:Model
    let item:Insight; let section:String; let history:[PreviousDecision]; let expanded:Bool; let toggle:()->Void
    /// The inline correction field. Which row is open lives on the Model — only one may be, so ⌘↩ always
    /// belongs to exactly one field.
    @State private var draft=""
    @FocusState private var focused:Bool
    var editing:Bool { m.editingInsight==item.id }
    var details:Int { item.evidence.count+history.count }
    var body:some View {
        VStack(alignment:.leading,spacing:0) {
            HStack(alignment:.firstTextBaseline,spacing:6) {
            Button(action:toggle) {
                HStack(alignment:.firstTextBaseline,spacing:8) {
                    Text("•").font(.system(size:15,weight:.bold)).foregroundStyle(MeetingStyle.accent)
                    Text(item.text).font(.system(size:15)).lineSpacing(4).multilineTextAlignment(.leading).textSelection(.enabled)
                        .strikethrough(item.superseded || item.removed).foregroundStyle(item.superseded || item.removed ? AnyShapeStyle(.secondary):AnyShapeStyle(.primary))
                        .fixedSize(horizontal:false,vertical:true)
                    ForEach(SummaryUX.chips(review:item.review,superseded:item.superseded,confirmed:item.confirmed,edited:item.userEdited)) { SummaryChipView(chip:$0) }
                    Spacer(minLength:8)
                    if details>0 {
                        Image(systemName:"chevron.down").font(.system(size:9,weight:.semibold)).foregroundStyle(.secondary)
                            .rotationEffect(.degrees(expanded ? 0: -90)).accessibilityHidden(true)
                    }
                }.padding(.vertical,7).contentShape(Rectangle())
            }.buttonStyle(.plain).disabled(details==0)
                .help(details==0 ? "" : expanded ? "Kanıtları gizle":"Bu maddenin neye dayandığını göster (\(details))")
                .accessibilityHint(details==0 ? "" : "Kaynak konuşmaları açar")
            menu
            }
            if editing {
                // ⌘↩ saves. The wording stays on this Mac and sits on top of the model's sentence; the
                // analysis itself is never rewritten, so "Geri al" can always bring the original back.
                VStack(alignment:.leading,spacing:6) {
                    TextField("Maddeyi kendi cümlenizle yazın",text:$draft,axis:.vertical).lineLimit(1...6).textFieldStyle(.roundedBorder).focused($focused)
                        .accessibilityIdentifier("insightEditField-\(item.id)")
                        .onSubmit { save() }
                    HStack(spacing:8) {
                        Button("Kaydet") { save() }.buttonStyle(.borderedProminent).disabled(!SummaryUX.editable(draft,original:item.text)).keyboardShortcut(.return,modifiers:.command)
                            .accessibilityIdentifier("insightEditSave-\(item.id)")
                        Button("Vazgeç") { m.editingInsight="" }.keyboardShortcut(.escape,modifiers:[])
                        if item.userEdited { Button("Model cümlesine dön") { m.editingInsight=""; Task { await m.restoreInsight(item,what:"edit") } }.accessibilityIdentifier("insightEditReset-\(item.id)") }
                        Spacer(minLength:0)
                        Text("⌘↩ kaydeder").font(.caption2).foregroundStyle(.secondary)
                    }.font(.callout)
                    if item.userEdited { Text("Modelin cümlesi: “\(item.modelText)”").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true) }
                }.padding(.leading,20).padding(.bottom,8)
            }
            if item.removed {
                HStack(spacing:8) {
                    Label("Kaldırdınız"+(item.removeReason.isEmpty ? "":" · "+SummaryUX.reasonLabel(item.removeReason)),systemImage:"eye.slash").font(.caption).foregroundStyle(.secondary)
                    Button("Geri getir") { Task { await m.restoreInsight(item,what:"remove") } }.controlSize(.small).accessibilityIdentifier("insightRestore-\(item.id)")
                    Spacer(minLength:0)
                }.padding(.leading,20).padding(.bottom,6)
            }
            if expanded, details>0 {
                VStack(alignment:.leading,spacing:6) {
                    ForEach(history) { p in Label("Önceki karar · \(p.meetingTitle): \(p.text)",systemImage:"clock.arrow.circlepath").font(.caption).foregroundStyle(.secondary) }
                    EvidenceView(m:m,evidence:item.evidence)
                    if item.evidence.isEmpty && history.isEmpty { Text("Bu madde için kaynak konuşma kaydedilmemiş.").font(.caption).foregroundStyle(.secondary) }
                }.padding(.leading,20).padding(.bottom,8)
            }
        }
    }
    /// Düzelt · Kaldır (isteğe bağlı nedenle) · Doğru. One small ⋯ per item, so the feedback sits inside the
    /// work rather than in a questionnaire at the end of the meeting.
    @ViewBuilder var menu:some View {
        Menu {
            Button(editing ? "Düzeltmeyi kapat":"Düzelt…") { let open = !editing; draft=item.text; m.editingInsight=open ? item.id:""; focused=open }
            Menu("Kaldır") {
                Button("Nedeni belirtmeden") { Task { await m.removeInsight(item,section:section,reason:nil) } }
                Divider()
                ForEach(SummaryUX.removeReasons,id:\.code) { reason in
                    Button(reason.label) { Task { await m.removeInsight(item,section:section,reason:reason.code) } }
                }
            }
            Button(SummaryUX.confirmTitle(item.confirmed)) { Task { await m.confirmInsight(item,section:section) } }
            if item.removed || item.userEdited {
                Divider()
                if item.removed { Button("Geri getir") { Task { await m.restoreInsight(item,what:"remove") } } }
                if item.userEdited { Button("Model cümlesine dön") { Task { await m.restoreInsight(item,what:"edit") } } }
            }
        } label: { Image(systemName:"ellipsis").font(.system(size:11,weight:.semibold)).foregroundStyle(.secondary).frame(width:22,height:18).contentShape(Rectangle()) }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
            .help("Bu maddeyi düzeltin, kaldırın veya doğru olarak işaretleyin")
            .accessibilityLabel("Madde işlemleri").accessibilityIdentifier("insightMenu-\(item.id)")
            .disabled(m.busy || item.itemID.isEmpty)
    }
    func save() {
        guard SummaryUX.editable(draft,original:item.text) else { m.editingInsight=""; return }
        let text=draft.trimmingCharacters(in:.whitespacesAndNewlines)
        m.editingInsight=""
        Task { await m.editInsight(item,section:section,text:text) }
    }
}

/// A section of the summary: header with its count, a "show the evidence" switch for the whole section,
/// then one line per item.
struct SummarySection:View {
    @ObservedObject var m:Model
    let section:String; let label:String; let items:[Insight]
    var unmatched:[InsightUnmatched]=[]
    @Binding var expanded:Set<String>
    /// Whether this section is currently also showing what the user removed. Per section, per visit.
    @State private var showRemoved=false
    /// Only decisions carry earlier-meeting history; everything else is backed by quotes alone.
    /// Keyed by the model's own sentence: a bullet the user reworded is still the same decision.
    func history(_ item:Insight)->[PreviousDecision] { section=="decisions" ? (m.continuity.historyByDecision[item.modelText] ?? []):[] }
    var shown:[Insight] { SummaryUX.visible(items,showRemoved:showRemoved) }
    var removed:Int { SummaryUX.removedCount(items) }
    /// Only items that actually have something folded away take part in the section switch.
    var keys:Set<String> { Set(shown.filter { !$0.evidence.isEmpty || !history($0).isEmpty }.map { SummaryUX.key(section,$0.id) }) }
    var allShown:Bool { !keys.isEmpty && keys.isSubset(of:expanded) }
    var body:some View {
        VStack(alignment:.leading,spacing:2) {
            HStack(alignment:.firstTextBaseline) {
                Text(shown.isEmpty && removed==0 ? label:"\(label) · \(items.count-removed)").font(.headline)
                Spacer(minLength:12)
                if !keys.isEmpty {
                    Button(allShown ? "Kanıtları gizle":"Kanıtları göster") { if allShown { expanded.subtract(keys) } else { expanded.formUnion(keys) } }
                        .buttonStyle(.plain).font(.caption).foregroundStyle(.secondary)
                        .accessibilityIdentifier("evidenceToggle-\(section)")
                }
            }.padding(.bottom,4)
            if shown.isEmpty { Text("Kayıtlarda açık bir madde bulunmadı.").font(.callout).foregroundStyle(.secondary) }
            else {
                LazyVStack(alignment:.leading,spacing:0) {
                    ForEach(shown) { item in
                        let key=SummaryUX.key(section,item.id)
                        InsightRow(m:m,item:item,section:section,history:history(item),expanded:expanded.contains(key)) {
                            if expanded.contains(key) { expanded.remove(key) } else { expanded.insert(key) }
                        }
                    }
                }
            }
            // Removing a bullet hides it; it never deletes it. One quiet line says how many and brings them back.
            if removed>0 {
                Button(SummaryUX.removedLine(removed,shown:showRemoved)) { showRemoved.toggle() }
                    .buttonStyle(.plain).font(.caption).foregroundStyle(.secondary).padding(.top,4)
                    .accessibilityIdentifier("removedToggle-\(section)")
            }
            let orphans=SummaryUX.unmatched(unmatched,section:section)
            if !orphans.isEmpty {
                // A re-analysis reworded or dropped the item this decision belonged to. Re-attaching it by
                // guesswork would put a "yanlış" on a different claim, so it is shown instead of applied.
                VStack(alignment:.leading,spacing:4) {
                    Text(SummaryUX.unmatchedLine(orphans.count)).font(.caption.weight(.medium)).foregroundStyle(.secondary)
                    ForEach(orphans) { o in
                        HStack(alignment:.firstTextBaseline,spacing:6) {
                            Text("eşleşmedi · "+o.label).font(.caption2).foregroundStyle(.secondary)
                            if !o.text.isEmpty { Text("“\(o.text)”").font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                            Spacer(minLength:0)
                            Button("Unut") { Task { await m.forgetUnmatched(o) } }.controlSize(.small).font(.caption2)
                                .accessibilityIdentifier("insightForget-\(o.id)")
                        }
                    }
                }.padding(.top,6).accessibilityIdentifier("unmatchedGroup-\(section)")
            }
        }.accessibilityIdentifier("summarySection-\(section)")
    }
}
