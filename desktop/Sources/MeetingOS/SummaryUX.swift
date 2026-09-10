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
    static func chips(review:Bool,superseded:Bool)->[SummaryChip] {
        if superseded { return [SummaryChip(text:"geri alındı",icon:"arrow.uturn.backward")] }
        return review ? [SummaryChip(text:"kontrol",icon:"exclamationmark.triangle")] : []
    }
    /// Two sections can carry the same sentence, so an expanded item is keyed by its section too.
    static func key(_ section:String,_ item:String)->String { "\(section)|\(item)" }
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
    let item:Insight; let history:[PreviousDecision]; let expanded:Bool; let toggle:()->Void
    var details:Int { item.evidence.count+history.count }
    var body:some View {
        VStack(alignment:.leading,spacing:0) {
            Button(action:toggle) {
                HStack(alignment:.firstTextBaseline,spacing:8) {
                    Text("•").font(.system(size:15,weight:.bold)).foregroundStyle(MeetingStyle.accent)
                    Text(item.text).font(.system(size:15)).lineSpacing(4).multilineTextAlignment(.leading).textSelection(.enabled)
                        .strikethrough(item.superseded).foregroundStyle(item.superseded ? AnyShapeStyle(.secondary):AnyShapeStyle(.primary))
                        .fixedSize(horizontal:false,vertical:true)
                    ForEach(SummaryUX.chips(review:item.review,superseded:item.superseded)) { SummaryChipView(chip:$0) }
                    Spacer(minLength:8)
                    if details>0 {
                        Image(systemName:"chevron.down").font(.system(size:9,weight:.semibold)).foregroundStyle(.secondary)
                            .rotationEffect(.degrees(expanded ? 0: -90)).accessibilityHidden(true)
                    }
                }.padding(.vertical,7).contentShape(Rectangle())
            }.buttonStyle(.plain).disabled(details==0)
                .help(details==0 ? "" : expanded ? "Kanıtları gizle":"Bu maddenin neye dayandığını göster (\(details))")
                .accessibilityHint(details==0 ? "" : "Kaynak konuşmaları açar")
            if expanded, details>0 {
                VStack(alignment:.leading,spacing:6) {
                    ForEach(history) { p in Label("Önceki karar · \(p.meetingTitle): \(p.text)",systemImage:"clock.arrow.circlepath").font(.caption).foregroundStyle(.secondary) }
                    EvidenceView(m:m,evidence:item.evidence)
                    if item.evidence.isEmpty && history.isEmpty { Text("Bu madde için kaynak konuşma kaydedilmemiş.").font(.caption).foregroundStyle(.secondary) }
                }.padding(.leading,20).padding(.bottom,8)
            }
        }
    }
}

/// A section of the summary: header with its count, a "show the evidence" switch for the whole section,
/// then one line per item.
struct SummarySection:View {
    @ObservedObject var m:Model
    let section:String; let label:String; let items:[Insight]
    @Binding var expanded:Set<String>
    /// Only decisions carry earlier-meeting history; everything else is backed by quotes alone.
    func history(_ item:Insight)->[PreviousDecision] { section=="decisions" ? (m.continuity.historyByDecision[item.text] ?? []):[] }
    /// Only items that actually have something folded away take part in the section switch.
    var keys:Set<String> { Set(items.filter { !$0.evidence.isEmpty || !history($0).isEmpty }.map { SummaryUX.key(section,$0.id) }) }
    var allShown:Bool { !keys.isEmpty && keys.isSubset(of:expanded) }
    var body:some View {
        VStack(alignment:.leading,spacing:2) {
            HStack(alignment:.firstTextBaseline) {
                Text(items.isEmpty ? label:"\(label) · \(items.count)").font(.headline)
                Spacer(minLength:12)
                if !keys.isEmpty {
                    Button(allShown ? "Kanıtları gizle":"Kanıtları göster") { if allShown { expanded.subtract(keys) } else { expanded.formUnion(keys) } }
                        .buttonStyle(.plain).font(.caption).foregroundStyle(.secondary)
                        .accessibilityIdentifier("evidenceToggle-\(section)")
                }
            }.padding(.bottom,4)
            if items.isEmpty { Text("Kayıtlarda açık bir madde bulunmadı.").font(.callout).foregroundStyle(.secondary) }
            else {
                LazyVStack(alignment:.leading,spacing:0) {
                    ForEach(items) { item in
                        let key=SummaryUX.key(section,item.id)
                        InsightRow(m:m,item:item,history:history(item),expanded:expanded.contains(key)) {
                            if expanded.contains(key) { expanded.remove(key) } else { expanded.insert(key) }
                        }
                    }
                }
            }
        }.accessibilityIdentifier("summarySection-\(section)")
    }
}
