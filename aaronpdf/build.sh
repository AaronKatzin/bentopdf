#!/usr/bin/env bash
# Build AaronPDF from this checkout: upstream static build, then prune + rebrand.
# Output is aaronpdf/site/, which wrangler.jsonc deploys.
set -euo pipefail

cd "$(dirname "$0")/.."

export HUSKY=0
export BASE_URL="${BASE_URL:-/pdf/}"
export COMPRESSION_MODE="${COMPRESSION_MODE:-o}"
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=4096}"
if [[ -z "${AARONPDF_COMMIT:-}" ]]; then
  AARONPDF_COMMIT="$(git rev-parse HEAD)"
  export AARONPDF_COMMIT
fi

python3 -c "import PIL" || {
  echo "Pillow is required (python3 -m pip install pillow)" >&2
  exit 1
}

npm run build
node scripts/assemble-dist-branch.mjs --out dist-publish
python3 aaronpdf/prepare_site.py dist-publish aaronpdf/site
python3 aaronpdf/smoke.py aaronpdf/site
