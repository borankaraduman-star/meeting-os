import SwiftUI
import AppKit
import UniformTypeIdentifiers

// Import creates a new text-only meeting. No account access or recording happens here.
struct TranscriptImportDraft {
    static let byteLimit=1_048_576
    var text=""
    var title=""
    var previewedText:String?
    var previewedTitle:String?
    var inputError:String? {
        if text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty { return "Aktarmak için transkript metnini yapıştırın veya bir .txt dosyası seçin." }
        if text.utf8.count > Self.byteLimit { return "Metin en fazla 1 MB olabilir. Daha küçük bir .txt dosyası seçin." }
        if text.contains("\0") { return "Dosya düz metin değil. UTF-8 biçiminde bir .txt dosyası seçin." }
        if title.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty { return "Toplantıya bir ad verin." }
        return nil
    }
    var canSave:Bool { inputError == nil && previewedText == text && previewedTitle == title }
    mutating func invalidatePreview() { previewedText=nil;previewedTitle=nil }
    mutating func markPreviewed() { previewedText=text;previewedTitle=title }
    static func readFile(_ url:URL) throws -> String {
        let handle=try FileHandle(forReadingFrom:url)
        defer { try? handle.close() }
        let data=try handle.read(upToCount:byteLimit+1) ?? Data()
        guard data.count <= byteLimit else { throw failure("Dosya en fazla 1 MB olabilir.") }
        guard let text=String(data:data,encoding:.utf8), !text.contains("\0") else { throw failure("Dosya UTF-8 düz metin olmalı. .txt biçiminde yeniden kaydedin.") }
        return text
    }
    static func failure(_ message:String)->NSError { NSError(domain:"MeetingOS.Import",code:1,userInfo:[NSLocalizedDescriptionKey:message]) }
}

struct TranscriptImportSheet:View {
    @ObservedObject var model:Model
    @Environment(\.dismiss) private var dismiss
    @State private var draft=TranscriptImportDraft()
    @State private var preview:[[String:Any]]=[]
    @State private var working=false
    @State private var message=""
    var body:some View {
        VStack(alignment:.leading,spacing:14) {
            Text("ChatGPT metni aktar").font(.title2.bold())
            Text("ChatGPT açılır. Kaydı ChatGPT’de başlatıp metni buraya kendiniz aktarın. Hesabınıza bağlanılmaz; ses yüklenmez.")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Button("ChatGPT’yi aç",action:openChatGPT)
                Button("UTF-8 .txt dosyası seç",action:chooseFile).accessibilityIdentifier("chooseTranscriptFileButton")
            }.disabled(working)
            TextField("Toplantı adı",text:$draft.title).textFieldStyle(.roundedBorder).disabled(working)
                .accessibilityIdentifier("importTranscriptTitle")
            TextEditor(text:$draft.text).font(.body).frame(minHeight:120,maxHeight:180).border(.quaternary).disabled(working)
                .accessibilityIdentifier("importTranscriptText")
            Text("En fazla 1 MB · Düz metin; varsa konuşmacı: metin veya [00:12] konuşmacı: metin. Eksik zaman ve isimler eklenmez.")
                .font(.caption).foregroundStyle(.secondary)
            if !preview.isEmpty {
                Text("Önizleme · \(preview.count) bölüm").font(.headline)
                ScrollView {
                    LazyVStack(alignment:.leading,spacing:12) {
                        ForEach(preview.indices,id:\.self) { i in
                            VStack(alignment:.leading,spacing:4) {
                                HStack {
                                    Text(preview[i]["speaker_name"] as? String ?? "İsim belirtilmemiş").font(.caption.bold())
                                    if let start=preview[i]["start"] as? Double { Text(String(format:"%02d:%02d",Int(start)/60,Int(start)%60)).font(.caption.monospacedDigit()) }
                                }.foregroundStyle(.secondary)
                                Text(preview[i]["text"] as? String ?? "").textSelection(.enabled)
                            }
                        }
                    }.frame(maxWidth:.infinity,alignment:.leading)
                }.frame(minHeight:80,maxHeight:170)
            }
            Text("Yeni bir toplantı oluşturulur. Ham metin korunur. Bu aktarım ses kaydı içermez; konuşmacı isimleri doğrulanmış ses profili sayılmaz.")
                .font(.caption).foregroundStyle(.secondary)
            if !message.isEmpty { Text(message).font(.callout).foregroundStyle(.red).accessibilityIdentifier("transcriptImportError") }
            HStack {
                Button("Vazgeç") { dismiss() }.keyboardShortcut(.cancelAction).disabled(working)
                Spacer()
                if working { ProgressView().controlSize(.small) }
                Button("Önizle") { Task { await previewText() } }.disabled(working).accessibilityIdentifier("previewTranscriptButton")
                Button("Yeni toplantıya kaydet") { Task { await save() } }
                    .buttonStyle(.borderedProminent).disabled(working || !draft.canSave || preview.isEmpty)
                    .accessibilityIdentifier("saveTranscriptImportButton")
            }
        }.padding(24).frame(width:640)
        .onChange(of:draft.text) { _,_ in resetPreview() }
        .onChange(of:draft.title) { _,_ in resetPreview() }
        .interactiveDismissDisabled(working)
    }
    private func resetPreview() { draft.invalidatePreview();preview=[];message="" }
    private func openChatGPT() {
        let installed=URL(fileURLWithPath:"/Applications/ChatGPT.app")
        let appURL=FileManager.default.fileExists(atPath:installed.path) ? installed : NSWorkspace.shared.urlForApplication(withBundleIdentifier:"com.openai.chat")
        if let url=appURL {
            NSWorkspace.shared.openApplication(at:url,configuration:NSWorkspace.OpenConfiguration()) { _,_ in }
        } else if let url=URL(string:"https://chatgpt.com/") { NSWorkspace.shared.open(url) }
    }
    private func chooseFile() {
        let panel=NSOpenPanel();panel.allowedContentTypes=[.plainText];panel.canChooseDirectories=false;panel.allowsMultipleSelection=false
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do {
            let text=try TranscriptImportDraft.readFile(url)
            draft.text=text
            if draft.title.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty { draft.title=url.deletingPathExtension().lastPathComponent }
            resetPreview()
        } catch { message=error.localizedDescription }
    }
    private func previewText() async {
        guard !working else { return }
        if let error=draft.inputError { message=error;return }
        let text=draft.text,title=draft.title
        working=true;message="";draft.invalidatePreview();preview=[]
        defer { working=false }
        do {
            let response=try await model.request(["action":"transcript_preview","text":text])
            guard text==draft.text,title==draft.title else { return }
            preview=response["rows"] as? [[String:Any]] ?? []
            guard !preview.isEmpty else { throw TranscriptImportDraft.failure("Aktarılabilir metin bölümü bulunamadı.") }
            draft.markPreviewed()
        } catch { message=error.localizedDescription }
    }
    private func save() async {
        guard !working,draft.canSave,!preview.isEmpty else { return }
        working=true;message=""
        defer { working=false }
        do {
            let response=try await model.request(["action":"transcript_import","text":draft.text,"title":draft.title])
            guard let mid=response["meeting"] as? String,!mid.isEmpty else { throw TranscriptImportDraft.failure("Toplantı kaydı doğrulanamadı. Toplantı listesini kontrol edin.") }
            model.selected=mid;model.tab="transcript";model.search=""
            model.activity="ChatGPT metni aktarıldı · Ses kaydı içermez"
            await model.refresh()
            dismiss()
        } catch { message=error.localizedDescription }
    }
}
