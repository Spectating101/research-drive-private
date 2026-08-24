#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 RUN_ID WINDOWS_HOSTNAME_OR_IP" >&2
  echo "example: $0 asia_gkg_window_20191201_20200101_20260526Tbackfill2018_2023Z DESKTOP-VEFGGDH" >&2
  exit 2
fi

run_id="$1"
node_selector="$2"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

inventory="${CLUSTER_INVENTORY:-/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv}"
key="${CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
remote_user_default="${CLUSTER_USER:-user}"
remote_job_root="${WINDOWS_JOB_ROOT:-C:\\ClusterData\\SharpeWorkers\\jobs}"
chunk_size="${CHUNK_SIZE:-50000}"
sample_size="${SAMPLE_SIZE:-200}"
blas_threads="${BLAS_THREADS:-2}"
force="${FORCE:-0}"

normalized_file="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}/asia_gkg_filtered.csv.gz"
proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"
scored_file="${proc_dir}/asia_gkg_scored.csv.gz"
daily_panel_file="${proc_dir}/daily_country_shock_panel.csv"
url_queue_file="${proc_dir}/url_enrichment_queue.csv.gz"

if [[ ! -s "${normalized_file}" ]]; then
  echo "missing_normalized_input=${normalized_file}" >&2
  exit 1
fi

if [[ "${force}" != "1" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] && gzip -t "${scored_file}" && gzip -t "${url_queue_file}"; then
  echo "score_outputs_already_exist=${proc_dir}"
  exit 0
fi

hostname=""
ip=""
remote_user=""
while IFS=, read -r csv_hostname csv_ip csv_user csv_status _notes; do
  [[ "${csv_hostname}" == "hostname" ]] && continue
  [[ "${csv_status}" == "joined" ]] || continue
  if [[ "${node_selector}" == "${csv_hostname}" || "${node_selector}" == "${csv_ip}" ]]; then
    hostname="${csv_hostname}"
    ip="${csv_ip}"
    remote_user="${csv_user:-${remote_user_default}}"
    break
  fi
done < "${inventory}"

if [[ -z "${ip}" ]]; then
  echo "node_not_found_or_not_joined=${node_selector}" >&2
  exit 1
fi

tmp_root="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp_root}"
}
trap cleanup EXIT

safe_run_id="${run_id//[^A-Za-z0-9_.-]/_}"
job_id="$(printf '%s' "${run_id}" | sha1sum | awk '{print substr($1, 1, 12)}')"
pkg_name="gdelt_score_input_${safe_run_id}.tar"
ps_name="run_gdelt_score_${safe_run_id}.ps1"
result_name="gdelt_score_result_${safe_run_id}.tar"
pkg="${tmp_root}/${pkg_name}"
ps="${tmp_root}/${ps_name}"
result="${tmp_root}/${result_name}"
extract_dir="${tmp_root}/extract"

tar -cf "${pkg}" \
  scripts/news_shock_taxonomy/score_gdelt_gkg_asia.py \
  config/news_shock_asia_universe.json \
  "${normalized_file}"

cat > "${ps}" <<'PS1'
param(
  [string]$RunId,
  [string]$JobId,
  [string]$PkgName,
  [string]$ResultName,
  [string]$RemoteJobRoot,
  [string]$ChunkSize,
  [string]$SampleSize,
  [string]$BlasThreads
)

$ErrorActionPreference = "Continue"
$job = Join-Path $RemoteJobRoot ("gs_" + $JobId)
$repo = Join-Path $job "r"
$pkg = Join-Path $HOME $PkgName
$result = Join-Path $HOME $ResultName

Remove-Item -Recurse -Force $job -ErrorAction SilentlyContinue
Remove-Item -Force $result -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $repo | Out-Null
tar -xf $pkg -C $repo

$out = Join-Path $job "out"
New-Item -ItemType Directory -Force $out | Out-Null
Set-Location $repo

$env:OMP_NUM_THREADS = $BlasThreads
$env:MKL_NUM_THREADS = $BlasThreads
$env:OPENBLAS_NUM_THREADS = $BlasThreads
$env:MALLOC_ARENA_MAX = "2"

$stdout = Join-Path $job "score.stdout.log"
$stderr = Join-Path $job "score.stderr.log"
$inputPath = "data_lake\news_shock_taxonomy\normalized\gdelt_gkg_asia_bulk\$RunId\asia_gkg_filtered.csv.gz"
$scoreArgs = @(
  "scripts\news_shock_taxonomy\score_gdelt_gkg_asia.py",
  "--input", $inputPath,
  "--config", "config\news_shock_asia_universe.json",
  "--out-root", $out,
  "--run-id", $RunId,
  "--chunk-size", $ChunkSize,
  "--sample-size", $SampleSize
)

$start = Get-Date
$proc = Start-Process -FilePath "py" -ArgumentList $scoreArgs -WorkingDirectory $repo -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
try {
  $proc.PriorityClass = "BelowNormal"
} catch {
  Write-Output ("priority_set_failed=" + $_.Exception.Message)
}
$proc.WaitForExit()
$proc.Refresh()
$elapsed = [math]::Round(((Get-Date) - $start).TotalSeconds, 2)
$exitCode = $proc.ExitCode
$summary = Join-Path (Join-Path $out $RunId) "scoring_summary.json"
if ($null -eq $exitCode) {
  if (Test-Path $summary) {
    $exitCode = 0
  } else {
    $exitCode = 1
  }
}

if (Test-Path $stdout) { Get-Content $stdout }
if (Test-Path $stderr) { Get-Content $stderr }
Write-Output ("EXIT=" + $exitCode)
Write-Output ("ELAPSED_SEC=" + $elapsed)

if ($exitCode -ne 0) {
  exit $exitCode
}

tar -cf $result -C $out $RunId
Write-Output ("RESULT_TGZ=" + $result)
PS1

echo "offload_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "run_id=${run_id}"
echo "node=${hostname}"
echo "ip=${ip}"
echo "input=${normalized_file}"

scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${pkg}" "${ps}" "${remote_user}@${ip}:"

ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${remote_user}@${ip}" \
  "powershell -NoProfile -ExecutionPolicy Bypass -File .\\${ps_name} -RunId \"${run_id}\" -JobId \"${job_id}\" -PkgName \"${pkg_name}\" -ResultName \"${result_name}\" -RemoteJobRoot \"${remote_job_root}\" -ChunkSize \"${chunk_size}\" -SampleSize \"${sample_size}\" -BlasThreads \"${blas_threads}\""

scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${remote_user}@${ip}:${result_name}" "${result}"

mkdir -p "${extract_dir}" "${proc_dir}"
tar -xf "${result}" -C "${extract_dir}"
cp -a "${extract_dir}/${run_id}/." "${proc_dir}/"

gzip -t "${scored_file}"
gzip -t "${url_queue_file}"
[[ -s "${daily_panel_file}" ]]

echo "offload_finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "processed_dir=${proc_dir}"
