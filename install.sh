#!/usr/bin/env bash
set -euo pipefail

project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mamba_command=$(command -v mamba)
ytamp_checkout=${YTAMP_CHECKOUT:-"$project/../ytamp"}
if [[ ! -d "$ytamp_checkout/ytamp" ]]; then
    git clone https://github.com/digonto10602/ytamp "$ytamp_checkout"
fi
ytamp_checkout=$(cd -- "$ytamp_checkout" && pwd)

bin_dir="$HOME/.local/bin"
app_dir="${XDG_DATA_HOME:-"$HOME/.local/share"}/applications"
mkdir -p -- "$bin_dir" "$app_dir"
launcher="$bin_dir/ytchords"
{
    printf '%s\n' '#!/usr/bin/env bash'
    printf 'export PYTHONPATH=%q\n' "$project:$ytamp_checkout"
    printf 'exec %q run -n ytchords python -m ytchords "$@"\n' "$mamba_command"
} > "$launcher"
chmod +x "$launcher"
escaped=${launcher//\\/\\\\}
escaped=${escaped//\"/\\\"}
escaped=${escaped//\$/\\\$}
escaped=${escaped//\`/\\\`}
cat > "$app_dir/org.omarchy.ytchords.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=ytchords
Comment=Find guitar chords from YouTube audio
Exec=omarchy launch tui --app-id=org.omarchy.ytchords "$escaped" --launcher
Icon=audio-x-generic
Terminal=false
Categories=AudioVideo;Audio;
DESKTOP
