import SwiftUI
import AppKit
import Security

/// API keys never enter CLI arguments, job logs, SQLite or transcript requests.
enum OpenRouterCredential {
    static let service="local.boran.meeting-os.openrouter"
    static var query:[String:Any] { [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:service,kSecAttrAccount as String:"openrouter"] }
    /// Every rebuild/update changes the app's code signature, and macOS then asks "Meeting OS wants to use your keychain"
    /// again even after "Her Zaman İzin Ver". So the key is read from the Keychain once and cached in a 0600 file the app
    /// owns (like gh/aws do); later launches and every job read the file and never touch the Keychain.
    static let cacheURL=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/MeetingOS/openrouter.key")
    static func cached()->String? {
        guard let data=try? Data(contentsOf:cacheURL), let s=String(data:data,encoding:.utf8) else { return nil }
        let v=s.trimmingCharacters(in:.whitespacesAndNewlines); return v.isEmpty ? nil : v
    }
    static func cache(_ value:String) {
        let dir=cacheURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        try? Data((value+"\n").utf8).write(to:cacheURL,options:.atomic)
        try? FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:cacheURL.path)
    }
    static func read()->String? {
        if let v=cached() { return v }
        var q=query; q[kSecReturnData as String]=true; q[kSecMatchLimit as String]=kSecMatchLimitOne
        var item:CFTypeRef?; guard SecItemCopyMatching(q as CFDictionary,&item)==errSecSuccess, let data=item as? Data, let s=String(data:data,encoding:.utf8) else { return nil }
        let v=s.trimmingCharacters(in:.whitespacesAndNewlines); if v.isEmpty { return nil }
        cache(v); return v   // one Keychain dialog per Mac, not one per update
    }
    static func environment()->[String:String] { read().map { ["OPENROUTER_API_KEY":$0] } ?? [:] }
    static func save(_ key:String) throws {
        let value=key.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !value.isEmpty,!value.contains(where:{$0.isWhitespace}) else { throw failure("Geçerli bir OpenRouter API anahtarı girin.") }
        cache(value)   // the file is what runs the product; the Keychain copy is the backup that survives a data-folder wipe
        var attributes=query;attributes[kSecValueData as String]=Data(value.utf8)
        attributes[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        var status=SecItemAdd(attributes as CFDictionary,nil)
        if status==errSecDuplicateItem { status=SecItemUpdate(query as CFDictionary,[kSecValueData as String:Data(value.utf8)] as CFDictionary) }
        guard status==errSecSuccess else { throw failure("Anahtar macOS Anahtar Zinciri’ne kaydedilemedi (\(status)).") }
    }
    static func forget() { try? FileManager.default.removeItem(at:cacheURL); SecItemDelete(query as CFDictionary) }
    static func failure(_ message:String)->NSError { NSError(domain:"MeetingOS.OpenRouter",code:1,userInfo:[NSLocalizedDescriptionKey:message]) }
}

struct OpenRouterModelOption:Identifiable,Decodable {
    let id:String
    let name:String
    let pricing:String
    let diarization:Bool
}

struct OpenRouterImportView:View {
    @ObservedObject var model:Model
    @Environment(\.dismiss) private var dismiss
    @State private var models:[OpenRouterModelOption]=[]
    @State private var selectedModel=CloudTranscription.defaultModel
    @State private var key=""
    @State private var path:URL?
    @State private var title=""
    @State private var consent=false
    @State private var message=""
    @State private var saving=false
    @State private var duplicate:ImportDuplicate?
    @State private var digest:String?          // SHA-256 of the picked file, registered on the new meeting after a successful import
    @State private var fileSize:Int?
    private var resumable:String? {
        guard let m=model.meeting,m.metadata["engine"] as? String=="openrouter",m.status != "complete",m.recoveryState != "active" else { return nil }
        return m.id
    }
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            Text("OpenRouter · Ses dosyasını yazıya çevir").font(.title2.bold())
            Text("Türkçe ses → transkript. Bu yolda bu Mac’te model yüklenmez; konuşmacı ayrımı seçilen modelden gelir (ayrım sunmayan modellerde konuşmacılar ayrılmaz). Özet, karar ve görevleri işlem bitince Özet sekmesinden bu Mac’te hazırlayabilirsiniz.").foregroundStyle(.secondary)
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
                    if panel.runModal() == .OK,let url=panel.url { path=url;title=url.deletingPathExtension().lastPathComponent;Task { await checkDuplicate(url) } }
                }
                Text(path?.lastPathComponent ?? "Dosya seçilmedi").lineLimit(2).foregroundStyle(.secondary)
            }
            if let duplicate {
                HStack(alignment:.top,spacing:10) {
                    Image(systemName:"doc.on.doc.fill").foregroundStyle(.orange)
                    VStack(alignment:.leading,spacing:4) {
                        Text(duplicate.notice).font(.callout.weight(.semibold))
                        Text("Aynı dosyayı yeniden göndermek yeni bir toplantı oluşturur ve API ücreti alınır.").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Mevcut toplantıyı aç") { model.selected=duplicate.meeting;model.tab="transcript";dismiss() }.accessibilityIdentifier("openDuplicateMeetingButton")
                }.padding(12).background(.orange.opacity(0.12),in:RoundedRectangle(cornerRadius:10)).accessibilityIdentifier("duplicateImportNotice")
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
                Button(ImportDuplicate.uploadLabel(duplicate:duplicate != nil)) { start(resume:nil) }.buttonStyle(.borderedProminent)
                    .disabled(!consent || models.isEmpty || path==nil || title.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || model.busy)
            }
        }.padding(24).frame(width:640)
        .task {
            do {
                let response=try await model.request(["action":"openrouter_models"])
                let data=try JSONSerialization.data(withJSONObject:response["models"] ?? [])
                models=try JSONDecoder().decode([OpenRouterModelOption].self,from:data)
                if let stored=model.meeting?.metadata["model"] as? String, resumable != nil, models.contains(where:{$0.id==stored}) { selectedModel=stored }
                guard models.contains(where:{$0.id==selectedModel}) else { throw OpenRouterCredential.failure("Varsayılan model listede yok.") }
            } catch { message=error.localizedDescription;models=[] }
        }
    }
    /// Hashes the picked file locally and asks the bridge whether a meeting already came from it. Never blocks the upload.
    private func checkDuplicate(_ url:URL) async {
        duplicate=nil;digest=nil;fileSize=nil
        guard let response=try? await model.request(["action":"check_duplicate","path":url.path]), path==url else { return }
        duplicate=ImportDuplicate.parse(response);digest=response["digest"] as? String;fileSize=response["size"] as? Int
    }
    private func start(resume:String?) {
        guard consent,!model.busy,models.contains(where:{$0.id==selectedModel}) else { return }
        let result=model.dataDir.appendingPathComponent("openrouter-\(UUID().uuidString).json")
        let args:[String]
        var registration:[String:Any]?   // digest of the picked file; only a fresh import owns the new meeting
        if let resume, let meeting=model.meetings.first(where:{ $0.id==resume }) { model.jobTitle=""; args=CloudTranscription.resumeArguments(meeting:meeting,model:selectedModel,output:result.path) }
        else if let path {
            model.jobTitle=title.isEmpty ? "OpenRouter toplantısı":title
            model.jobAudioPath=path.path
            args=CloudTranscription.importArguments(model:selectedModel,output:result.path)
            if let digest { registration=["action":"register_import_digest","digest":digest];if let fileSize { registration?["size"]=fileSize } }
        }
        else { return }
        model.activity="Ses OpenRouter’a gönderiliyor · Bu Mac’te model yüklenmiyor"
        model.launch(args) { [weak model] ok in
            guard let model else { return }
            if ok,let mid=model.resultMeeting(result) {
                if var registration { registration["meeting"]=mid;Task { _=try? await model.request(registration);await model.refresh() } }
                model.selected=mid;model.tab="transcript";model.analyzeAutomatically(mid)
            } else { model.activity="İşlem tamamlanamadı · Kaydedilen parçalar korunuyor. OpenRouter penceresinden sürdürebilirsiniz." }
        }
        dismiss()
    }
}
