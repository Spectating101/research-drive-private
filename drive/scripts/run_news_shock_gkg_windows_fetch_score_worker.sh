#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "usage: $0 RUN_ID START_DATE END_DATE WINDOWS_HOSTNAME_OR_IP" >&2
  echo "example: $0 win_probe_20200401_20200402 2020-04-01 2020-04-02 DESKTOP-VEFGGDH" >&2
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

inventory="${CLUSTER_INVENTORY:-/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv}"
key="${CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
remote_user_default="${CLUSTER_USER:-user}"
remote_job_root="${WINDOWS_JOB_ROOT:-C:\\cw}"
fetch_workers="${FETCH_WORKERS:-2}"
fetch_timeout="${FETCH_TIMEOUT:-180}"
fetch_retries="${FETCH_RETRIES:-3}"
fetch_sleep="${FETCH_SLEEP:-0.3}"
fetch_max_files="${FETCH_MAX_FILES:-0}"
score_chunk_size="${SCORE_CHUNK_SIZE:-50000}"
score_sample_size="${SCORE_SAMPLE_SIZE:-100}"
blas_threads="${BLAS_THREADS:-2}"
windows_python_exe="${WINDOWS_PYTHON_EXE:-py}"
force="${FORCE:-0}"
return_mode="${RETURN_MODE:-tar}"

norm_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"
normalized_file="${norm_dir}/asia_gkg_filtered.csv.gz"
scored_file="${proc_dir}/asia_gkg_scored.csv.gz"
daily_panel_file="${proc_dir}/daily_country_shock_panel.csv"
url_queue_file="${proc_dir}/url_enrichment_queue.csv.gz"

if [[ "${force}" != "1" && -s "${normalized_file}" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] && gzip -t "${normalized_file}" && gzip -t "${scored_file}" && gzip -t "${url_queue_file}"; then
  echo "fetch_score_outputs_already_exist=${run_id}"
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
pkg_name="gdelt_fetch_score_input_${safe_run_id}.tar"
ps_name="run_gdelt_fetch_score_${safe_run_id}.ps1"
result_name="gdelt_fetch_score_result_${safe_run_id}.tar"
pkg="${tmp_root}/${pkg_name}"
ps="${tmp_root}/${ps_name}"
result="${tmp_root}/${result_name}"
extract_dir="${tmp_root}/extract"

tar -cf "${pkg}" \
  scripts/news_shock_taxonomy/fetch_gdelt_gkg_asia_bulk.py \
  scripts/news_shock_taxonomy/score_gdelt_gkg_asia.py \
  config/news_shock_asia_universe.json

cat > "${ps}" <<'PS1'
param(
  [string]$RunId,
  [string]$StartDate,
  [string]$EndDate,
  [string]$JobId,
  [string]$PkgName,
  [string]$ResultName,
  [string]$RemoteJobRoot,
  [string]$FetchWorkers,
  [string]$FetchTimeout,
  [string]$FetchRetries,
  [string]$FetchSleep,
  [string]$FetchMaxFiles,
  [string]$ScoreChunkSize,
  [string]$ScoreSampleSize,
  [string]$BlasThreads,
  [string]$PythonExe
)

$ErrorActionPreference = "Continue"
$job = Join-Path $RemoteJobRoot ("fs_" + $JobId)
$repo = Join-Path $job "r"
$pkg = Join-Path $HOME $PkgName
$result = Join-Path $HOME $ResultName

Remove-Item -Recurse -Force $job -ErrorAction SilentlyContinue
Remove-Item -Force $result -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $repo | Out-Null
tar -xf $pkg -C $repo
Set-Location $repo

$env:OMP_NUM_THREADS = $BlasThreads
$env:MKL_NUM_THREADS = $BlasThreads
$env:OPENBLAS_NUM_THREADS = $BlasThreads
$env:MALLOC_ARENA_MAX = "2"

$fetchOutLog = Join-Path $job "fetch.stdout.log"
$fetchErrLog = Join-Path $job "fetch.stderr.log"
$scoreOutLog = Join-Path $job "score.stdout.log"
$scoreErrLog = Join-Path $job "score.stderr.log"
$fetchArgs = @(
  "scripts\news_shock_taxonomy\fetch_gdelt_gkg_asia_bulk.py",
  "--run-id", $RunId,
  "--start-date", $StartDate,
  "--end-date", $EndDate,
  "--timeout", $FetchTimeout,
  "--retries", $FetchRetries,
  "--sleep", $FetchSleep,
  "--workers", $FetchWorkers,
  "--master-refresh-seconds", "86400",
  "--no-keep-raw"
)
if ([int]$FetchMaxFiles -gt 0) {
  $fetchArgs += @("--max-files", $FetchMaxFiles)
}

Write-Output ("FETCH_STARTED=" + (Get-Date).ToUniversalTime().ToString("s") + "Z")
$fetchStart = Get-Date
$fetchProc = Start-Process -FilePath $PythonExe -ArgumentList $fetchArgs -WorkingDirectory $repo -PassThru -NoNewWindow -RedirectStandardOutput $fetchOutLog -RedirectStandardError $fetchErrLog
try { $fetchProc.PriorityClass = "BelowNormal" } catch {}
$fetchProc.WaitForExit(); $fetchProc.Refresh()
$fetchElapsed = [math]::Round(((Get-Date) - $fetchStart).TotalSeconds, 2)
if (Test-Path $fetchOutLog) { Get-Content $fetchOutLog }
if (Test-Path $fetchErrLog) { Get-Content $fetchErrLog }
$fetchExit = $fetchProc.ExitCode
if ($null -eq $fetchExit) { $fetchExit = 0 }
Write-Output ("FETCH_EXIT=" + $fetchExit)
Write-Output ("FETCH_ELAPSED_SEC=" + $fetchElapsed)
if ($fetchExit -ne 0) { exit $fetchExit }

$inputPath = "data_lake\news_shock_taxonomy\normalized\gdelt_gkg_asia_bulk\$RunId\asia_gkg_filtered.csv.gz"
if (-not (Test-Path $inputPath)) {
  Write-Output ("FETCH_MISSING_OUTPUT=" + $inputPath)
  exit 1
}

$scoreArgs = @(
  "scripts\news_shock_taxonomy\score_gdelt_gkg_asia.py",
  "--input", $inputPath,
  "--config", "config\news_shock_asia_universe.json",
  "--out-root", "data_lake\news_shock_taxonomy\processed",
  "--run-id", $RunId,
  "--chunk-size", $ScoreChunkSize,
  "--sample-size", $ScoreSampleSize
)

Write-Output ("SCORE_STARTED=" + (Get-Date).ToUniversalTime().ToString("s") + "Z")
$scoreStart = Get-Date
$scoreProc = Start-Process -FilePath $PythonExe -ArgumentList $scoreArgs -WorkingDirectory $repo -PassThru -NoNewWindow -RedirectStandardOutput $scoreOutLog -RedirectStandardError $scoreErrLog
try { $scoreProc.PriorityClass = "BelowNormal" } catch {}
$scoreProc.WaitForExit(); $scoreProc.Refresh()
$scoreElapsed = [math]::Round(((Get-Date) - $scoreStart).TotalSeconds, 2)
if (Test-Path $scoreOutLog) { Get-Content $scoreOutLog }
if (Test-Path $scoreErrLog) { Get-Content $scoreErrLog }
$summary = "data_lake\news_shock_taxonomy\processed\$RunId\scoring_summary.json"
$scoreExit = $scoreProc.ExitCode
if ($null -eq $scoreExit) {
  if (Test-Path $summary) { $scoreExit = 0 } else { $scoreExit = 1 }
}
Write-Output ("SCORE_EXIT=" + $scoreExit)
Write-Output ("SCORE_ELAPSED_SEC=" + $scoreElapsed)
if ($scoreExit -ne 0) { exit $scoreExit }

tar -cf $result `
  "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/$RunId" `
  "data_lake/news_shock_taxonomy/processed/$RunId"
Write-Output ("RESULT_TAR=" + $result)
PS1

echo "worker_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "run_id=${run_id}"
echo "start_date=${start_date}"
echo "end_date=${end_date}"
echo "node=${hostname}"
echo "ip=${ip}"
echo "fetch_max_files=${fetch_max_files}"
echo "return_mode=${return_mode}"
echo "windows_python_exe=${windows_python_exe}"

scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${pkg}" "${ps}" "${remote_user}@${ip}:"

ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
  "${remote_user}@${ip}" \
  "powershell -NoProfile -ExecutionPolicy Bypass -File .\\${ps_name} -RunId \"${run_id}\" -StartDate \"${start_date}\" -EndDate \"${end_date}\" -JobId \"${job_id}\" -PkgName \"${pkg_name}\" -ResultName \"${result_name}\" -RemoteJobRoot \"${remote_job_root}\" -FetchWorkers \"${fetch_workers}\" -FetchTimeout \"${fetch_timeout}\" -FetchRetries \"${fetch_retries}\" -FetchSleep \"${fetch_sleep}\" -FetchMaxFiles \"${fetch_max_files}\" -ScoreChunkSize \"${score_chunk_size}\" -ScoreSampleSize \"${score_sample_size}\" -BlasThreads \"${blas_threads}\" -PythonExe \"${windows_python_exe}\""

mkdir -p "${norm_dir}" "${proc_dir}"
if [[ "${return_mode}" == "direct" ]]; then
  rm -rf "${norm_dir}" "${proc_dir}"
  mkdir -p "$(dirname "${norm_dir}")" "$(dirname "${proc_dir}")"
  remote_repo="C:/cw/fs_${job_id}/r"
  scp -q -r -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "${remote_user}@${ip}:${remote_repo}/${norm_dir}" "${norm_dir}"
  scp -q -r -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "${remote_user}@${ip}:${remote_repo}/${proc_dir}" "${proc_dir}"
else
  scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "${remote_user}@${ip}:${result_name}" "${result}"

  mkdir -p "${extract_dir}"
  tar -xf "${result}" -C "${extract_dir}"
  cp -a "${extract_dir}/${norm_dir}/." "${norm_dir}/"
  cp -a "${extract_dir}/${proc_dir}/." "${proc_dir}/"
fi

gzip -t "${normalized_file}"
gzip -t "${scored_file}"
gzip -t "${url_queue_file}"
[[ -s "${daily_panel_file}" ]]

echo "worker_finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "normalized_dir=${norm_dir}"
echo "processed_dir=${proc_dir}"
