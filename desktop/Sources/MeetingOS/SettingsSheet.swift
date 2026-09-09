import SwiftUI
import AppKit

struct SettingsSheet:View {
    @ObservedObject var model:Model
    @AppStorage("settingsSection") private var section="genel"
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:16) {
                HStack { Text("Ayarlar").font(.title2.bold()); Spacer(); Text("⌘,").font(.caption.monospaced()).foregroundStyle(.secondary) }
                Picker("Ayar grubu",selection:$section) { Text("Genel").tag("genel"); Text("Sözlük ve sesler").tag("sozluk"); Text("Depolama").tag("depolama"); Text("Güncelleme ve raporlar").tag("guncelleme"); Text("Kurulum durumu").tag("durum") }.pickerStyle(.segmented).labelsHidden().accessibilityIdentifier("settingsSection")
                if section=="durum" {
                if !model.setupChecks.isEmpty {
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
                        Text("Uygulama yoklaması · \(BridgeStats.shared.summary)").font(.caption2).foregroundStyle(.secondary).help("Python köprüsüne yapılan çağrıların süresi; p95 birkaç yüz ms üzerindeyse Mac yavaşlamış demektir")
                    }.padding(14).meetingCard().accessibilityElement(children:.contain).accessibilityIdentifier("setupStatus")
                }
                }
                if section=="sozluk" {
                Text("Kişi adlarını ve özel terimleri her satıra bir tane yazın.")
                TextEditor(text:$model.vocabulary).font(.body.monospaced()).frame(height:160).border(.quaternary)
                Text("Proje sözlüğü (glossary.jsonl)").font(.headline)
                Text(model.glossaryFromFile>0 ? "\(model.glossaryFromFile) terim dosyadan, toplam \(model.glossaryCount) · örnek: \(model.glossarySample.prefix(6).joined(separator:", ")) · iCloud Drive ile bütün Mac’lerde aynı" : "Henüz sözlük dosyası yok. Slack agent’ın ürettiği JSON Lines dosyasını içe aktarın; iCloud Drive üzerinden bütün Mac’lere yayılır.").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button("glossary.jsonl içe aktar…") { Task { await model.importGlossary() } }.accessibilityIdentifier("importGlossaryButton")
                    Text("Sözlük üç yerde kullanılır: bulut STT’ye yazım ipucu (etkisi sağlayıcıya bağlı), transkript sonrası düzeltme önerileri (Kontrol), özetlerde kısaltma açılımı. Ham metin hiçbir zaman kendiliğinden değiştirilmez.").font(.caption2).foregroundStyle(.secondary)
                }
                }
                if section=="guncelleme" {
                if let cost=model.cost, let month=cost["month"] as? [String:Any], let all=cost["all"] as? [String:Any] {
                    VStack(alignment:.leading,spacing:6) {
                        Text("Bulut maliyeti").font(.headline)
                        HStack(spacing:12) {
                            SmallMetric(value:String(format:"$%.2f",month["usd"] as? Double ?? 0),label:"Bu ay · \(month["meetings"] as? Int ?? 0) toplantı, \(Int(month["minutes"] as? Double ?? 0)) dk",icon:"cloud")
                            SmallMetric(value:String(format:"$%.2f",all["usd"] as? Double ?? 0),label:"Toplam · \(all["meetings"] as? Int ?? 0) toplantı, \(Int(all["minutes"] as? Double ?? 0)) dk",icon:"sum")
                        }
                        Text("OpenRouter’ın bildirdiği transkript ücretleri (≈ $0.10/saat MAI-Transcribe 2). Özet/görev analizi ve yankı olarak atlanan parçalar dahil değildir.").font(.caption2).foregroundStyle(.secondary)
                    }
                }
                Text("Güncelleme ve raporlar").font(.headline)
                Text(model.update?.headline ?? "Sürüm kontrolü yapılmadı").font(.caption).foregroundStyle(.secondary)
                Text("Yeni sürüm varsa kenar çubuğunda ve menü çubuğu simgesinde “Güncelle ve yeniden başlat” görünür; güncelken düğme yoktur. Kontrol açılışta, uygulama öne gelince ve 15 dakikada bir yapılır.").font(.caption2).foregroundStyle(.secondary)
                HStack {
                    Button("Şimdi kontrol et") { Task { await model.checkForUpdates(force:true) } }
                    if model.update?.available==true { Button(model.zoomMeetingOpen ? "Güncelleme toplantı bitince" : "Güncelle ve yeniden başlat") { model.startUpdate() }.disabled(model.busy || model.recording || model.zoomMeetingOpen) }
                }
                Toggle("Yeni sürüm bulununca açılışta kendiliğinden güncelle (kayıt yokken)",isOn:$model.reportSettings.autoUpdate).onChange(of:model.reportSettings.autoUpdate) { _ in Task { await model.saveReportSettings() } }
                Toggle("Her toplantıdan sonra teşhis raporunu paylaşılan klasöre yaz",isOn:$model.reportSettings.shareReports).onChange(of:model.reportSettings.shareReports) { _ in Task { await model.saveReportSettings() } }
                Toggle("Raporlara transkript metnini de ekle (varsayılan kapalı)",isOn:$model.reportSettings.shareText).onChange(of:model.reportSettings.shareText) { _ in Task { await model.saveReportSettings() } }
                HStack {
                    Text(model.reportSettings.reportDir.replacingOccurrences(of:NSHomeDirectory(),with:"~")).font(.caption2.monospaced()).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                    Spacer()
                    Button("Rapor klasörünü aç") { NSWorkspace.shared.open(URL(fileURLWithPath:model.reportSettings.reportDir)) }
                }
                Text("Raporlar yalnız sayı, puan, maliyet, model adı ve hata satırı içerir; iCloud Drive üzerinden diğer Mac’e geçer. Geliştirme oradaki raporlara bakılarak sürer.").font(.caption2).foregroundStyle(.secondary)
                }
                if section=="sozluk" {
                Text("Kaydedilmiş sesler").font(.headline)
                Text("Aynı isimde farklı kişiler için ayırt edici bir ad kullanın (ör. Ali Tasarım). Yeni bir profil, aynı isimdeki mevcut kişinin ses örneklerine eklenir.").font(.caption).foregroundStyle(.secondary)
                if model.profiles.isEmpty {
                    VStack(alignment:.leading,spacing:6) {
                        Label("Henüz ses profili yok",systemImage:"person.wave.2")
                        Text("Bir transkript bölümünde Düzelt düğmesine basarak temiz bir konuşma örneğinden profil kaydedebilirsiniz.").font(.caption).foregroundStyle(.secondary)
                    }.frame(maxWidth:.infinity,alignment:.leading).padding(16).meetingCard()
                } else { VStack(alignment:.leading,spacing:4) { ForEach(model.profiles) { p in ProfileMaintenanceRow(model:model,profile:p) } }.padding(12).meetingCard() }
                }
                if section=="genel" {
                Text("Sizin adınız").font(.headline)
                HStack(spacing:10) {
                    TextField("Adınız",text:$model.reportSettings.userName)
                        .textFieldStyle(.roundedBorder).frame(width:220)
                        .accessibilityIdentifier("userNameField")
                        .onSubmit { Task { await model.saveReportSettings() } }
                        .onDisappear { Task { await model.saveReportSettings() } }   // saved once when the field goes away, not on every keystroke
                    Text("Mikrofon kaydı bu adla etiketlenir; “Bana ait” filtresi bu adı kullanır.").font(.caption2).foregroundStyle(.secondary)
                }
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
                Toggle("Zoom toplantı penceresi açılınca kaydı kendiliğinden başlat, pencere kapanınca 1 dk sonra bitir (elle başlatılan kayıtlara dokunmaz)",isOn:$model.zoomAutoRecord)
                Toggle("Kayıt sırasında her pencerenin üstünde küçük kayıt paneli göster (süre, an işaretleri, bitir)",isOn:$model.showRecorderPanel)
                Toggle("Kayıt başlarken takvimdeki toplantının adını başlık yap, katılımcılarını adlandırmada öner (takvim yalnız okunur)",isOn:$model.useCalendar)
                }
                if section=="depolama" {
                if let storage=model.storage { StorageSection(model:model,storage:storage) }
                }
                HStack {
                    Button("Veri klasörünü aç") { NSWorkspace.shared.open(model.dataDir) }
                    Spacer()
                    if section=="sozluk" { Button("Sözlüğü kaydet") { Task { await model.saveVocabulary() } }.buttonStyle(.borderedProminent).accessibilityIdentifier("saveSettingsButton") }
                    Button("Kapat") { model.showSettings=false }.keyboardShortcut(.cancelAction).accessibilityIdentifier("cancelSettingsButton")
                }
            }.padding(28)
        }.scrollIndicators(.visible).frame(width:640,height:min(["genel":470,"sozluk":820,"depolama":700,"guncelleme":620,"durum":660][section] ?? 700,(NSScreen.main?.visibleFrame.height ?? 900)-80))
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
            HStack(spacing:8) {
                Text("Eski toplantıların sesi").font(.callout)
                Picker("",selection:Binding(get:{ model.reportSettings.audioRetentionDays },set:{ v in model.reportSettings.audioRetentionDays=v; Task { await model.saveReportSettings() } })) { Text("silinmesin").tag(0); Text("14 gün sonra").tag(14); Text("30 gün sonra").tag(30); Text("60 gün sonra").tag(60); Text("90 gün sonra").tag(90) }.labelsHidden().frame(width:150).accessibilityIdentifier("audioRetentionPicker")
                Text("silinir; yazı, özet ve görevler kalır. “Sesi koru” işaretli toplantılara dokunulmaz. Saatte bir, kayıt yokken çalışır.").font(.caption2).foregroundStyle(.secondary)
            }
            Divider()
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
        }.frame(maxWidth:.infinity,alignment:.leading).padding(16).meetingCard()
    }
}
