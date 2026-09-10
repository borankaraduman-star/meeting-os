import SwiftUI
import AppKit

struct SettingsSheet:View {
    @ObservedObject var model:Model
    @AppStorage("settingsSection") private var section="genel"
    @State private var advanced=false
    /// A refused recording sends the caret here; the sheet opens on Genel and the field takes focus.
    @FocusState private var nameFocused:Bool
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:16) {
                Picker("Ayar grubu",selection:Binding(get:{ SettingsSections.normalize(section) },set:{ section=$0 })) { Text("Genel").tag("genel"); Text("Sesler ve sözlük").tag("sesler"); Text("Sistem").tag("sistem") }.pickerStyle(.segmented).labelsHidden().accessibilityIdentifier("settingsSection")
                if group=="sistem" {
                Text("Yazıya çevirme").font(.headline)
                Picker("Yazıya çevirme",selection:$model.transcriptionMode) { Text("OpenRouter (bulut)").tag("openrouter");Text("Yerel model").tag("local") }
                    .pickerStyle(.segmented).labelsHidden().frame(width:320).disabled(model.recording || model.busy).accessibilityIdentifier("transcriptionModePicker")
                if model.transcriptionMode=="openrouter" {
                    if model.cloudModels.isEmpty { Text("Model listesi yükleniyor…").font(.caption).foregroundStyle(.secondary) }
                    else {
                        Picker("Model",selection:$model.cloudModel) { ForEach(model.cloudModels) { Text($0.name).tag($0.id) } }
                            .labelsHidden().frame(width:320).disabled(model.recording || model.busy).accessibilityIdentifier("cloudModelPicker")
                    }
                    Text("Kayıt bitince ses OpenRouter’a gider; bu Mac’te model yüklenmez, canlı metin olmaz. Her yerden ⌃⌥R başlat/bitir, ⌃⌥M an işaretle.").font(.caption2).foregroundStyle(.secondary)
                } else {
                    Text("Yerel model bu Mac’te çalışır ve bellek baskısında durur.").font(.caption2).foregroundStyle(.secondary)
                }
                OpenRouterKeyRow()
                Divider()
                }
                if group=="sistem" {
                if let storage=model.storage { StorageSection(model:model,storage:storage); Divider() }
                }
                if group=="sesler" {
                Text("Kaydedilmiş sesler").font(.headline)
                Text("Aynı isimde farklı kişiler için ayırt edici bir ad kullanın (ör. Ali Tasarım). Yeni bir profil, aynı isimdeki mevcut kişinin ses örneklerine eklenir.").font(.caption).foregroundStyle(.secondary)
                if model.profiles.isEmpty {
                    VStack(alignment:.leading,spacing:6) {
                        Label("Henüz ses profili yok",systemImage:"person.wave.2")
                        Text("Bir transkript bölümünde Düzelt düğmesine basarak temiz bir konuşma örneğinden profil kaydedebilirsiniz.").font(.caption).foregroundStyle(.secondary)
                    }.frame(maxWidth:.infinity,alignment:.leading).padding(16).meetingCard()
                } else { VStack(alignment:.leading,spacing:4) { ForEach(model.profiles) { p in ProfileMaintenanceRow(model:model,profile:p) } }.padding(12).meetingCard()
                    .task { await model.loadMaintenance() }   // the person cards read profile health: samples, weakest fit, last meeting
                }
                Divider()
                }
                if group=="sesler" {
                Text("Sözlük").font(.headline)
                Text("Kişi adlarını ve özel terimleri her satıra bir tane yazın.")
                TextEditor(text:$model.vocabulary).font(.body.monospaced()).frame(height:160).border(.quaternary)
                Text("Proje sözlüğü (glossary.jsonl)").font(.headline)
                Text(model.glossaryFromFile>0 ? "\(model.glossaryFromFile) terim dosyadan, toplam \(model.glossaryCount) · örnek: \(model.glossarySample.prefix(6).joined(separator:", ")) · iCloud Drive ile bütün Mac’lerde aynı" : "Henüz sözlük dosyası yok. Slack agent’ın ürettiği JSON Lines dosyasını içe aktarın; iCloud Drive üzerinden bütün Mac’lere yayılır.").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button("glossary.jsonl içe aktar…") { Task { await model.importGlossary() } }.accessibilityIdentifier("importGlossaryButton")
                    Text("Sözlük üç yerde kullanılır: bulut yazıya çevirmeye yazım ipucu (etkisi sağlayıcıya bağlı), transkript sonrası düzeltme önerileri (Kontrol), özetlerde kısaltma açılımı. Ham metin hiçbir zaman kendiliğinden değiştirilmez.").font(.caption2).foregroundStyle(.secondary)
                }
                Divider()
                }
                if group=="sesler" { LearnedWordsSection(model:model); Divider() }
                if group=="sesler" {
                Text("Ekip klasörü").font(.headline)
                HStack(spacing:8) {
                    Text(model.reportSettings.teamDir.isEmpty ? "Seçilmedi" : model.reportSettings.teamDir.replacingOccurrences(of:NSHomeDirectory(),with:"~"))
                        .font(.caption.monospaced()).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                    Spacer()
                    Button("Seç…") { pickTeamDir() }.accessibilityIdentifier("pickTeamDirButton")
                    if !model.reportSettings.teamDir.isEmpty {
                        Button("Kaldır") { model.reportSettings.teamDir=""; Task { await model.saveReportSettings() } }.accessibilityIdentifier("clearTeamDirButton")
                    }
                }
                Toggle("Sözlüğü ekip klasörüyle paylaş (yerel sözlük her zaman öncelikli)",isOn:$model.reportSettings.shareGlossary)
                    .onChange(of:model.reportSettings.shareGlossary) { _ in Task { await model.saveReportSettings() } }
                    .disabled(model.reportSettings.teamDir.isEmpty)
                Toggle("Öğretilen kelimeleri ekiple paylaş (ekip klasörü)",isOn:$model.reportSettings.shareWords)
                    .onChange(of:model.reportSettings.shareWords) { _ in Task { await model.saveReportSettings() } }
                    .disabled(model.reportSettings.teamDir.isEmpty).accessibilityIdentifier("shareWordsToggle")
                Toggle("Ses profillerimi ekiple paylaş (kişi adı + ses vektörü; ses kaydı değil)",isOn:$model.reportSettings.shareProfiles)
                    .onChange(of:model.reportSettings.shareProfiles) { _ in Task { await model.saveReportSettings() } }
                    .disabled(model.reportSettings.teamDir.isEmpty).accessibilityIdentifier("shareProfilesToggle")
                Text("Kapalıyken yalnız bu Mac tanır. Açınca ekip klasörüne yazılır; ekip arkadaşları bu kişileri ilk toplantıda tanır.").font(.caption2).foregroundStyle(.secondary)
                Text("Ortak bir klasör (paylaşılan disk, Drive, Dropbox) seçin: ekip klasörü ortak bilgi tabanıdır — sözlük, öğretilen kelimeler ve ses profilleri (kişi adı + ses vektörü) ekipçe birikir, teşhis raporları da kişisel klasör yerine oraya yazılır. Ses kaydı, transkript, toplantı adı ve toplantı numarası bu klasöre hiç girmez.").font(.caption2).foregroundStyle(.secondary)
                }
                if group=="sistem" {
                if let cost=model.cost, let month=cost["month"] as? [String:Any], let all=cost["all"] as? [String:Any] {
                    VStack(alignment:.leading,spacing:6) {
                        Text("Bulut maliyeti").font(.headline)
                        HStack(spacing:12) {
                            SmallMetric(value:String(format:"$%.2f",month["usd"] as? Double ?? 0),label:"Bu ay · \(month["meetings"] as? Int ?? 0) toplantı, \(Int(month["minutes"] as? Double ?? 0)) dk",icon:"cloud")
                            SmallMetric(value:String(format:"$%.2f",all["usd"] as? Double ?? 0),label:"Toplam · \(all["meetings"] as? Int ?? 0) toplantı, \(Int(all["minutes"] as? Double ?? 0)) dk",icon:"sum")
                        }
                        // `analysis_unpriced` meetings were analysed before their calls were recorded: the sum is real
                        // but incomplete, so it is shown with "(kısmi)" rather than hidden behind an em dash.
                        SmallMetric(value:cost["analysis_cost"] == nil || ((cost["analysis_calls"] as? Int ?? 0)==0 && (cost["analysis_cost_known"] as? Bool)==false) ? "—" : String(format:"$%.2f",cost["analysis_cost"] as? Double ?? 0),label:"Analiz · \(cost["analysis_calls"] as? Int ?? 0) çağrı"+((cost["analysis_estimated"] as? Bool)==true ? " (tahmini)" : "")+((cost["analysis_unpriced"] as? Int ?? 0)>0 && (cost["analysis_calls"] as? Int ?? 0)>0 ? " (kısmi)" : ""),icon:"text.badge.checkmark").accessibilityIdentifier("analysisCost")
                        Text("OpenRouter’ın bildirdiği transkript ücretleri (≈ $0.10/saat MAI-Transcribe 2) ve özet/görev analizi çağrıları"+((cost["analysis_estimated"] as? Bool)==true ? " (analiz tutarı model fiyatından tahmin edilir)" : "")+". Yankı olarak atlanan parçalar ücretlendirilmez.").font(.caption2).foregroundStyle(.secondary)
                    }
                }
                Text("Güncelleme ve raporlar").font(.headline)
                Text(model.update?.headline ?? "Sürüm kontrolü yapılmadı").font(.caption).foregroundStyle(.secondary)
                Text("Yeni sürüm varsa kenar çubuğunda ve menü çubuğu simgesinde “Güncelle ve yeniden başlat” görünür; güncelken düğme yoktur. Kontrol açılışta, uygulama öne gelince ve 15 dakikada bir yapılır.").font(.caption2).foregroundStyle(.secondary)
                HStack {
                    Button("Şimdi kontrol et") { Task { await model.checkForUpdates(force:true) } }
                    if model.update?.canUpdate==true { Button(model.zoomMeetingOpen ? "Güncelleme toplantı bitince" : "Güncelle ve yeniden başlat") { model.startUpdate() }.disabled(model.busy || model.recording || model.zoomMeetingOpen) }
                }
                Divider()
                }
                if group=="sistem", !model.setupChecks.isEmpty {
                    VStack(alignment:.leading,spacing:6) {
                        HStack { Text("Kurulum durumu").font(.headline);Spacer();Button("Yenile") { Task { await model.loadSetupStatus() } }.controlSize(.small) }
                        ForEach(model.setupChecks) { c in
                            HStack(alignment:.top,spacing:8) {
                                Circle().fill(c.state == .ok ? MeetingStyle.accent : (c.state == .missing ? Color.red : (c.state == .unknown ? Color.orange : Color.secondary))).frame(width:8,height:8).padding(.top,5)
                                VStack(alignment:.leading,spacing:1) { Text(c.title).font(.callout); Text(c.hint).font(.caption2).foregroundStyle(.secondary) }
                                Spacer()
                                if SetupStatus.fixable(c) { Button(SetupStatus.fixLabel(c)) { SetupStatus.fix(c.id,calendarWanted:model.useCalendar) { Task { await model.loadSetupStatus() } } }.controlSize(.small).accessibilityIdentifier("fixSetup-\(c.id)") }
                            }
                        }
                        Text("Kırmızı: kayıt ya da güncelleme bu izin/ayar olmadan çalışmaz. Gri: isteğe bağlı.").font(.caption2).foregroundStyle(.secondary)
                    }.padding(14).meetingCard().accessibilityElement(children:.contain).accessibilityIdentifier("setupStatus")
                }
                if group=="sistem" {
                DisclosureGroup("Gelişmiş",isExpanded:$advanced) {
                    VStack(alignment:.leading,spacing:10) {
                        if let storage=model.storage { StorageCleanupSection(model:model,storage:storage) }
                        Text("Kendiliğinden çalışanlar ve raporlar").font(.callout.weight(.semibold))
                        Toggle("Yeni sürüm bulununca açılışta kendiliğinden güncelle (kayıt yokken)",isOn:$model.reportSettings.autoUpdate).onChange(of:model.reportSettings.autoUpdate) { _ in Task { await model.saveReportSettings() } }
                        Toggle("Bulut hatasında boşta yeniden dene (kayıt ve Zoom toplantısı yokken, 10 dakikada bir en fazla bir toplantı)",isOn:$model.reportSettings.autoRetry).onChange(of:model.reportSettings.autoRetry) { _ in Task { await model.saveReportSettings() } }.accessibilityIdentifier("autoRetryToggle")
                        Toggle("Her toplantıdan sonra teşhis raporunu paylaşılan klasöre yaz",isOn:$model.reportSettings.shareReports).onChange(of:model.reportSettings.shareReports) { _ in Task { await model.saveReportSettings() } }
                        Toggle("Raporlara transkript metnini de ekle (varsayılan kapalı)",isOn:$model.reportSettings.shareText).onChange(of:model.reportSettings.shareText) { _ in Task { await model.saveReportSettings() } }
                        HStack {
                            Text(model.reportSettings.reportDir.replacingOccurrences(of:NSHomeDirectory(),with:"~")).font(.caption2.monospaced()).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                            Spacer()
                            Button("Rapor klasörünü aç") { NSWorkspace.shared.open(URL(fileURLWithPath:model.reportSettings.reportDir)) }
                        }
                        Text("Raporlar sayı, puan, maliyet, model adı ve hata satırı içerir; toplantı başlığı ve konuşmacı adları yalnız “metni de ekle” açıkken girer (1.2.37). iCloud Drive ya da ekip klasörü üzerinden diğer Mac’e geçer.").font(.caption2).foregroundStyle(.secondary)
                        Divider()
                        HStack { Button("Öz-test") { Task { await model.runProbe() } }.controlSize(.small).disabled(model.recording || model.busy).help("Kayıt yardımcısı, ffmpeg, ses modeli, veritabanı, disk, anahtar, sözlük ve rapor klasörünü birkaç saniyede sınar; toplantıdan önce çalıştırın").accessibilityIdentifier("probeButton"); Text("toplantıdan önce her şeyin yerinde olduğunu doğrular").font(.caption2).foregroundStyle(.secondary) }
                        if !model.probeLines.isEmpty { VStack(alignment:.leading,spacing:2) { ForEach(Array(model.probeLines.enumerated()),id:\.offset) { i,l in Text(l).font(i==0 ? .caption.weight(.semibold) : .caption2.monospacedDigit()).foregroundStyle(i==0 ? .primary : .secondary) } }.accessibilityIdentifier("probeResult") }
                        Text("Uygulama yoklaması · \(BridgeStats.shared.summary)").font(.caption2).foregroundStyle(.secondary).help("Python köprüsüne yapılan çağrıların süresi; p95 birkaç yüz ms üzerindeyse Mac yavaşlamış demektir")
                    }.padding(.top,8)
                }.font(.callout).accessibilityIdentifier("systemAdvanced")
                }
                if group=="genel" {
                Text("Sizin adınız").font(.headline)
                HStack(spacing:10) {
                    TextField("Adınızı yazın",text:$model.reportSettings.userName)
                        .textFieldStyle(.roundedBorder).frame(width:220)
                        .focused($nameFocused)
                        .accessibilityIdentifier("userNameField")
                        .onSubmit { Task { await model.saveUserName() } }
                        .onDisappear { Task { await model.saveUserName() } }   // saved once when the field goes away, not on every keystroke
                        .onChange(of:model.userNameFocusToken) { _,_ in nameFocused=true }
                        .onAppear { if !model.hasUserName { nameFocused=true } }   // the sheet a refused recording opened arrives after the token was bumped
                    Text("Mikrofon kaydı bu adla etiketlenir; “Bana ait” filtresi bu adı kullanır. Adı değiştirince önceki toplantılardaki kendi sesiniz de yeni adla etiketlenir.").font(.caption2).foregroundStyle(.secondary)
                }
                if !model.hasUserName { Label(Model.nameRequiredMessage,systemImage:"exclamationmark.circle").font(.caption).foregroundStyle(.orange).accessibilityIdentifier("userNameMissing") }
                Text("Görünüm").font(.headline)
                HStack(spacing:10) {
                    Picker("Tema",selection:$model.appearance) { Text("Sistem").tag("system"); Text("Açık").tag("light"); Text("Koyu").tag("dark") }.pickerStyle(.segmented).frame(width:220).accessibilityIdentifier("appearancePicker")
                    Text("Vurgu").font(.callout).foregroundStyle(.secondary)
                    ForEach(Accents.all,id:\.key) { a in
                        Button { model.accentKey=a.key } label: { Circle().fill(a.color).frame(width:18,height:18).overlay(Circle().stroke(Color.primary.opacity(model.accentKey==a.key ? 0.8 : 0),lineWidth:2)) }.buttonStyle(.plain).help(a.name).accessibilityIdentifier("accent-\(a.key)").accessibilityLabel(a.name)
                    }
                }
                Text("Tema uygulama penceresi ve yüzen paneli etkiler; menü çubuğu simgesi sistemi izler.").font(.caption2).foregroundStyle(.secondary)
                Text("Kayıt sırasında").font(.headline)
                Toggle("Zoom toplantısı açılınca bildirim gönder (kayıt yokken, 20 dakikada en fazla bir)",isOn:$model.zoomNotify)
                Toggle("Zoom toplantı penceresi açılınca kaydı kendiliğinden başlat, pencere kapandıktan 5 dk sonra ve mikrofon serbestse bitir (elle başlatılan kayıtlara dokunmaz)",isOn:$model.zoomAutoRecord)
                Toggle("Kayıt sırasında her pencerenin üstünde küçük kayıt paneli göster (süre, an işaretleri, bitir)",isOn:$model.showRecorderPanel)
                Toggle("Kayıt başlarken takvimdeki toplantının adını başlık yap, katılımcılarını adlandırmada öner (takvim yalnız okunur)",isOn:$model.useCalendar)
                }
                HStack {
                    Button("Veri klasörünü aç") { NSWorkspace.shared.open(model.dataDir) }
                    Spacer()
                    if group=="sesler" { Button("Sözlüğü kaydet") { Task { await model.saveVocabulary() } }.buttonStyle(.borderedProminent).accessibilityIdentifier("saveSettingsButton") }
                }
            }.padding(.horizontal,28).padding(.top,18).padding(.bottom,28)
        }.scrollIndicators(.visible).frame(maxHeight:.infinity)
        .sheetChrome(title:"Ayarlar",hint:"⌘,",onClose:close)
        .frame(width:640,height:CGFloat(SettingsSections.sheetHeight(section,screen:Double(NSScreen.main?.visibleFrame.height ?? 900))))
        .task { await model.loadCloudModels() }
    }
    /// The ✕ must leave the sheet exactly as the old footer button did: the name typed in Genel is written back
    /// (the field's onDisappear does it too, but only if the field was on screen) and the sheet closes.
    func close() {
        Task { await model.saveUserName() }
        model.showSettings=false
    }
    /// Folded from the five sections that shipped earlier; a value stored back then must still open a section.
    var group:String { SettingsSections.normalize(section) }
    /// Read-write folder picker; the backend refuses a path it cannot see, so the field reverts on failure.
    func pickTeamDir() {
        let panel=NSOpenPanel();panel.canChooseDirectories=true;panel.canChooseFiles=false;panel.allowsMultipleSelection=false;panel.prompt="Seç"
        guard panel.runModal() == .OK, let url=panel.url else { return }
        model.reportSettings.teamDir=url.path
        Task { await model.saveReportSettings() }
    }
}

/// The words the user taught (and the ones the app learned from repeated edits), with one way out per row.
/// Loaded only when the section appears: nothing here rides the two-second poll.
struct LearnedWordsSection:View {
    @ObservedObject var model:Model
    var body:some View {
        VStack(alignment:.leading,spacing:6) {
            HStack {
                Text("Öğrenilen kelimeler").font(.headline)
                if !model.teamSummary.isEmpty {
                    Text(model.teamSummary).font(.caption2).foregroundStyle(.secondary)
                        .help("Ekip klasöründen gelen ses profilleri ve kelimeler; her biri tek tek kapatılabilir").accessibilityIdentifier("teamSummary")
                }
                Spacer(); Button("Yenile") { Task { await model.loadWordRules() } }.controlSize(.small).accessibilityIdentifier("refreshWordRules")
            }
            if model.wordRules.isEmpty {
                Text("Henüz öğrenilen kelime yok. Düzelt penceresinde bir kelimeyi düzeltin.").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("wordRulesEmpty")
            } else {
                VStack(alignment:.leading,spacing:4) {
                    ForEach(model.wordRules) { rule in
                        HStack(spacing:8) {
                            Text(rule.line).font(.caption).lineLimit(1).truncationMode(.middle).foregroundStyle(rule.isTeam && !rule.active ? .secondary : .primary)
                            if rule.isTeam {
                                // Whose word this is, said on the row: a spelling that arrived from another Mac is
                                // not something the user typed here, and "Unut" would be the wrong verb for it.
                                Text(rule.host).font(.caption2).padding(.horizontal,6).padding(.vertical,1)
                                    .background(Capsule().fill(Color.secondary.opacity(0.15))).foregroundStyle(.secondary)
                                    .help("Bu kelimeyi ekip klasöründe \(rule.host) adlı Mac öğretti").accessibilityIdentifier("teamWordHost-\(rule.host)-\(rule.original)")
                                if !rule.teamNote.isEmpty { Text(rule.teamNote).font(.caption2).foregroundStyle(.secondary) }
                            }
                            Spacer()
                            if rule.isTeam {
                                Button(rule.enabled ? "Kapat" : "Aç") { Task { await model.toggleTeamWord(rule,enabled:!rule.enabled) } }.controlSize(.mini)
                                    .help(rule.enabled ? "Bu kelime bu Mac’te kendiliğinden düzeltilmesin; ekip klasöründeki hâline dokunulmaz" : "Bu kelime bu Mac’te yeniden uygulansın")
                                    .accessibilityIdentifier("toggleTeamWord-\(rule.host)-\(rule.original)")
                            } else {
                                Button("Unut") { Task { await model.forgetWord(rule.original) } }.controlSize(.mini).help("Bu kelime bir daha kendiliğinden düzeltilmez").accessibilityIdentifier("forgetWord-\(rule.original)")
                            }
                        }
                    }
                }.padding(12).meetingCard().accessibilityElement(children:.contain).accessibilityIdentifier("wordRulesList")
            }
            Text("Bir kelimeyi Düzelt penceresinde bir kez düzeltince buraya girer: sonraki toplantılarda aynı yazım kendiliğinden düzeltilir, yakın yazımlar Kontrol'e öneri olarak gelir. “Unut” kuralı kaldırır. Ekip klasörü açıksa ekip arkadaşlarınızın öğrettiği kelimeler de burada, öğreten Mac’in adıyla listelenir; “Kapat” onu yalnız bu Mac’te susturur, ekip klasöründeki hâline dokunmaz.").font(.caption2).foregroundStyle(.secondary)
        }.task { if model.wordRules.isEmpty { await model.loadWordRules() } }
    }
}

/// The only place the key was reachable used to be the OpenRouter import sheet, which nobody opens when they
/// merely want to paste a key. Same Keychain item, same save path — one compact row in Ayarlar → Sistem.
struct OpenRouterKeyRow:View {
    @State private var key=""
    /// Never `read()` here: a view initializer runs on every re-init of the settings sheet, and `read()` may open a
    /// Keychain dialog. The key file is the source of truth the app actually uses; the row only needs to know it exists.
    @State private var stored=OpenRouterCredential.cached() != nil
    @State private var message=""
    var body:some View {
        VStack(alignment:.leading,spacing:4) {
            HStack(spacing:8) {
                Text("OpenRouter anahtarı").font(.callout)
                SecureField(stored ? "Yeni anahtar girin" : "OpenRouter API anahtarı",text:$key)
                    .textFieldStyle(.roundedBorder).frame(width:240).accessibilityIdentifier("openRouterKeyField")
                    .onSubmit { save() }
                Button("Kaydet") { save() }.disabled(key.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty).accessibilityIdentifier("saveOpenRouterKeyButton")
                if stored { Label("Anahtar kayıtlı",systemImage:"checkmark.circle").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("openRouterKeyStored") }
            }
            if !stored && OpenRouterCredential.accessDenied {
                Text("Anahtar Zinciri erişimi reddedildi; anahtarı buraya yeniden girin.").font(.caption2).foregroundStyle(.secondary).accessibilityIdentifier("openRouterKeyDenied")
            }
            Text(message.isEmpty ? "Anahtar bu Mac’te yalnız size açık bir dosyada (openrouter.key) durur, yedeği macOS Anahtar Zinciri’ndedir; kayıtlıysa yeniden girmeniz gerekmez." : message).font(.caption2).foregroundStyle(.secondary)
        }
    }
    private func save() {
        do { try OpenRouterCredential.save(key); key=""; message="Anahtar kaydedildi." }
        catch { message=error.localizedDescription }
        stored=OpenRouterCredential.cached() != nil   // reflects what save() actually wrote, not what it intended to
    }
}

/// Read-only disk usage; deletion goes through the sidebar's existing confirmation. No automatic cleanup.
struct StorageSection:View {
    @ObservedObject var model:Model
    let storage:StorageReport
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            Text("Depolama").font(.headline)
            Text("Toplam \(StorageReport.format(bytes:storage.total)) · Kayıtlar \(StorageReport.format(bytes:storage.recordings)) · İçe aktarımlar \(StorageReport.format(bytes:storage.imports)) · Veritabanı \(StorageReport.format(bytes:storage.database))")
                .font(.caption).foregroundStyle(.secondary)
            if storage.meetings.isEmpty {
                Text("Ses dosyası olan toplantı yok.").font(.caption).foregroundStyle(.secondary)
            } else {
                Text("En büyük toplantılar").font(.caption.weight(.semibold))
                ForEach(storage.largest(5)) { entry in
                    HStack {
                        Text(entry.title.isEmpty ? "Adsız toplantı" : entry.title).lineLimit(1)
                        Spacer()
                        Text(StorageReport.format(bytes:entry.bytes)).monospacedDigit().foregroundStyle(.secondary)
                        Button("Sil…",role:.destructive) { model.requestDelete(meetingID:entry.meeting) }
                            .disabled(model.busy || entry.active)
                            .accessibilityIdentifier("storageDelete-\(entry.meeting)")
                    }.font(.callout)
                }
                Text("Silme, arşivdeki onay penceresinden yapılır.").font(.caption2).foregroundStyle(.secondary)
            }
            Divider()
            HStack { Button("Sesleri sıkıştır") { Task { await model.compactStorage() } }.disabled(model.busy || model.recording).accessibilityIdentifier("compactStorageButton"); Text("Tamamlanmış kayıtlarda ham 12 saniyelik parçalar silinir ve birleştirilmiş ses kayıpsız FLAC’e çevrilir (≈3–4× küçülür; çalma ve ses profili aynen çalışır). Yeni kayıtlarda kendiliğinden yapılır.").font(.caption2).foregroundStyle(.secondary) }
        }.frame(maxWidth:.infinity,alignment:.leading).padding(16).meetingCard()
    }
}

/// Deleting old audio is a once-a-quarter decision, so it lives under Ayarlar → Sistem → Gelişmiş rather than
/// next to the disk totals everybody reads. Same controls, same identifiers.
struct StorageCleanupSection:View {
    @ObservedObject var model:Model
    let storage:StorageReport
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            HStack(spacing:8) {
                Text("Eski toplantıların sesi").font(.callout)
                Picker("",selection:Binding(get:{ model.reportSettings.audioRetentionDays },set:{ v in model.reportSettings.audioRetentionDays=v; Task { await model.saveReportSettings() } })) { Text("silinmesin").tag(0); Text("14 gün sonra").tag(14); Text("30 gün sonra").tag(30); Text("60 gün sonra").tag(60); Text("90 gün sonra").tag(90) }.labelsHidden().frame(width:150).accessibilityIdentifier("audioRetentionPicker")
                Text("silinir; yazı, özet ve görevler kalır. “Sesi koru” işaretli toplantılara dokunulmaz. Saatte bir, kayıt yokken çalışır.").font(.caption2).foregroundStyle(.secondary)
            }
            Text("Eski sesleri temizle").font(.caption.weight(.semibold))
            Text("Transkript, özet, görevler ve ses profilleri kalır; yalnız tamamlanmış eski toplantıların ses dosyaları silinir. “Sesi koru” işaretli toplantılara dokunulmaz. Önce liste gösterilir.").font(.caption2).foregroundStyle(.secondary)
            HStack {
                Picker("Şundan eski",selection:$model.cleanupDays) { Text("30 gün").tag(30);Text("60 gün").tag(60);Text("90 gün").tag(90);Text("180 gün").tag(180) }.frame(width:200)
                Button("Silineceklere bak") { Task { await model.previewCleanup() } }.disabled(model.busy)
            }
            if let p=model.cleanupPreview {
                if p.count==0 { Text("\(p.days) günden eski, sesi silinebilecek toplantı yok.").font(.caption) }
                else {
                    Text("\(p.count) toplantının sesi silinecek · \(StorageReport.format(bytes:p.bytes)) boşalır · \(p.titles.joined(separator:", "))\(p.count>p.titles.count ? " …" : "")").font(.caption)
                    Button("Sesleri sil (\(StorageReport.format(bytes:p.bytes)))",role:.destructive) { Task { await model.runCleanup() } }.disabled(model.busy).accessibilityIdentifier("runCleanupButton")
                }
            }
            if let meeting=model.meeting {
                Toggle("Seçili toplantının sesini koru (“\(meeting.title)”)",isOn:Binding(get:{ meeting.metadata["keep"] as? Bool ?? false },set:{ v in Task { await model.keepMeeting(meeting.id,keep:v) } })).font(.caption)
            }
            Divider()
        }
    }
}
