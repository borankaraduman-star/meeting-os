import SwiftUI

/// First launch on a fresh Mac: three steps and nothing else.
struct WelcomeView:View {
    @ObservedObject var model:Model
    var body:some View {
        VStack(alignment:.leading,spacing:18) {
            Text("Hoş geldin").font(.system(size:27,weight:.bold,design:.rounded))
            Text("Meeting OS Zoom toplantılarını kaydeder, OpenRouter’da Türkçe yazıya çevirir, konuşanları tanır ve kararları, görevleri çıkarır. Bu Mac’te model yüklenmez.").font(.callout).foregroundStyle(.secondary).frame(maxWidth:560,alignment:.leading)
            VStack(alignment:.leading,spacing:12) {
                step("1","Kaydı başlat","Zoom açıkken her yerden ⌃⌥R, ya da soldaki “Yeni kayıt”. Bitirmek için yine ⌃⌥R veya yüzen paneldeki “Bitir”.")
                step("2","Transkript ve özet kendiliğinden gelir","Kayıt bitince ses OpenRouter’a gider; birkaç dakika içinde transkript, özet, görevler ve Kontrol kuyruğu hazır olur.")
                step("3","Bir kez adlandır, sonra tanınır","Kontrol sekmesinde konuşanlara adını ver; ses profili kaydedilir ve sonraki toplantılarda aynı kişi kendiliğinden tanınır.")
            }.padding(18).meetingCard().frame(maxWidth:640)
            HStack(spacing:10) {
                Button { model.start() } label: { Label("Yeni kayıt",systemImage:"record.circle") }.buttonStyle(.borderedProminent).disabled(model.busy)
                Button("Ayarlar → Kurulum durumu") { Task { await model.settings() } }
            }
            Text("İzinler eksikse Kurulum durumu kartı gösterir ve tek tıkla ister.").font(.caption).foregroundStyle(.secondary)
        }.padding(32).frame(maxWidth:.infinity,maxHeight:.infinity,alignment:.topLeading).accessibilityIdentifier("welcome")
    }
    func step(_ n:String,_ title:String,_ text:String)->some View {
        HStack(alignment:.top,spacing:12) {
            Text(n).font(.caption.weight(.bold)).frame(width:22,height:22).background(MeetingStyle.accent.opacity(0.15),in:Circle()).foregroundStyle(MeetingStyle.accent)
            VStack(alignment:.leading,spacing:2) { Text(title).font(.headline); Text(text).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true) }
        }
    }
}
