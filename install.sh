#!/bin/sh
set -e
ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
BIN_DIR="${1:-$HOME/.local/bin}"

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/rapi" << WRAP
#!/bin/sh
export PYTHONPATH="$ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m rapi "\$@"
WRAP
chmod 755 "$BIN_DIR/rapi" 2>/dev/null || true

echo "Installed: $BIN_DIR/rapi"
echo ""
echo "Make sure $BIN_DIR is in your PATH:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
echo ""
echo "Then use:"
echo "  rapi --help"
echo "  rapi host /sample get -r '{\"ok\":true}'"
echo "  rapi start"
