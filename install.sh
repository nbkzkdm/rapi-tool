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

# Optional runtime deps (OpenAPI YAML support)
if [ -f "$ROOT/requirements.txt" ]; then
  if command -v pip3 >/dev/null 2>&1; then
    echo "Installing Python dependencies (requirements.txt)..."
    pip3 install -r "$ROOT/requirements.txt" || \
      echo "Warning: pip install failed. OpenAPI YAML may need: pip install pyyaml"
  elif command -v pip >/dev/null 2>&1; then
    echo "Installing Python dependencies (requirements.txt)..."
    pip install -r "$ROOT/requirements.txt" || \
      echo "Warning: pip install failed. OpenAPI YAML may need: pip install pyyaml"
  else
    echo "Note: pip not found. For OpenAPI YAML support: pip install -r requirements.txt"
  fi
fi

echo "Installed: $BIN_DIR/rapi"
echo ""
echo "Make sure $BIN_DIR is in your PATH:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
echo ""
echo "Then use:"
echo "  rapi --help"
echo "  rapi host /sample get -r '{\"ok\":true}'"
echo "  rapi start"
