#!/bin/zsh
set -euo pipefail
here=${0:A:h}
studio=${here:h}
if [[ "${1:-}" != "--skip-web" ]]; then npm --prefix "$studio/web" run build; fi
app="${KARAOKE_APP_OUTPUT:-$studio/KaraokeStudio-11月7日.app}"
mkdir -p "$app/Contents/MacOS"
if [[ ! -f "$app/Contents/Info.plist" ]]; then
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Karaoke Studio</string>
<key>CFBundleIdentifier</key><string>local.karaokestudio.desktop</string>
<key>CFBundleExecutable</key><string>KaraokeStudioLauncher</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2.0</string>
<key>LSUIElement</key><false/>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
fi
/usr/bin/swiftc "$here/DesktopHost-11月7日.swift" -o "$app/Contents/MacOS/KaraokeStudioLauncher" -framework Cocoa -framework WebKit -parse-as-library
/usr/libexec/PlistBuddy -c 'Set :LSUIElement false' "$app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleShortVersionString 0.2.0' "$app/Contents/Info.plist"
/usr/bin/codesign --force --deep --sign - "$app"
