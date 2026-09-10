import SwiftUI

/// Week-two audit: "analysed", "priced" and "still fresh" are three different facts, and the cross-meeting
/// views used to blur all three into a row of zeros. These are the pure sentences behind that separation —
/// every one of them is a string decision, so the views stay dumb and the tests stay cheap.
enum AuditText {
    /// The same two words Görevlerim already uses for a task whose source moved under it.
    static let staleBadge="Kaynak değişti"
    static let staleHelp="Kaynak değişti · özeti yenileyin"

    /// A meeting nobody ever analysed has no counts — it has no analysis. "0 karar" is a lie; this says so.
    static func counts(analyzed:Bool,decisions:Int,actions:Int,questions:Int)->String {
        analyzed ? "\(decisions) karar · \(actions) görev · \(questions) soru" : "analiz yok"
    }

    /// One meeting's analysis spend. "—" when the bridge cannot price it, "(tahmini)" when it guessed.
    static func meetingCost(_ value:Double?,known:Bool,estimated:Bool)->String {
        guard known, let v=value else { return "—" }
        return String(format:"$%.3f",v)+(estimated ? " (tahmini)" : "")
    }

    /// The period card's analysis spend; same rule, coarser format, no per-meeting estimate flag.
    static func periodCost(_ value:Double?,known:Bool)->String {
        guard known, let v=value else { return "—" }
        return String(format:"$%.2f",v)
    }

    /// The gap the karne used to hide: meetings inside the window that were never analysed at all.
    static func unanalyzed(_ n:Int)->String? { n>0 ? "\(n) toplantı analiz edilmedi" : nil }

    /// Where a cross-meeting list came from, and how much of it has since gone out of date.
    static func sourceLine(staleMeetings:Int)->String {
        let base="Her toplantının en güncel analizinden alınmıştır"
        return staleMeetings>0 ? base+" · \(staleMeetings) toplantının analizi bayat" : base
    }
}

/// The orange "source moved" chip, shared by Karne, Kararlar, Sorular and Beklediklerim so one glance means
/// one thing everywhere.
struct StaleBadge:View {
    var body:some View {
        Text(AuditText.staleBadge).font(.caption2.weight(.semibold))
            .padding(.horizontal,7).padding(.vertical,2)
            .background(Color.orange.opacity(0.15),in:Capsule()).foregroundStyle(.orange)
            .help(AuditText.staleHelp).accessibilityLabel(AuditText.staleHelp).accessibilityIdentifier("staleBadge")
    }
}
