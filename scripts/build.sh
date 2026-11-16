set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
uv python install
uv sync --locked
PYTHON_EXECUTABLE="$(uv run --locked python -c 'import sys; print(sys.executable)')"
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE="$PYTHON_EXECUTABLE" "$@"
cmake --build build --parallel 2
