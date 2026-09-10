import SwiftUI
import AppKit

/// Accent presets the user can pick in Ayarlar → Görünüm. Views re-render because the choice lives on the Model.
enum Accents {
    static let all:[(key:String,name:String,color:Color)]=[
        ("green","Yeşil",Color(red:0.20,green:0.68,blue:0.57)),
        ("blue","Mavi",Color(red:0.22,green:0.52,blue:0.86)),
        ("indigo","Lacivert",Color(red:0.38,green:0.42,blue:0.86)),
        ("orange","Turuncu",Color(red:0.88,green:0.52,blue:0.18)),
        ("rose","Gül",Color(red:0.84,green:0.33,blue:0.48)),
        ("graphite","Grafit",Color(red:0.45,green:0.48,blue:0.50))]
    static func color(_ key:String)->Color { all.first { $0.key==key }?.color ?? all[0].color }
}
enum MeetingStyle {
    /// Set from Model.accentKey; default green. A static read keeps the 18 call sites unchanged.
    static var accent=Accents.color(UserDefaults.standard.string(forKey:"accentKey") ?? "green")
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
    /// Work waiting behind a tab: open tasks of this meeting, items in the review queue.
    func badge(_ key:String)->Int? { key=="actions" ? model.openTaskCount : (key=="review" ? model.review.count : nil) }
    let tabs=[("transcript","Transkript","waveform"),("analysis","Özet","text.alignleft"),("actions","Görevlerim","checklist"),("review","Kontrol","checklist.checked"),("memory","Hafıza","sparkle.magnifyingglass")]
    var body:some View { HStack(spacing:5) { ForEach(Array(tabs.enumerated()),id:\.element.0) { index,tab in let (key,title,icon)=tab; Button { model.tab=key } label:{ HStack(spacing:7) { Image(systemName:icon);Text(title).fontWeight(model.tab==key ? .semibold:.medium); if key=="analysis", model.summaryStale { Circle().fill(Color.orange).frame(width:6,height:6).accessibilityIdentifier("staleDot-analysis") }; if let n=badge(key), n>0 { Text("\(n)").font(.caption2.weight(.semibold)).monospacedDigit().padding(.horizontal,6).padding(.vertical,1).background(MeetingStyle.accent.opacity(0.14),in:Capsule()).foregroundStyle(MeetingStyle.accent).accessibilityIdentifier("badge-\(key)") } }.font(.callout).frame(maxWidth:.infinity).padding(.vertical,10).contentShape(Rectangle()) }.buttonStyle(.plain).foregroundStyle(model.tab==key ? Color.primary:Color.secondary).background(model.tab==key ? MeetingStyle.surface:Color.clear,in:RoundedRectangle(cornerRadius:10)).overlay(alignment:.bottom) { if model.tab==key { Capsule().fill(MeetingStyle.accent).frame(width:24,height:2).offset(y:3) } }.accessibilityIdentifier("tab-\(key)").accessibilityLabel(title).accessibilityAddTraits(model.tab==key ? .isSelected:[]).help("\(title) (⌘\(index+1))") } }.padding(5).background(.primary.opacity(0.035),in:RoundedRectangle(cornerRadius:14)).accessibilityElement(children:.contain).accessibilityLabel("Toplantı görünümleri") }
}
struct MeetingLibraryRow:View {
    let meeting:Meeting
    var body:some View { VStack(alignment:.leading,spacing:8) { Text(meeting.title).font(.system(size:13,weight:.semibold)).lineLimit(2);HStack(spacing:5) { Circle().fill(meeting.status=="complete" && meeting.segments==0 ? Color.secondary : MeetingStyle.statusColor(meeting.displayStatus)).frame(width:5,height:5);Text(meeting.sidebarDetail);Spacer();Text(MeetingDates.label(meeting.created)).monospacedDigit() }.font(.system(size:10)).foregroundStyle(.secondary) }.padding(.vertical,9) }
}

struct TaskStatusBadge:View {
    let state:String
    var label:String { switch state { case "done":return "Tamamlandı";case "dismissed":return "Kaldırıldı";case "in_progress":return "Devam ediyor";default:return "Açık" } }
    var icon:String { switch state { case "done":return "checkmark.circle.fill";case "dismissed":return "minus.circle";case "in_progress":return "clock";default:return "circle" } }
    var color:Color { switch state { case "done":return MeetingStyle.accent;case "in_progress":return MeetingStyle.accent.opacity(0.7);default:return .secondary } }
    var body:some View { Label(label,systemImage:icon).font(.caption.weight(.medium)).foregroundStyle(color).padding(.horizontal,9).padding(.vertical,5).background(color.opacity(0.09),in:Capsule()).fixedSize() }
}

/// Widths every content page and every notice agrees on. Boran, 10 Sep 2026: "boş tablerde gelen uyarı
/// ortalı değil; uygulamayı genişletince ya da küçültünce kötü görünüyor." The cause was that an empty
/// state is just another row of a leading-aligned VStack, so at 2300 pt it sat in the top-left corner and
/// its sentence ran the whole width of the screen.
enum NoticeMetrics {
    /// A notice's own text column. One sentence must never be wider than this, at any window size.
    static let textWidth:CGFloat=420
    /// The reading column every tab's content sits in, centred in the window.
    static let readingWidth:CGFloat=820
    /// A notice that shares a scrolling page with other content still gets a block of its own.
    static let inlineHeight:CGFloat=220
}

/// The one shape every empty state and page-level notice takes: icon, title, one detail line, and at most
/// a couple of buttons — centred on both axes inside whatever space it is given, text capped and centred.
struct CenteredNotice<Actions:View>:View {
    let icon:String
    let title:String
    let detail:String
    @ViewBuilder var actions:()->Actions
    init(icon:String,title:String,detail:String,@ViewBuilder actions:@escaping ()->Actions={ EmptyView() }) {
        self.icon=icon;self.title=title;self.detail=detail;self.actions=actions
    }
    var body:some View {
        VStack(spacing:10) {
            Image(systemName:icon).font(.system(size:34,weight:.regular)).foregroundStyle(.secondary).accessibilityHidden(true)
            Text(title).font(.headline).multilineTextAlignment(.center).fixedSize(horizontal:false,vertical:true)
            Text(detail).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).fixedSize(horizontal:false,vertical:true)
            // Bare, not wrapped in an HStack: a notice with no button (most of them) must not pay for a
            // zero-height row's spacing, which would push the whole thing off centre by a few points.
            actions()
        }
        .frame(maxWidth:NoticeMetrics.textWidth)
        .padding(24)
        .accessibilityElement(children:.contain)
        .accessibilityLabel(title)
    }
}

extension View {
    /// A notice that owns the whole tab: centred horizontally and vertically in the content area.
    /// Only ever applied outside a ScrollView — a scroll view proposes an unbounded height, so
    /// `maxHeight:.infinity` inside one collapses to the notice's own height and centres nothing.
    func noticeArea()->some View { frame(maxWidth:.infinity,maxHeight:.infinity,alignment:.center) }
    /// A notice on a page that still has other content (a header, a card, a filter): centred across the
    /// page with a block of height of its own so it does not cling to the row above it.
    func inlineNoticeArea()->some View { frame(maxWidth:.infinity,minHeight:NoticeMetrics.inlineHeight,alignment:.center) }
    /// One reading column per tab: capped, centred in the window, its own content still left-aligned.
    /// Two frames, not one — the inner cap is what wraps the text, the outer `.infinity` is what centres it.
    func readingColumn(_ width:CGFloat=NoticeMetrics.readingWidth)->some View {
        frame(maxWidth:width,alignment:.leading).frame(maxWidth:.infinity,alignment:.center)
    }
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
        case "pending_finalization":return "Canlı kayıt sona erdi. Kaydedilen sesi yazıya dönüştürmek için “Bulutta yazıya çevir” (bu Mac’te model yüklemez) veya “Yerel modelle tamamla” düğmesini kullanın."
        case "capture_unknown":return "Bu kaydın çalışan bir işleme ait olup olmadığı doğrulanamadı."
        case "capturing","processing","provisional":return "Bu toplantı henüz nihai değil. Kullanılabilir bölümler geldikçe burada görünür."
        case "failed","incomplete":return "İşlem durumunu ve varsa hata bilgisini kontrol edin. Kayıt arşivi varsa üstteki kurtarma seçeneğini kullanabilirsiniz."
        case "canceled":return "Bu toplantı için şu anda gösterilecek bir konuşma bölümü yok. Yeni bir kayıt başlatabilir ya da kenar çubuğundaki ⋯ menüsünden ses dosyası açabilirsiniz."
        case "complete":return "Bu toplantının metni şu anda boş görünüyor. Yenileyerek tekrar kontrol edebilirsiniz."
        default:return "Bir toplantı seçin, ⌃⌥R ile kayıt başlatın veya bir ses dosyası açın."
        }
    }
    var body:some View {
        CenteredNotice(icon:model.rows.isEmpty ? "waveform":"magnifyingglass",title:title,detail:detail) {
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
    @ObservedObject var jobs:JobState
    init(model:Model) { self.model=model; _jobs=ObservedObject(wrappedValue:model.jobs) }
    var body:some View {
        VStack(alignment:.leading,spacing:7) {
            HStack(spacing:7) {
                if model.recording { Image(systemName:"record.circle.fill").foregroundStyle(.red) }
                else if model.busy { ProgressView().controlSize(.mini) }
                else if !model.error.isEmpty { Image(systemName:"exclamationmark.triangle").foregroundStyle(.orange) }
                else { Image(systemName:"info.circle").foregroundStyle(.secondary) }
                Text(model.recording ? "Kayıt oturumu":model.busy ? "İşlem sürüyor":model.error.isEmpty ? "Son durum":"Sorun var").font(.caption.weight(.semibold))
            }
            if model.busy && !jobs.jobProgress.isEmpty { Text(jobs.jobProgress).font(.caption.weight(.medium)).fixedSize(horizontal:false,vertical:true) }
            if !model.microphoneHint.isEmpty { Label(model.microphoneHint,systemImage:"mic.slash").font(.caption).foregroundStyle(.orange).fixedSize(horizontal:false,vertical:true) }
            Text(model.activity).font(.caption).foregroundStyle(.secondary).lineLimit(4).fixedSize(horizontal:false,vertical:true)
                .help("Sistem kanalı bu Mac’in ses çıkışını kaydeder. Başka bir cihazdan çalınan ses mikrofondan alınır. Sinyal ölçümü, konuşma algılandığı anlamına gelmez. Eksik canlı metin, kayıt sonunda tam ses üzerinden yeniden işlenmelidir.")
            if model.canUndoNaming { Button("Geri al (⌘Z)") { Task { await model.undoNaming() } }.controlSize(.mini).disabled(model.busy).help("Son adlandırmayı geri alır; öğrenilen ses örneği de silinir").accessibilityIdentifier("undoNamingButton") }
        }.padding(12).frame(maxWidth:.infinity,alignment:.leading).meetingCard()
    }
}
