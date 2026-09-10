import SwiftUI

/// First launch on a fresh Mac: three steps and nothing else.
struct WelcomeView:View {
    @ObservedObject var model:Model
    /// The name field is the one thing this screen must not let anybody walk past: a recording started without
    /// it files this Mac's own voice under nobody. ⌃⌥R and the buttons send the caret back here.
    @FocusState private var nameFocused:Bool
    var body:some View {
        VStack(alignment:.leading,spacing:18) {
            Text("Hoş geldiniz").font(.system(size:27,weight:.bold,design:.rounded))
            Text("Meeting OS Zoom toplantılarını kaydeder, bulutta Türkçe yazıya çevirir, konuşanları tanır ve kararları, görevleri çıkarır. Bu Mac’te model yüklenmez.").font(.callout).foregroundStyle(.secondary).frame(maxWidth:560,alignment:.leading)
            HStack(spacing:10) {
                Text("Adınız").font(.callout)
                TextField("Adınızı yazın",text:$model.reportSettings.userName)
                    .textFieldStyle(.roundedBorder).frame(width:200)
                    .focused($nameFocused)
                    .accessibilityIdentifier("welcomeUserNameField")
                    .onSubmit { Task { await model.saveUserName() } }
                    .onDisappear { Task { await model.saveUserName() } }   // first run: the name is asked once, saved when the view goes away
                    .onChange(of:model.userNameFocusToken) { _,_ in nameFocused=true }
                Text("Mikrofon kaydınız bu adla etiketlenir; sonradan Ayarlar → Genel’den değişir.").font(.caption).foregroundStyle(.secondary)
            }
            if !model.hasUserName {
                Label("Kayıt başlamadan önce bu alan dolu olmalı.",systemImage:"info.circle").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("welcomeNameRequired")
            }
            VStack(alignment:.leading,spacing:12) {
                step("1","Kaydı başlat","Zoom açıkken her yerden ⌃⌥R, ya da soldaki “Yeni kayıt”. Bitirmek için yine ⌃⌥R veya yüzen paneldeki “Bitir”.")
                step("2","Transkript ve özet kendiliğinden gelir","Kayıt bitince ses buluta gider; birkaç dakika içinde transkript, özet, görevler ve Kontrol sekmesi hazır olur.")
                step("3","Bir kez adlandırın, sonra tanınır","Transkriptin üstündeki İsimler kartında her sese bir kez ad verin; ses profili kaydedilir ve sonraki toplantılarda aynı kişi kendiliğinden tanınır.")
            }.padding(18).meetingCard().frame(maxWidth:640)
            HStack(spacing:10) {
                Button { model.beginRecording() } label: { Label("Yeni kayıt",systemImage:"record.circle") }.buttonStyle(.borderedProminent).disabled(!model.recording && model.recordProcess != nil)
                Button("Kurulum durumunu aç") { Task { await model.settings() } }
            }
            Text("İzinler eksikse Kurulum durumu kartı gösterir ve tek tıkla ister.").font(.caption).foregroundStyle(.secondary)
            Text("Her toplantıdan sonra sayısal bir teşhis raporu (süre, puan, maliyet, model adı) varsayılan olarak iCloud’daki ekip klasörüne yazılır; konuşma metni girmez. Kapatmak için: Ayarlar → Sistem → Gelişmiş.").font(.caption).foregroundStyle(.secondary).frame(maxWidth:640,alignment:.leading).fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("welcomeReportsNotice")
        }.padding(32).frame(maxWidth:.infinity,maxHeight:.infinity,alignment:.topLeading).accessibilityIdentifier("welcome")
    }
    func step(_ n:String,_ title:String,_ text:String)->some View {
        HStack(alignment:.top,spacing:12) {
            Text(n).font(.caption.weight(.bold)).frame(width:22,height:22).background(MeetingStyle.accent.opacity(0.15),in:Circle()).foregroundStyle(MeetingStyle.accent)
            VStack(alignment:.leading,spacing:2) { Text(title).font(.headline); Text(text).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true) }
        }
    }
}
