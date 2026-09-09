import SwiftUI

/// Who spoke how long in one meeting, from the final transcript rows. Echo rows and the fillers-only back-channels
/// still count as speech; only microphone echo of the speakers is excluded so the host is not double-counted.
struct TalkShare: Identifiable, Equatable {
    let id:String; let seconds:Double
    var share:Double
    static func compute(_ rows:[Row])->[TalkShare] {
        var totals:[String:Double]=[:]
        for r in rows where !r.flags.contains("possible_echo") && r.end>r.start {
            totals[r.label, default:0]+=r.end-r.start
        }
        let sum=totals.values.reduce(0,+)
        guard sum>0 else { return [] }
        return totals.map { TalkShare(id:$0.key,seconds:$0.value,share:$0.value/sum) }.sorted { $0.seconds>$1.seconds }
    }
    var minutes:String { seconds>=60 ? String(format:"%d dk",Int(seconds/60)) : String(format:"%d sn",Int(seconds)) }
}

struct TalkShareView:View {
    let shares:[TalkShare]
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
            HStack { Text("Konuşma payı").font(.headline);Spacer();Text("\(shares.count) konuşmacı").font(.caption).foregroundStyle(.secondary) }
            GeometryReader { geo in
                HStack(spacing:2) {
                    ForEach(Array(shares.prefix(8).enumerated()),id:\.element.id) { i,s in
                        RoundedRectangle(cornerRadius:3).fill(MeetingStyle.accent.opacity(1.0-Double(i)*0.11)).frame(width:max(3,geo.size.width*s.share-2))
                    }
                }
            }.frame(height:10)
            VStack(alignment:.leading,spacing:5) {
                ForEach(Array(shares.prefix(8).enumerated()),id:\.element.id) { i,s in
                    HStack(spacing:8) {
                        Circle().fill(MeetingStyle.accent.opacity(1.0-Double(i)*0.11)).frame(width:8,height:8)
                        Text(s.id).font(.callout)
                        Spacer()
                        Text(s.minutes).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        Text(String(format:"%%%d",Int((s.share*100).rounded()))).font(.caption.monospacedDigit().weight(.semibold)).frame(width:38,alignment:.trailing)
                    }.accessibilityElement(children:.combine)
                }
                if shares.count>8 { Text("+\(shares.count-8) kısa konuşmacı").font(.caption).foregroundStyle(.secondary) }
            }
        }.padding(18).meetingCard().accessibilityIdentifier("talkShare")
    }
}
