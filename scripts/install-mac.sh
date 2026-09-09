#!/bin/bash
# Eski ad: "Meeting OS.command" ve belgeler bunu çağırıyordu. Tek kurulum yolu artık scripts/install.sh.
set -euo pipefail
exec /bin/sh "$(dirname "$0")/install.sh" "$@"
