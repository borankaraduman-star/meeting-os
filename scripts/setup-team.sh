#!/bin/sh
# İkinci geliştiriciyi depoya al ve v0.1'i koru. Bir kez, depo sahibi çalıştırır (repo ayarı değiştirir).
#
#     sh scripts/setup-team.sh <github-kullanıcı-adı>
#
# Ne yapar: (1) kullanıcıyı push yetkisiyle davet eder, (2) v0.1'e dal koruması koyar — PR zorunlu, iki CI işi
# (python, swift) yeşil olmalı, bir onay gerekir, force-push ve silme kapalı. `enforce_admins` KAPALI: depo
# sahibi `scripts/release.sh`'in doğrudan push'unu yapmaya devam edebilir; kural arkadaşınız için işler.
set -eu
USER_LOGIN=${1:-}
REPO=${MEETING_OS_REPO:-borankaraduman-star/meeting-os}
[ -n "$USER_LOGIN" ] || { echo "kullanım: sh scripts/setup-team.sh <github-kullanıcı-adı>" >&2; exit 2; }
command -v gh >/dev/null || { echo "gh yok: brew install gh && gh auth login" >&2; exit 1; }

echo "==> 1/2 $USER_LOGIN depoya davet ediliyor (push yetkisi)"
gh api -X PUT "repos/$REPO/collaborators/$USER_LOGIN" -f permission=push >/dev/null
echo "    davet gönderildi; $USER_LOGIN e-postasından kabul etmeli"

echo "==> 2/2 v0.1 dal koruması"
gh api -X PUT "repos/$REPO/branches/v0.1/protection" --input - >/dev/null <<'JSON'
{
  "required_status_checks": {"strict": false, "contexts": ["python", "swift"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {"required_approving_review_count": 1, "dismiss_stale_reviews": true, "require_code_owner_reviews": false},
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON
gh api "repos/$REPO/branches/v0.1/protection" \
  --jq '"    zorunlu kontroller: \(.required_status_checks.contexts|join(", ")) · onay: \(.required_pull_request_reviews.required_approving_review_count) · yönetici muaf: \(.enforce_admins.enabled|not)"'
echo "tamam — arkadaşınız artık dal açıp PR gönderebilir (docs/GELISTIRME.md)"
