import Foundation

/// Why a task field changed, when the user says so.
///
/// "Model yanlış çıkardı" and "iş sonradan devredildi/ertelendi" look identical in the data and mean opposite
/// things: the first is a model error worth learning from, the second is a meeting doing what meetings do.
/// Turning every edit into a correction label would teach the model that half of reality is its own mistake
/// (Codex, 11 Sep 2026, P0 #3).
///
/// The default is `.unsaid`, and it stays that way unless the user picks: nobody is made to answer a question
/// to save their own task, and an unexplained change is never used as a training label.
enum TaskEditReason: String, CaseIterable, Identifiable {
    case unsaid = ""
    case inferenceError = "inference_error"
    case changedLater = "changed_later"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .unsaid: return "Belirtilmedi"
        case .inferenceError: return "Çıkarım hatası"
        case .changedLater: return "Sonradan değişti"
        }
    }

    /// The two the edit sheet offers as radio buttons. "Belirtilmedi" is the state, not a third button.
    static var choices: [TaskEditReason] { [.inferenceError, .changedLater] }

    /// What the bridge is sent. `nil` when the user said nothing: `memory.update_action` accepts no empty
    /// string, and a key that is not there is the honest way to say "unknown".
    var payload: String? { self == .unsaid ? nil : rawValue }

    /// Clicking the selected button again clears it — this is a two-button radio with no "neither" button,
    /// so the only way back to "Belirtilmedi" is the button itself.
    func toggled(_ choice: TaskEditReason) -> TaskEditReason { self == choice ? .unsaid : choice }
}
