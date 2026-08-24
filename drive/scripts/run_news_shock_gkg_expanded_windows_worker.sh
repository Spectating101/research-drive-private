#!/usr/bin/env bash
# Expanded-universe GDELT fetch+score on a Windows cluster node (Asia + global adjunct).
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "usage: $0 RUN_ID START_DATE END_DATE WINDOWS_HOSTNAME_OR_IP" >&2
  exit 2
fi

run_id="$1"
start_date="$2"
end_date="$3"
node_selector="$4"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

python3 scripts/news_shock_taxonomy/build_expanded_universe_config.py

inventory="${CLUSTER_INVENTORY:-/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv}"
key="${CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
remote_user_default="${CLUSTER_USER:-user}"
remote_job_root="${WINDOWS_JOB_ROOT:-C:\\cw}"
fetch_workers="${FETCH_WORKERS:-2}"
fetch_timeout="${FETCH_TIMEOUT:-180}"
fetch_retries="${FETCH_RETRIES:-3}"
fetch_sleep="${FETCH_SLEEP:-0.3}"
score_chunk_size="${SCORE_CHUNK_SIZE:-50000}"
score_sample_size="${SCORE_SAMPLE_SIZE:-100}"
blas_threads="${BLAS_THREADS:-2}"
windows_python_exe="${WINDOWS_PYTHON_EXE:-C:\\Users\\user\\anaconda3\\python.exe}"
force="${FORCE:-0}"
return_mode="${RETURN_MODE:-direct}"

gkg_config="config/news_shock_expanded_universe.json"
gkg_out_root="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk"

norm_dir="${gkg_out_root}/${run_id}"
proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"
normalized_file="${norm_dir}/asia_gkg_filtered.csv.gz"
scored_file="${proc_dir}/asia_gkg_scored.csv.gz"
daily_panel_file="${proc_dir}/daily_country_shock_panel.csv"
url_queue_file="${proc_dir}/url_enrichment_queue.csv.gz"

if [[ "${force}" != "1" && -s "${normalized_file}" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] \
  && gzip -t "${normalized_file}" && gzip -t "${scored_file}" && gzip -t "${url_queue_file}"; then
  echo "expanded_fetch_score_outputs_already_exist=${run_id}"
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

tmp_parent="${SR_GDELT_TMP:-/media/phyrexian/Transcend/sharpe-renaissance/tmp/gdelt_expanded}"
mkdir -p "${tmp_parent}"
tmp_root="$(mktemp -d -p "${tmp_parent}")"
cleanup() { rm -rf "${tmp_root}"; }
trap cleanup EXIT

safe_run_id="${run_id//[^A-Za-z0-9_.-]/_}"
job_id="$(printf '%s' "${run_id}" | sha1sum | awk '{print substr($1, 1, 12)}')"
pkg_name="gdelt_expanded_input_${safe_run_id}.tar"
ps_name="run_gdelt_expanded_${safe_run_id}.ps1"
result_name="gdelt_expanded_result_${safe_run_id}.tar"
pkg="${tmp_root}/${pkg_name}"
ps="${tmp_root}/${ps_name}"
result="${tmp_root}/${result_name}"
extract_dir="${tmp_root}/extract"

tar -cf "${pkg}" \
  scripts/news_shock_taxonomy/fetch_gdelt_gkg_asia_bulk.py \
  scripts/news_shock_taxonomy/score_gdelt_gkg_asia.py \
  config/news_shock_expanded_universe.json \
  config/news_shock_asia_universe.json \
  config/news_shock_global_adjunct_universe.json

cat > "${ps}" <<'PS1'
param(
  [string]$RunId, [string]$StartDate, [string]$EndDate, [string]$JobId,
  [string]$PkgName, [string]$ResultName, [string]$RemoteJobRoot,
  [string]$FetchWorkers, [string]$FetchTimeout, [string]$FetchRetries, [string]$FetchSleep,
  [string]$ScoreChunkSize, [string]$ScoreSampleSize, [string]$BlasThreads, [string]$PythonExe
)
$ErrorActionPreference = "Continue"
$job = Join-Path $RemoteJobRoot ("fs_" + $JobId)
$repo = Join-Path $job "r"
$pkg = Join-Path $HOME $PkgName
Remove-Item -Recurse -Force $job -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $repo | Out-Null
tar -xf $pkg -C $repo
Set-Location $repo
$env:OMP_NUM_THREADS = $BlasThreads
$env:MKL_NUM_THREADS = $BlasThreads
$env:OPENBLAS_NUM_THREADS = $BlasThreads
$outRoot = "data_lake\news_shock_taxonomy\normalized\gdelt_gkg_expanded_bulk"
$fetchArgs = @(
  "scripts\news_shock_taxonomy\fetch_gdelt_gkg_asia_bulk.py",
  "--config", "config\news_shock_expanded_universe.json",
  "--out-root", $outRoot,
  "--run-id", $RunId, "--start-date", $StartDate, "--end-date", $EndDate,
  "--timeout", $FetchTimeout, "--retries", $FetchRetries, "--sleep", $FetchSleep,
  "--workers", $FetchWorkers, "--master-refresh-seconds", "86400", "--no-keep-raw"
)
$fetchProc = Start-Process -FilePath $PythonExe -ArgumentList $fetchArgs -WorkingDirectory $repo -PassThru -NoNewWindow -Wait
if ($fetchProc.ExitCode -ne 0) { exit $fetchProc.ExitCode }
$inputPath = Join-Path $outRoot "$RunId\asia_gkg_filtered.csv.gz"
$scoreArgs = @(
  "scripts\news_shock_taxonomy\score_gdelt_gkg_asia.py",
  "--input", $inputPath, "--run-id", $RunId,
  "--chunk-size", $ScoreChunkSize, "--sample-size", $ScoreSampleSize
)
$scoreProc = Start-Process -FilePath $PythonExe -ArgumentList $scoreArgs -WorkingDirectory $repo -PassThru -NoNewWindow -Wait
exit $scoreProc.ExitCode
PS1

echo "expanded_windows_worker_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) run_id=${run_id} node=${hostname}"

scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${pkg}" "${ps}" "${remote_user}@${ip}:"

ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${remote_user}@${ip}" \
  "powershell -NoProfile -ExecutionPolicy Bypass -File .\\${ps_name} -RunId \"${run_id}\" -StartDate \"${start_date}\" -EndDate \"${end_date}\" -JobId \"${job_id}\" -PkgName \"${pkg_name}\" -ResultName \"${result_name}\" -RemoteJobRoot \"${remote_job_root}\" -FetchWorkers \"${fetch_workers}\" -FetchTimeout \"${fetch_timeout}\" -FetchRetries \"${fetch_retries}\" -FetchSleep \"${fetch_sleep}\" -ScoreChunkSize \"${score_chunk_size}\" -ScoreSampleSize \"${score_sample_size}\" -BlasThreads \"${blas_threads}\" -PythonExe \"${windows_python_exe}\""

mkdir -p "${norm_dir}" "${proc_dir}"
rm -rf "${norm_dir}" "${proc_dir}"
mkdir -p "$(dirname "${norm_dir}")" "$(dirname "${proc_dir}")"
remote_repo="C:/cw/fs_${job_id}/r"
scp -q -r -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${remote_user}@${ip}:${remote_repo}/${norm_dir}" "$(dirname "${norm_dir}")/"
scp -q -r -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${remote_user}@${ip}:${remote_repo}/${proc_dir}" "$(dirname "${proc_dir}")/"

gzip -t "${normalized_file}"
gzip -t "${scored_file}"
gzip -t "${url_queue_file}"
[[ -s "${daily_panel_file}" ]]

echo "expanded_windows_worker_finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
