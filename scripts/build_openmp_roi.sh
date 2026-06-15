#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT_DIR/src/hpc/openmp_roi.cpp"
OUT="$ROOT_DIR/build/openmp_roi"
mkdir -p "$(dirname "$OUT")"

if [[ ! -f "$SRC" ]]; then
  echo "missing source: $SRC" >&2
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  CXX_BIN="${CXX:-/opt/homebrew/opt/llvm/bin/clang++}"
  SDKROOT_PATH="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path 2>/dev/null || true)}"
  if [[ ! -x "$CXX_BIN" ]]; then
    echo "Homebrew LLVM clang++ not found. Install with: brew install llvm libomp" >&2
    exit 1
  fi
  cmd=("$CXX_BIN" -O3 -std=c++17 -fopenmp)
  if [[ -n "$SDKROOT_PATH" ]]; then
    cmd+=(-isysroot "$SDKROOT_PATH")
  fi
  cmd+=(
    -I/opt/homebrew/opt/libomp/include
    -L/opt/homebrew/opt/libomp/lib
    -Wl,-rpath,/opt/homebrew/opt/libomp/lib
    "$SRC" -o "$OUT"
  )
  "${cmd[@]}"
else
  CXX_BIN="${CXX:-g++}"
  "$CXX_BIN" -O3 -std=c++17 -fopenmp "$SRC" -o "$OUT"
fi

chmod +x "$OUT"
echo "built $OUT"
