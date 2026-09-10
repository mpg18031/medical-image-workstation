#!/usr/bin/env bash
# Compile GLSL shaders to SPIR-V outside the CMake build, for quick iteration.
# The authoritative compilation happens in core/vulkan/CMakeLists.txt.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHADER_DIR="$REPO_ROOT/core/vulkan/shaders"
OUT_DIR="${1:-$REPO_ROOT/core/build/spv}"

command -v glslc >/dev/null 2>&1 || {
  echo "glslc not found; install the Vulkan SDK" >&2
  exit 1
}

mkdir -p "$OUT_DIR"

status=0
shopt -s nullglob
for shader in "$SHADER_DIR"/*.{vert,frag,comp,geom,tesc,tese}; do
  name="$(basename "$shader")"
  if glslc --target-env=vulkan1.3 -O -Werror "$shader" -o "$OUT_DIR/$name.spv"; then
    printf '  ok   %s\n' "$name"
  else
    printf '  FAIL %s\n' "$name" >&2
    status=1
  fi
done

exit "$status"
