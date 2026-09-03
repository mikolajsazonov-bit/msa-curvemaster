#!/bin/bash
# =============================================================================
# Skrypt pakujący wtyczkę MSA: CurveMaster do pliku ZIP (zgodny z plugins.qgis.org)
# =============================================================================

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION=$(grep "^version=" "$PLUGIN_DIR/metadata.txt" | cut -d= -f2 | tr -d ' \r\n')
ZIP_NAME="msa_curvemaster.${VERSION}.zip"
OUT_DIR="$PLUGIN_DIR/dist"

echo "=== Pakowanie wtyczki MSA: CurveMaster (wersja $VERSION) ==="

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/$ZIP_NAME"

TMP_STAGE="$(mktemp -d)"
mkdir -p "$TMP_STAGE/msa_curvemaster"

# Kopiowanie plików wtyczki
cp "$PLUGIN_DIR/metadata.txt" "$TMP_STAGE/msa_curvemaster/"
cp "$PLUGIN_DIR/__init__.py" "$TMP_STAGE/msa_curvemaster/"
cp "$PLUGIN_DIR/plugin.py" "$TMP_STAGE/msa_curvemaster/"
cp "$PLUGIN_DIR/icon.png" "$TMP_STAGE/msa_curvemaster/"
cp "$PLUGIN_DIR/icon.svg" "$TMP_STAGE/msa_curvemaster/"
cp "$PLUGIN_DIR/README.md" "$TMP_STAGE/msa_curvemaster/"

cp -r "$PLUGIN_DIR/core" "$TMP_STAGE/msa_curvemaster/"
cp -r "$PLUGIN_DIR/gui" "$TMP_STAGE/msa_curvemaster/"
cp -r "$PLUGIN_DIR/tools" "$TMP_STAGE/msa_curvemaster/"
cp -r "$PLUGIN_DIR/icons" "$TMP_STAGE/msa_curvemaster/"

# Usunięcie zbędnych plików systemowych
find "$TMP_STAGE" -name ".DS_Store" -delete 2>/dev/null || true
find "$TMP_STAGE" -name "._*" -delete 2>/dev/null || true
find "$TMP_STAGE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Budowa archiwum ZIP
(cd "$TMP_STAGE" && zip -r "$OUT_DIR/$ZIP_NAME" msa_curvemaster -x "*.git*" "*__pycache__*" "*.DS_Store*")

rm -rf "$TMP_STAGE"

echo "✓ Wygenerowano paczkę produkcyjną:"
echo "  -> $OUT_DIR/$ZIP_NAME"
