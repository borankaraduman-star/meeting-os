import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// What the share preview contains. Pure value so the bridge request, the status line and the file name are testable.
struct ShareOptions:Equatable {
    var maskNames=true
    var onlyDecisions=false
    var includeTranscript=true
    /// Decisions-only never needs the transcript; the bridge drops everything but the decisions section anyway.
    var kinds:[String] { (includeTranscript && !onlyDecisions) ? ["transcript","summary"] : ["summary"] }
    func request(action:String,meeting:String,path:String?=nil)->[String:Any] {
        var r:[String:Any]=["action":action,"meeting":meeting,"mask_names":maskNames,"only_decisions":onlyDecisions,"kinds":kinds]
        if let path { r["path"]=path }
        return r
    }
    /// One line under the preview: what was masked and how much of the meeting is included.
    func summary(maskedNames:Int,segments:Int)->String {
        // Literal capitals: String.uppercased() without a Turkish locale would turn “isimler” into “Isimler”.
        let names=maskNames ? (maskedNames==0 ? "Maskelenecek isim bulunmadı" : "\(maskedNames) isim maskelendi") : "İsimler açık"
        let scope=onlyDecisions ? "yalnız kararlar" : (includeTranscript ? "\(segments) bölüm" : "transkript yok")
        return "\(names) · \(scope)"
    }
    func fileName(title:String)->String {
        let base=title.trimmingCharacters(in:.whitespacesAndNewlines).replacingOccurrences(of:"/",with:"-").replacingOccurrences(of:":",with:"-")
        return "\(base.isEmpty ? "Toplantı" : base) · paylaşım\(onlyDecisions ? " · kararlar" : "")\(maskNames ? " · maskeli" : "").md"
    }
}

/// Read-only preview of one meeting for sharing. Nothing stored changes; masking is applied to the exported text only.
@MainActor struct ShareSheet:View {
    @ObservedObject var model:Model
    @State var options=ShareOptions()
    @State var preview=""
    @State var status="Önizleme hazırlanıyor…"
    @State var failure=""
    @State var loading=false
    var body:some View {
        VStack(alignment:.leading,spacing:14) {
            Text("Önizleme bu Mac’te hazırlanır; kayıtlı metin, isimler ve analiz değişmez. Maskeleme konuşmacı adlarını ve sözlükteki kişileri yalnız dışa verilen metinde “Kişi A, Kişi B…” yapar.").font(.caption).foregroundStyle(.secondary)
            HStack(spacing:18) {
                Toggle("İsimleri maskele",isOn:$options.maskNames).accessibilityIdentifier("shareMaskToggle")
                Toggle("Yalnız kararlar",isOn:$options.onlyDecisions).accessibilityIdentifier("shareDecisionsToggle")
                Toggle("Transkripti dahil et",isOn:$options.includeTranscript).disabled(options.onlyDecisions).accessibilityIdentifier("shareTranscriptToggle")
            }.toggleStyle(.checkbox)
            ScrollView {
                Text(preview.isEmpty && !loading ? "Önizleme yok." : preview).font(.system(.body,design:.monospaced)).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading).padding(12)
            }.frame(maxWidth:.infinity,maxHeight:.infinity).border(.quaternary).accessibilityIdentifier("sharePreview")
            HStack {
                if loading { ProgressView().controlSize(.small) }
                Text(failure.isEmpty ? status : ErrorPresentation.summary(failure)).font(.caption).foregroundStyle(failure.isEmpty ? Color.secondary : Color.red).lineLimit(2)
                Spacer()
                Button("Dosyaya kaydet…") { Task { await save() } }.buttonStyle(.borderedProminent).disabled(loading || model.selected==nil || !failure.isEmpty).accessibilityIdentifier("shareSaveButton")
            }
        }.padding(.horizontal,24).padding(.top,16).padding(.bottom,24).frame(maxHeight:.infinity)
        .sheetChrome(title:"Paylaşım önizlemesi") { model.showShare=false }
        .frame(width:640,height:600)
        .task(id:options) { await refresh() }
    }
    func refresh() async {
        guard let mid=model.selected else { preview="";status="Toplantı seçilmedi";return }
        loading=true;failure=""
        do {
            let r=try await model.request(options.request(action:"share_preview",meeting:mid))
            preview=r["text"] as? String ?? ""
            status=options.summary(maskedNames:r["masked_names"] as? Int ?? 0,segments:r["segments"] as? Int ?? 0)
        } catch { failure=error.localizedDescription }
        loading=false
    }
    func save() async {
        guard let mid=model.selected else { return }
        let panel=NSSavePanel();panel.nameFieldStringValue=options.fileName(title:model.meeting?.title ?? "");panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do {
            let r=try await model.request(options.request(action:"share_export",meeting:mid,path:url.path))
            model.activity="Paylaşım dosyası kaydedildi · "+options.summary(maskedNames:r["masked_names"] as? Int ?? 0,segments:r["segments"] as? Int ?? 0)+" · Gönderim yapılmadı"
            model.showShare=false
        } catch { failure=error.localizedDescription }
    }
}
