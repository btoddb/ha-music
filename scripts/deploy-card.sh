#!/usr/bin/env bash
# Build the BToddB HA Music Lovelace card and deploy it into the
# integration's www/ directory.
#
# The integration serves the card at /btoddb_ha_music/ and auto-registers
# it as a frontend module (add_extra_js_url) with no-cache headers, so after this
# runs you only need to HARD-REFRESH the browser — there is no Lovelace resource
# to add and no Home Assistant restart required.
#
# Requires Node/npm (provided by the devcontainer's Node feature).

SCRIPTS_DIR=$(cd $(dirname $0); pwd)
HOME_DIR=$(dirname ${SCRIPTS_DIR})
echo "home dir = ${HOME_DIR}"

set -euo pipefail

CARD_DIR="${HOME_DIR}/custom_components/btoddb_ha_music/card"
COMPONENT_WWW="$(cd "$CARD_DIR/.." && pwd)/www"
cd "$CARD_DIR"

# --- 1. Install deps first (clean, correct-platform native binaries). This is the
#        most failure-prone step and does not depend on the version, so running it
#        before the bump means a network/install failure leaves the tree untouched. ---
echo "Installing dependencies..."
npm install

# --- 2. Bump patch version (package.json) and sync the console banner so you can
#        confirm in the browser console which build actually loaded. The version is
#        compiled into the bundle, so it must be bumped before the build. Back up the
#        two touched files and roll them back if the build/deploy fails, so a broken
#        build never leaves a bumped-but-unbuilt (dirty, inconsistent) tree. ---
PKG_BACKUP="$(mktemp)"
LOCK_BACKUP="$(mktemp)"
IDX_BACKUP="$(mktemp)"
cp package.json "$PKG_BACKUP"
cp package-lock.json "$LOCK_BACKUP"
cp src/index.ts "$IDX_BACKUP"
rollback() {
    echo "ERROR: build/deploy failed — rolling back the version bump." >&2
    cp "$PKG_BACKUP" package.json
    cp "$LOCK_BACKUP" package-lock.json
    cp "$IDX_BACKUP" src/index.ts
    rm -f "$PKG_BACKUP" "$LOCK_BACKUP" "$IDX_BACKUP"
}
trap rollback ERR

OLD_VERSION=$(python3 -c "import json; print(json.load(open('package.json'))['version'])")
NEW_VERSION=$(python3 -c "p='${OLD_VERSION}'.split('.'); p[2]=str(int(p[2])+1); print('.'.join(p))")
python3 - "$NEW_VERSION" <<'PYEOF'
import json, re, sys
new = sys.argv[1]
data = json.load(open("package.json"))
data["version"] = new
open("package.json", "w").write(json.dumps(data, indent=2) + "\n")
src = open("src/index.ts").read()
src = re.sub(r"v\d+\.\d+\.\d+", f"v{new}", src, count=1)
open("src/index.ts", "w").write(src)
PYEOF
echo "Version: $OLD_VERSION -> $NEW_VERSION"

# Sync package-lock.json's version to the bump. npm only rewrites the lock when
# it runs, and step 1's install happened before the bump, so without this the
# lock stays one version behind. Deps are already installed, so this only
# refreshes the lock's version fields (no network, no node_modules changes).
npm install --package-lock-only

# --- 3. Build. ---
echo "Building..."
npm run build

# --- 4. Deploy the bundle into the component's www/ directory. ---
echo "Deploying to $COMPONENT_WWW ..."
mkdir -p "$COMPONENT_WWW"
cp btoddb_ha_music.js btoddb_ha_music.js.map "$COMPONENT_WWW/"

# Success: drop the rollback trap and discard the backups.
trap - ERR
rm -f "$PKG_BACKUP" "$LOCK_BACKUP" "$IDX_BACKUP"

echo "Done (v$NEW_VERSION). Hard-refresh your browser (Ctrl+Shift+R) to load the new card."
