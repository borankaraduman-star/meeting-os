import Foundation

/// The analysis model the app starts with, and the one-time move off the old default. 11 Sep 2026 benchmark
/// (scripts/benchmark-compare-models.py): DeepSeek V3.2 30/30 fictional cases in three runs, gpt-4.1-mini 26/30 with
/// one leak, at half the price. A Mac whose stored value is still the OLD default never chose it — it is moved once;
/// a Mac that picked anything else keeps its choice.
enum AnalysisModelDefault {
    static let model="deepseek/deepseek-v3.2"
    static let legacy="openai/gpt-4.1-mini"
    static let key="cloudAnalysisModel"
    static let migratedKey="cloudAnalysisModelMoved1269"
    static func current(defaults:UserDefaults = .standard)->String {
        resolve(stored:defaults.string(forKey:key),migrated:defaults.bool(forKey:migratedKey)) { value in
            if let value { defaults.set(value,forKey:key) } else { defaults.removeObject(forKey:key) }
            defaults.set(true,forKey:migratedKey)
        }
    }
    /// Pure rule: (stored value, already migrated) → the model to use; `write` is called once when the stored value moves.
    static func resolve(stored:String?,migrated:Bool,write:(String?)->Void)->String {
        if !migrated {
            if stored==legacy { write(nil); return model }   // the old default, never a choice
            write(stored)
        }
        return stored ?? model
    }
}
