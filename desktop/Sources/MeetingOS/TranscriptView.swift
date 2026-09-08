import SwiftUI

struct TranscriptView:View {
    @ObservedObject var model:Model
    var body:some View {
        ScrollView {
            LazyVStack(alignment:.leading,spacing:20) {
                ForEach(model.filteredRows) { row in TranscriptRow(model:model,row:row) }
                if model.filteredRows.isEmpty { TranscriptEmptyView(model:model).padding(32) }
            }.padding(24)
        }
    }
}

struct TranscriptRow:View {
    @ObservedObject var model:Model
    let row:Row
    var body:some View {
        HStack(alignment:.top,spacing:14) {
            Button { model.play(row) } label:{
                VStack(spacing:8) {
                    Image(systemName:"play.circle.fill").font(.title2).foregroundStyle(MeetingStyle.accent)
                    Text(row.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }.frame(width:48)
            }
            .buttonStyle(.plain).help("Bu bölümü dinle")
            .disabled(model.recording || model.meeting?.metadata["text_only"] as? Bool == true)
            .accessibilityIdentifier("playSegment-\(row.id)")
            .accessibilityLabel("Bu bölümü dinle, \(row.time)")
            VStack(alignment:.leading,spacing:7) {
                ViewThatFits(in:.horizontal) {
                    HStack {
                        Text(row.label).font(.headline).lineLimit(1)
                        Text(row.source=="mic" ? "Mikrofon":"Sistem sesi").font(.caption).foregroundStyle(.secondary)
                        Spacer(minLength:12)
                        editButton
                    }
                    VStack(alignment:.leading,spacing:4) {
                        HStack { Text(row.label).font(.headline).lineLimit(1);Spacer();editButton }
                        Text(row.source=="mic" ? "Mikrofon":"Sistem sesi").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Text(row.text).font(.system(size:15)).textSelection(.enabled).lineSpacing(6)
                if !row.flags.isEmpty { Label(row.notices,systemImage:"exclamationmark.triangle").font(.caption2).foregroundStyle(.orange) }
            }
        }.padding(20).meetingCard()
    }
    var editButton:some View {
        Button("Düzelt") { model.editRow=row;model.editName=row.name;model.editText=row.text;model.clean=false }
            .disabled(model.meeting?.status != "complete")
            .accessibilityIdentifier("editSegment-\(row.id)")
            .accessibilityLabel("Bölümü düzelt: \(row.label)")
    }
}
