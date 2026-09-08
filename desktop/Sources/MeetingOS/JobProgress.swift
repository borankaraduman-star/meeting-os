import Foundation
struct JobProgress:Decodable {
    let stage:String;let current:Int;let total:Int;let source:String;let updated_at:Double
    var label:String {
        let names=["stopping_capture":"Kayıt kapanıyor; ses nihai işleme hazırlanıyor","assembling":"Ses parçaları birleştiriliyor","loading_models":"Yerel modeller hazırlanıyor","reading_audio":"Ses okunuyor","vad":"Konuşma aralıkları bulunuyor","diarizing":"Konuşmacılar ayrılıyor","transcribing":"Konuşma yazıya çevriliyor","identifying":"Ses kimlikleri eşleştiriliyor","complete":"Transkript tamamlandı"]
        let base=names[stage] ?? "İşleniyor"
        let channel=source=="mic" ? " · Mikrofon":source=="system" ? " · Sistem sesi":""
        return base+channel+(total>0 ? " · \(current)/\(total) bölüm":"")
    }
}
