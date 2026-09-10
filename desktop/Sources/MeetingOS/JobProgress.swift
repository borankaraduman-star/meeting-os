import Foundation
struct JobProgress:Decodable {
    let stage:String;let current:Int;let total:Int;let source:String;let updated_at:Double
    var label:String {
        let names=["stopping_capture":"Kayıt kapanıyor; ses nihai işleme hazırlanıyor","assembling":"Ses parçaları birleştiriliyor","loading_models":"Yerel modeller hazırlanıyor","reading_audio":"Ses okunuyor","vad":"Konuşma aralıkları bulunuyor","diarizing":"Konuşmacılar ayrılıyor","transcribing":"Konuşma yazıya çevriliyor","identifying":"Ses kimlikleri eşleştiriliyor","complete":"Transkript tamamlandı"]
        let base=names[stage] ?? "İşleniyor"
        let channel=source=="mic" ? " · Mikrofon":source=="system" ? " · Sistem sesi":""
        return base+channel+(total>0 ? " · \(current)/\(total) bölüm":"")
    }
    /// "≈4 dk kaldı", from the rate this job has actually managed so far. One finished piece is not a rate
    /// (the first one carries model loading and the upload warm-up), so nothing is claimed before the second.
    /// A total that is unknown, already reached, or an estimate over an hour says nothing at all — a wrong
    /// number here is worse than no number, because people leave the Mac on the strength of it.
    func remaining(elapsed:TimeInterval)->String? {
        guard total>0, current>=2, current<total, elapsed>0 else { return nil }
        let minutes=Int((elapsed/Double(current)*Double(total-current)/60).rounded(.up))
        guard minutes>0, minutes<=60 else { return nil }
        return "≈\(minutes) dk kaldı"
    }
    /// The status line: what is happening, then how long is left when that can be said honestly.
    func line(elapsed:TimeInterval)->String { label+(remaining(elapsed:elapsed).map { " · "+$0 } ?? "") }
}
