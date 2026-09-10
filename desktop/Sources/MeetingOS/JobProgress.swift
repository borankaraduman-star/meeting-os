import Foundation
struct JobProgress:Decodable {
    let stage:String;let current:Int;let total:Int;let source:String;let updated_at:Double
    /// Seconds of audio already sent and seconds in the meeting, when the Python side reports them. Pieces are
    /// not the same length — a 20-minute tail piece and a 30-second one both count as "1/8" — so seconds give a
    /// straighter estimate than the piece counter and are preferred whenever both are present.
    let uploaded_seconds:Double?
    let total_seconds:Double?
    var label:String {
        let names=["stopping_capture":"Kayıt kapanıyor; ses nihai işleme hazırlanıyor","assembling":"Ses parçaları birleştiriliyor","loading_models":"Yerel modeller hazırlanıyor","reading_audio":"Ses okunuyor","vad":"Konuşma aralıkları bulunuyor","diarizing":"Konuşmacılar ayrılıyor","transcribing":"Konuşma yazıya çevriliyor","identifying":"Ses kimlikleri eşleştiriliyor","complete":"Transkript tamamlandı"]
        let base=names[stage] ?? "İşleniyor"
        let channel=source=="mic" ? " · Mikrofon":source=="system" ? " · Sistem sesi":""
        return base+channel+(total>0 ? " · \(current)/\(total) bölüm":"")
    }
    /// "≈4 dk kaldı", from the rate this job has actually managed so far. One finished piece is not a rate
    /// (the first one carries model loading and the upload warm-up), so nothing is claimed before the second.
    /// A total that is unknown, already reached, or an estimate past the cap says nothing at all — a wrong
    /// number here is worse than no number, because people leave the Mac on the strength of it.
    ///
    /// The cap is an hour for a job the user is waiting on. A low-priority job (the idle retry queue, or one
    /// throttled under a live meeting) is deliberately slow and legitimately takes two: capping it at an hour
    /// meant the longest jobs — exactly the ones worth an estimate — silently showed none.
    func remaining(elapsed:TimeInterval,lowPriority:Bool=false)->String? {
        guard elapsed>0 else { return nil }
        let cap=lowPriority ? 120 : 60
        // Whichever unit is available, the warm-up rule holds: when pieces are reported at all, the first one
        // is not a rate, and no estimate is offered until the second has landed.
        guard total<=0 || current>=2 else { return nil }
        let minutes:Int
        if let done=uploaded_seconds, let all=total_seconds, done>0, all>done, done.isFinite, all.isFinite {
            minutes=Int((elapsed/done*(all-done)/60).rounded(.up))
        } else {
            guard total>0, current>=2, current<total else { return nil }
            minutes=Int((elapsed/Double(current)*Double(total-current)/60).rounded(.up))
        }
        guard minutes>0, minutes<=cap else { return nil }
        return "≈\(minutes) dk kaldı"
    }
    /// The status line: what is happening, then how long is left when that can be said honestly.
    func line(elapsed:TimeInterval,lowPriority:Bool=false)->String { label+(remaining(elapsed:elapsed,lowPriority:lowPriority).map { " · "+$0 } ?? "") }
}
