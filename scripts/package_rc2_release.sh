#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

out_root="${repo_root}/artifacts/rc2-release"
stage="${out_root}/research-drive-rc2"
archive="${repo_root}/artifacts/research-drive-rc2-public.tar.gz"
archive_checksum="${archive}.sha256"
attestation="${repo_root}/artifacts/rc2-release-verification.json"

rm -rf "${stage}" "${archive}" "${archive_checksum}"
mkdir -p "${stage}/docs/releases" "${repo_root}/artifacts"

if [[ "${YZU_REUSE_RELEASE_VERIFICATION:-0}" == "1" ]]; then
  node scripts/verify_rc2_release.mjs --attestation-only
else
  npm run release:verify
fi
npm run build

cp -R dist "${stage}/dist"
cp release/research-drive-rc2.json "${stage}/release-manifest.json"
cp "${attestation}" "${stage}/release-verification.json"
cp docs/releases/RESEARCH_DRIVE_RC2.md "${stage}/docs/releases/"
cp docs/releases/RC2_OPERATOR_QUICKSTART.md "${stage}/docs/releases/"
cp README.md "${stage}/README.md"

(
  cd "${stage}"
  find . -type f ! -name SHA256SUMS ! -name FILELIST.txt -print | LC_ALL=C sort > FILELIST.txt
  while IFS= read -r file; do
    sha256sum "${file}"
  done < FILELIST.txt > SHA256SUMS
  sha256sum -c SHA256SUMS
)

# GNU tar options make the archive reproducible across clean Linux CI runs.
tar \
  --sort=name \
  --mtime='UTC 2026-07-21 00:00:00' \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  -czf "${archive}" \
  -C "${out_root}" \
  research-drive-rc2

(
  cd "$(dirname "${archive}")"
  sha256sum "$(basename "${archive}")" > "$(basename "${archive_checksum}")"
  sha256sum -c "$(basename "${archive_checksum}")"
)

echo "RC2 package: ${archive}"
echo "Checksum:   ${archive_checksum}"
echo "Staged:     ${stage}"
