import SwiftUI
import AppKit
import Security

/// API keys never enter CLI arguments, job logs, SQLite or transcript requests.
enum OpenRouterCredential {
    static let service="local.boran.meeting-os.openrouter"
    static var query:[String:Any] { [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:service,kSecAttrAccount as String:"openrouter"] }
    static func save(_ key:String) throws {
        let value=key.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !value.isEmpty,!value.contains(where:{$0.isWhitespace}) else { throw failure("Geçerli bir OpenRouter API anahtarı girin.") }
        var attributes=query;attributes[kSecValueData as String]=Data(value.utf8)
        attributes[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        var status=SecItemAdd(attributes as CFDictionary,nil)
        if status==errSecDuplicateItem { status=SecItemUpdate(query as CFDictionary,[kSecValueData as String:Data(value.utf8)] as CFDictionary) }
        guard status==errSecSuccess else { throw failure("Anahtar macOS Anahtar Zinciri’ne kaydedilemedi (\(status)).") }
    }
    static func failure(_ message:String)->NSError { NSError(domain:"MeetingOS.OpenRouter",code:1,userInfo:[NSLocalizedDescriptionKey:message]) }
}

struct OpenRouterModelOption:Identifiable,Decodable {
    let id:String
    let name:String
    let pricing:String
}

struct OpenRouterImportView:View {
    @ObservedObject var model:Model
    @Environment(\.dismiss) private var dismiss
    @State private var models:[OpenRouterModelOption]=[]
    @State private var selectedModel="openai/gpt-transcribe"
    @State private var key=""
    @State private var path:URL?
    @State private var title=""
    @State private var consent=false
    @State private var message=""
    @State private var saving=false
    private var resumable:String? {
        guard let m=model.meeting,m.metadata["engine"] as? String=="openrouter",m.status != "complete",m.recoveryState != "active" else { return nil }
        return m.id
    }
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            Text("OpenRouter · Ses transkripsiyonu").font(.title2.bold())
            Text("Türkçe ses → transkript. Konuşmacı ayrımı ve ses profilleri Mac’te işlenir. Özet, karar ve görevleri işlem bitince Özet sekmesinden bu Mac’te hazırlayabilirsiniz.").foregroundStyle(.secondary)
            if models.isEmpty { Text("Model listesi yükleniyor…").font(.caption) }
            else {
                Picker("Transkripsiyon modeli",selection:$selectedModel) {
                    ForEach(models) { option in Text(option.name).tag(option.id) }
                }.accessibilityIdentifier("openRouterModelPicker")
            }
            HStack {
                Text(models.first(where:{$0.id==selectedModel})?.pricing ?? "").font(.caption)
                Spacer()
                if let url=URL(string:"https://openrouter.ai/"+selectedModel) { Link("Model ve fiyat",destination:url).font(.caption) }
            }
            HStack {
                SecureField("OpenRouter API anahtarı",text:$key)
                Button("Anahtarı kaydet") {
                    saving=true
                    do { try OpenRouterCredential.save(key);key="";message="Anahtar Anahtar Zinciri’ne kaydedildi." }
                    catch { message=error.localizedDescription }
                    saving=false
                }.disabled(key.isEmpty || saving)
            }
            Text("Anahtar daha önce kaydedildiyse yeniden girmeniz gerekmez. macOS ilk kullanımda Anahtar Zinciri erişimi isteyebilir.").font(.caption).foregroundStyle(.secondary)
            TextField("Toplantı başlığı",text:$title)
            HStack {
                Button("Ses dosyası seç") {
                    let panel=NSOpenPanel();panel.canChooseDirectories=false;panel.allowsMultipleSelection=false
                    if panel.runModal() == .OK,let url=panel.url { path=url;title=url.deletingPathExtension().lastPathComponent }
                }
                Text(path?.lastPathComponent ?? "Dosya seçilmedi").lineLimit(2).foregroundStyle(.secondary)
            }
            Text("Ücretli API. Ücret seçilen model, sağlayıcı ve kullanıma bağlıdır. ChatGPT aboneliği API kredisi değildir.").font(.callout)
            Text("Konuşmacı etiketleri tahminidir; isimleri düzeltebilirsiniz. Zamanlar konuşma parçası sınırlarıdır. Özel kelime ipuçları bu bağlantıda doğrulanmadığından gönderilmez.").font(.caption).foregroundStyle(.secondary)
            Toggle("Seçtiğim sesin OpenRouter üzerinden seçili modelin sağlayıcısına gönderilmesini ve API ücretini kabul ediyorum.",isOn:$consent)
            if let original=model.meeting?.metadata["model"] as? String,resumable != nil {
                Text("Seçili işlemin modeli: \(models.first(where:{$0.id==original})?.name ?? original). Devam etmek için bu modeli seçin; farklı modelle denemek yeni toplantı oluşturur.").font(.caption).foregroundStyle(.secondary)
            }
            if !message.isEmpty { Text(message).font(.callout).textSelection(.enabled) }
            HStack {
                Button("Vazgeç") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                if let mid=resumable { Button("Seçili işlemi sürdür") { start(resume:mid) }.disabled(!consent || model.busy || selectedModel != model.meeting?.metadata["model"] as? String) }
                Button("Yükle ve yazıya çevir") { start(resume:nil) }.buttonStyle(.borderedProminent)
                    .disabled(!consent || models.isEmpty || path==nil || title.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || model.busy)
            }
        }.padding(24).frame(width:640)
        .task {
            do {
                let response=try await model.request(["action":"openrouter_models"])
                let data=try JSONSerialization.data(withJSONObject:response["models"] ?? [])
                models=try JSONDecoder().decode([OpenRouterModelOption].self,from:data)
                guard models.contains(where:{$0.id==selectedModel}) else { throw OpenRouterCredential.failure("Varsayılan model listede yok.") }
            } catch { message=error.localizedDescription;models=[] }
        }
    }
    private func start(resume:String?) {
        guard consent,!model.busy,models.contains(where:{$0.id==selectedModel}) else { return }
        let result=model.dataDir.appendingPathComponent("openrouter-\(UUID().uuidString).json")
        var args=["openrouter-import","--allow-upload","--model",selectedModel,"--title",title.isEmpty ? "OpenRouter toplantısı":title,"--output",result.path]
        if let resume { args += ["--resume",resume] } else if let path { args.append(path.path) } else { return }
        model.activity="Konuşmacılar yerelde ayrılıyor; seçilen transkripsiyon modeli hazırlanıyor…"
        model.launch(args) { [weak model] ok in
            guard let model else { return }
            if ok,let mid=model.resultMeeting(result) {
                model.selected=mid;model.tab="transcript";model.analyzeAutomatically(mid)
            } else { model.activity="İşlem tamamlanamadı · Kaydedilen parçalar korunuyor. OpenRouter penceresinden sürdürebilirsiniz." }
        }
        dismiss()
    }
}
