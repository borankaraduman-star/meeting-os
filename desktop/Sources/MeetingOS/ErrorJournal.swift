import Foundation

/// One line of the local error journal as the bridge hands it over. Display only: every field was redacted
/// and bounded by the Python side before it reached disk, so nothing here has to be trimmed again.
struct ErrorEntry:Identifiable,Equatable {
    let id:String; let time:String; let kind:String; let message:String
    init(time:String,kind:String,message:String,index:Int=0) {
        self.time=time; self.kind=kind; self.message=message; self.id="\(index)·\(time)·\(kind)"
    }
    init(_ raw:[String:Any],index:Int) {
        self.init(time:raw["time"] as? String ?? "",kind:raw["kind"] as? String ?? "ui",message:raw["message"] as? String ?? "",index:index)
    }
    var kindLabel:String { ErrorJournal.label(kind) }
    var timeLabel:String { ErrorJournal.moment(time) }
    var isCrash:Bool { kind=="crash" }
}

/// Turkish labels and one-line summaries for the Hatalar card. Pure formatting, no state.
enum ErrorJournal {
    static let labels=["ui":"Arayüz","job":"İşlem","cloud":"Bulut","capture":"Kayıt","update":"Güncelleme","crash":"Çökme"]
    static func label(_ kind:String)->String { labels[kind] ?? kind }
    private static let fractional:ISO8601DateFormatter = { let f=ISO8601DateFormatter(); f.formatOptions=[.withInternetDateTime,.withFractionalSeconds]; return f }()
    private static let plain:ISO8601DateFormatter = { let f=ISO8601DateFormatter(); f.formatOptions=[.withInternetDateTime]; return f }()
    private static let shown:DateFormatter = { let f=DateFormatter(); f.locale=Locale(identifier:"tr_TR"); f.dateFormat="d MMM HH:mm"; return f }()
    static func date(_ iso:String)->Date? { fractional.date(from:iso) ?? plain.date(from:iso) }
    /// A stamp the journal wrote; an unparseable one is shown as it stands rather than hidden.
    static func moment(_ iso:String)->String { date(iso).map { shown.string(from:$0) } ?? String(iso.prefix(16)) }
    /// The card's one-line header. A quiet day says so: an empty card looks broken, not calm.
    static func headline(counts:[String:Int],crashes:Int)->String {
        let total=counts.values.reduce(0,+)
        guard total>0 else { return "Son 24 saatte hata yok" }
        return crashes>0 ? "Son 24 saatte \(total) kayıt · \(crashes) çökme" : "Son 24 saatte \(total) kayıt"
    }
}

/// Which error texts this app session has already sent to the journal. The Python side dedupes by ten
/// minutes as well; this stops the bridge call itself, because a banner is re-set by every two-second poll
/// and a failing poll would otherwise spawn a bridge process per tick.
struct ErrorReportThrottle {
    private var sent:[String:Date]=[:]
    private let window:TimeInterval
    init(window:TimeInterval=600) { self.window=window }
    /// Keyed on the message alone, never on the kind: a job failure reports itself as `job` and then sets the
    /// banner, and the banner's `ui` echo of the same text must not become a second line.
    mutating func admit(_ message:String,now:Date = Date())->Bool {
        sent=sent.filter { now.timeIntervalSince($0.value) < window }
        if let last=sent[message], now.timeIntervalSince(last) < window { return false }
        sent[message]=now; return true
    }
}
