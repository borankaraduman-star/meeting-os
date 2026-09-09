import SwiftUI
import AppKit

enum MeetingStyle {
    static let accent=Color(red:0.20,green:0.68,blue:0.57)
    static let surface=Color(nsColor:.controlBackgroundColor)
    static let canvas=Color(nsColor:.windowBackgroundColor)
    static let sidebarWidth:CGFloat=264
    static let minDetailWidth:CGFloat=640
    static let minWindowWidth:CGFloat=900
    static let minWindowHeight:CGFloat=620
    static func statusColor(_ status:String)->Color {
        switch status { case "complete":return accent;case "failed","not_started","capturing":return .red;case "processing","provisional","incomplete","pending_finalization","capture_unknown":return .orange;default:return .secondary }
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
    var body:some View { HStack(spacing:5) { ForEach(tabs,id:\.0) { key,title,icon in Button { model.tab=key } label:{ HStack(spacing:7) { Image(systemName:icon);Text(title).fontWeight(model.tab==key ? .semibold:.medium) }.font(.callout).frame(maxWidth:.infinity).padding(.vertical,10).contentShape(Rectangle()) }.buttonStyle(.plain).foregroundStyle(model.tab==key ? Color.primary:Color.secondary).background(model.tab==key ? MeetingStyle.surface:Color.clear,in:RoundedRectangle(cornerRadius:10)).overlay(alignment:.bottom) { if model.tab==key { Capsule().fill(MeetingStyle.accent).frame(width:24,height:2).offset(y:3) } }.accessibilityIdentifier("tab-\(key)").accessibilityLabel(title).accessibilityAddTraits(model.tab==key ? .isSelected:[]) } }.padding(5).background(.primary.opacity(0.035),in:RoundedRectangle(cornerRadius:14)).accessibilityElement(children:.contain).accessibilityLabel("Toplantı görünümleri") }
}
struct MeetingLibraryRow:View {
    let meeting:Meeting
    var body:some View { VStack(alignment:.leading,spacing:8) { Text(meeting.title).font(.system(size:13,weight:.semibold)).lineLimit(2);HStack(spacing:5) { Circle().fill(MeetingStyle.statusColor(meeting.displayStatus)).frame(width:5,height:5);Text(statusLabel(meeting.displayStatus));Spacer();Text(String(meeting.created.prefix(10))).monospacedDigit() }.font(.system(size:10)).foregroundStyle(.secondary) }.padding(.vertical,9) }
}

struct TaskStatusBadge:View {
    let state:String
    var label:String { switch state { case "done":return "Tamamlandı";case "dismissed":return "Kaldırıldı";case "in_progress":return "Devam ediyor";default:return "Açık" } }
    var icon:String { switch state { case "done":return "checkmark.circle.fill";case "dismissed":return "minus.circle";case "in_progress":return "clock";default:return "circle" } }
    var color:Color { switch state { case "done":return MeetingStyle.accent;case "in_progress":return .blue;default:return .secondary } }
    var body:some View { Label(label,systemImage:icon).font(.caption.weight(.medium)).foregroundStyle(color).padding(.horizontal,9).padding(.vertical,5).background(color.opacity(0.09),in:Capsule()).fixedSize() }
}

struct TranscriptEmptyView:View {
    @ObservedObject var model:Model
    var title:String {
        if !model.rows.isEmpty { return model.focusedSegment == nil ? "Eşleşen konuşma bulunamadı":"Kaynak bölümü görünmüyor" }
        switch model.meeting?.displayStatus {
        case "not_started":return "Kayıt başlayamadı"
        case "pending_finalization":return "Kayıt bitti · Son işlem bekliyor"
        case "capture_unknown":return "Kayıt durumu doğrulanamıyor"
        case "capturing","processing","provisional":return "Konuşma bölümleri bekleniyor"
        case "failed","incomplete":return "Transkript tamamlanamadı"
        case "canceled":return "Kayıt iptal edildi"
        case "complete":return "Gösterilecek konuşma bölümü yok"
        default:return "Dinlemeye hazır"
        }
    }
    var detail:String {
        if !model.rows.isEmpty { return "Başka bir kelime deneyin veya tüm konuşmayı gösterin." }
        switch model.meeting?.displayStatus {
        case "not_started":return "Bu denemede ses parçası alınmadı. macOS izinlerini kontrol edip Yeni kayıt düğmesiyle tekrar başlayın."
        case "pending_finalization":return "Canlı kayıt sona erdi. Kaydedilen sesi yazıya dönüştürmek için “OpenRouter ile yazıya çevir” (bu Mac’te model yüklemez) veya “Yerel modelle tamamla” düğmesini kullanın."
        case "capture_unknown":return "Bu kaydın çalışan bir işleme ait olup olmadığı doğrulanamadı."
        case "capturing","processing","provisional":return "Bu toplantı henüz nihai değil. Kullanılabilir bölümler geldikçe burada görünür."
        case "failed","incomplete":return "İşlem durumunu ve varsa hata bilgisini kontrol edin. Kayıt arşivi varsa üstteki kurtarma seçeneğini kullanabilirsiniz."
        case "canceled":return "Bu toplantı için şu anda gösterilecek bir konuşma bölümü yok. Yeni bir kayıt başlatabilir veya ses dosyası açabilirsiniz."
        case "complete":return "Bu toplantının metni şu anda boş görünüyor. Yenileyerek tekrar kontrol edebilirsiniz."
        default:return "Bir toplantı seçin, kayıt başlatın veya ses dosyası açın."
        }
    }
    var body:some View {
        ContentUnavailableView {
            Label(title,systemImage:model.rows.isEmpty ? "waveform":"magnifyingglass")
        } description: { Text(detail) } actions: {
            if !model.rows.isEmpty {
                Button("Tüm konuşmayı göster") { model.search="";model.focusedSegment=nil;model.pendingEvidence=nil }
            } else if model.selected != nil {
                Button("Yenile") { Task { await model.refresh() } }
            }
        }
    }
}

struct ApplicationActivityView:View {
    @ObservedObject var model:Model
    var body:some View {
        VStack(alignment:.leading,spacing:7) {
            HStack(spacing:7) {
                if model.recording { Image(systemName:"record.circle.fill").foregroundStyle(.red) }
                else if model.busy { ProgressView().controlSize(.mini) }
                else if !model.error.isEmpty { Image(systemName:"exclamationmark.triangle").foregroundStyle(.orange) }
                else { Image(systemName:"info.circle").foregroundStyle(.secondary) }
                Text(model.recording ? "Kayıt oturumu":model.busy ? "İşlem sürüyor":model.error.isEmpty ? "Son durum":"Kontrol gerekiyor").font(.caption.weight(.semibold))
            }
            if model.busy && !model.jobProgress.isEmpty { Text(model.jobProgress).font(.caption.weight(.medium)).fixedSize(horizontal:false,vertical:true) }
            if !model.microphoneHint.isEmpty { Label(model.microphoneHint,systemImage:"mic.slash").font(.caption).foregroundStyle(.orange).fixedSize(horizontal:false,vertical:true) }
            Text(model.activity).font(.caption).foregroundStyle(.secondary).lineLimit(4).fixedSize(horizontal:false,vertical:true)
                .help("Sistem kanalı bu Mac’in ses çıkışını kaydeder. Başka bir cihazdan çalınan ses mikrofondan alınır. Sinyal ölçümü, konuşma algılandığı anlamına gelmez. Eksik canlı metin, kayıt sonunda tam ses üzerinden yeniden işlenmelidir.")
        }.padding(12).frame(maxWidth:.infinity,alignment:.leading).meetingCard()
    }
}
