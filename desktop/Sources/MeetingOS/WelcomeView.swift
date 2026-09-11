import SwiftUI

/// First launch on a fresh Mac: three steps and nothing else.
struct WelcomeView:View {
    @ObservedObject var model:Model
    /// The name field is the one thing this screen must not let anybody walk past: a recording started without
    /// it files this Mac's own voice under nobody. ⌃⌥R and the buttons send the caret back here.
    @FocusState private var nameFocused:Bool
    /// A teammate who was sent an invite has nothing to set up: they paste the link here and the app joins the
    /// team, key included when the sender ticked the box. Shown only while this Mac has neither a key nor a
    /// team — a second Mac of Boran's, or a colleague on day one.
    @State private var invite=""
    /// A downloaded package carries its own invite and applies it on first launch, so this whole card stays
    /// away: that Mac is asked for a name and nothing else. It comes back only if the shipped invite could
    /// not be applied, because then pasting one is the only way in.
    /// Also shown when the team is already joined but there is no key yet (a package invite carries only the team;
    /// the personal key arrives as a second link): pasting that link here writes the key.
    private var needsInvite:Bool { OpenRouterCredential.cached()==nil && !model.bundleInvitePending }
    var body:some View {
        VStack(alignment:.leading,spacing:18) {
            Text("Hoş geldiniz").font(.system(size:27,weight:.bold,design:.rounded))
            Text("Meeting OS Zoom toplantılarını kaydeder, bulutta Türkçe yazıya çevirir, konuşanları tanır ve kararları, görevleri çıkarır. Bu Mac’te model yüklenmez.").font(.callout).foregroundStyle(.secondary).frame(maxWidth:560,alignment:.leading)
            if needsInvite {
                VStack(alignment:.leading,spacing:8) {
                    Text(model.teamConfigured ? "Kişisel bağlantınızı yapıştırın" : "Ekipten davet aldınız mı?").font(.headline)
                    HStack(spacing:10) {
                        TextField("Davet bağlantısını buraya yapıştırın",text:$invite)
                            .textFieldStyle(.roundedBorder).frame(width:320)
                            .accessibilityIdentifier("welcomeInviteField")
                            .onSubmit { join() }
                        Button("Katıl") { join() }.buttonStyle(.borderedProminent)
                            .disabled(TeamInvite.payload(invite)==nil).accessibilityIdentifier("welcomeInviteJoinButton")
                    }
                    Text("Ekip arkadaşınızın gönderdiği `meetingos://join…` bağlantısını yapıştırın: ekibin sözlüğü, kelimeleri ve ses profilleri bu Mac’e iner. Davette OpenRouter anahtarı da varsa aşağıdaki anahtar adımını hiç görmezsiniz.").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                }.padding(16).meetingCard().frame(maxWidth:640).accessibilityIdentifier("welcomeInvite")
            }
            HStack(spacing:10) {
                Text("Adınız").font(.callout)
                TextField("Adınızı yazın",text:$model.reportSettings.userName)
                    .textFieldStyle(.roundedBorder).frame(width:200)
                    .focused($nameFocused)
                    .accessibilityIdentifier("welcomeUserNameField")
                    .onSubmit { Task { await model.saveUserName() } }
                    .onDisappear { Task { await model.saveUserName() } }   // first run: the name is asked once, saved when the view goes away
                    .onChange(of:model.userNameFocusToken) { _,_ in nameFocused=true }
                Text("Mikrofon kaydınız bu adla etiketlenir; sonradan Ayarlar → Genel’den değişir.").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
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
            Text("İzinler eksikse Kurulum durumu kartı gösterir ve tek tıkla ister.").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
            Text("Her toplantıdan sonra sayısal bir teşhis raporu (süre, puan, maliyet, model adı) varsayılan olarak iCloud’daki ekip klasörüne yazılır; konuşma metni girmez. Kapatmak için: Ayarlar → Sistem → Gelişmiş.").font(.caption).foregroundStyle(.secondary).frame(maxWidth:640,alignment:.leading).fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("welcomeReportsNotice")
        // A form, not a notice: the column is centred in the window but stays top-aligned and left-read,
        // because vertical centring would move the name field under the caret as the steps grow.
        }.padding(32).readingColumn(700).frame(maxHeight:.infinity,alignment:.top).accessibilityIdentifier("welcome")
        .task { await model.loadTeamStatus() }   // one tiny bridge call: does this Mac belong to a team yet?
    }
    private func join() {
        guard let payload=TeamInvite.payload(invite) else { return }
        invite=""
        Task { await model.joinTeam(payload) }
    }
    func step(_ n:String,_ title:String,_ text:String)->some View {
        HStack(alignment:.top,spacing:12) {
            Text(n).font(.caption.weight(.bold)).frame(width:22,height:22).background(MeetingStyle.accent.opacity(0.15),in:Circle()).foregroundStyle(MeetingStyle.accent)
            VStack(alignment:.leading,spacing:2) { Text(title).font(.headline); Text(text).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true) }
        }
    }
}
