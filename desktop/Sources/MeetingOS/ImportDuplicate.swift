import Foundation

/// Result of the `check_duplicate` bridge action: an earlier meeting made from the very same audio file.
struct ImportDuplicate:Equatable {
    let meeting:String; let title:String; let model:String
    static func parse(_ response:[String:Any])->ImportDuplicate? {
        guard let d=response["duplicate"] as? [String:Any], let id=d["meeting"] as? String, !id.isEmpty else { return nil }
        return ImportDuplicate(meeting:id,title:d["title"] as? String ?? "",model:d["model"] as? String ?? "")
    }
    var notice:String {
        let name=title.isEmpty ? "Adsız toplantı" : title
        return model.isEmpty ? "Bu dosyayı zaten işlemiştin: “\(name)”" : "Bu dosyayı zaten işlemiştin: “\(name)” · \(model)"
    }
    static func uploadLabel(duplicate:Bool)->String { duplicate ? "Yine de gönder" : "Yükle ve yazıya çevir" }
}
