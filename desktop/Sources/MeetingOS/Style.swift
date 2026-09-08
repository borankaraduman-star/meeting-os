import SwiftUI
import AppKit

enum MeetingStyle {
    static let accent=Color(red:0.20,green:0.68,blue:0.57)
    static let surface=Color(nsColor:.controlBackgroundColor)
    static let canvas=Color(nsColor:.windowBackgroundColor)
    static func statusColor(_ status:String)->Color {
        switch status { case "complete":return accent;case "failed":return .red;case "processing","provisional","incomplete":return .orange;default:return .secondary }
    }
}
struct MeetingCard:ViewModifier {
    func body(content:Content)->some View {
        content.background(MeetingStyle.surface,in:RoundedRectangle(cornerRadius:16))
            .overlay(RoundedRectangle(cornerRadius:16).strokeBorder(.primary.opacity(0.055),lineWidth:1))
    }
}
extension View { func meetingCard()->some View { modifier(MeetingCard()) } }
struct SmallMetric:View {
    let value:String;let label:String;let icon:String
    var body:some View { HStack(spacing:10) { Image(systemName:icon).foregroundStyle(MeetingStyle.accent).font(.system(size:17,weight:.medium)).frame(width:32,height:32).background(MeetingStyle.accent.opacity(0.10),in:RoundedRectangle(cornerRadius:9));VStack(alignment:.leading,spacing:2) { Text(value).font(.system(.headline,design:.rounded));Text(label).font(.caption).foregroundStyle(.secondary) };Spacer(minLength:0) }.padding(13).frame(maxWidth:.infinity).meetingCard() }
}
struct MeetingNavigation:View {
    @ObservedObject var model:Model
    let tabs=[("transcript","Transkript","waveform"),("analysis","Özet","text.alignleft"),("actions","Görevlerim","checklist"),("memory","Hafıza","sparkle.magnifyingglass")]
    var body:some View { HStack(spacing:5) { ForEach(tabs,id:\.0) { key,title,icon in Button { model.tab=key } label:{ HStack(spacing:7) { Image(systemName:icon);Text(title).fontWeight(model.tab==key ? .semibold:.medium) }.font(.callout).frame(maxWidth:.infinity).padding(.vertical,10).contentShape(Rectangle()) }.buttonStyle(.plain).foregroundStyle(model.tab==key ? Color.primary:Color.secondary).background(model.tab==key ? MeetingStyle.surface:Color.clear,in:RoundedRectangle(cornerRadius:10)).overlay(alignment:.bottom) { if model.tab==key { Capsule().fill(MeetingStyle.accent).frame(width:24,height:2).offset(y:3) } }.accessibilityAddTraits(model.tab==key ? .isSelected:[]) } }.padding(5).background(.primary.opacity(0.035),in:RoundedRectangle(cornerRadius:14)).accessibilityElement(children:.contain).accessibilityLabel("Toplantı görünümleri") }
}
struct MeetingLibraryRow:View {
    let meeting:Meeting
    var body:some View { VStack(alignment:.leading,spacing:8) { Text(meeting.title).font(.system(size:13,weight:.semibold)).lineLimit(2);HStack(spacing:5) { Circle().fill(MeetingStyle.statusColor(meeting.status)).frame(width:5,height:5);Text(statusLabel(meeting.status));Spacer();Text(String(meeting.created.prefix(10))).monospacedDigit() }.font(.system(size:10)).foregroundStyle(.secondary) }.padding(.vertical,9) }
}

struct TaskStatusBadge:View {
    let state:String
    var label:String { switch state { case "done":return "Tamamlandı";case "dismissed":return "Kaldırıldı";case "in_progress":return "Devam ediyor";default:return "Açık" } }
    var icon:String { switch state { case "done":return "checkmark.circle.fill";case "dismissed":return "minus.circle";case "in_progress":return "clock";default:return "circle" } }
    var color:Color { switch state { case "done":return MeetingStyle.accent;case "in_progress":return .blue;default:return .secondary } }
    var body:some View { Label(label,systemImage:icon).font(.caption.weight(.medium)).foregroundStyle(color).padding(.horizontal,9).padding(.vertical,5).background(color.opacity(0.09),in:Capsule()).fixedSize() }
}
