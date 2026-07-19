@echo off
set OUTDIR=C:\cw\dataset_index_v3
if not exist "%OUTDIR%" mkdir "%OUTDIR%"
"C:\Users\user\AppData\Local\Programs\Python\Python39\python.exe" "C:\Users\user\harvest_dataset_indexes_full.py" --out-dir "%OUTDIR%" --sources datacite --max-records-per-source 5000000 --page-size 500 --sleep 0.25 >> "%OUTDIR%\harvest.stdout.log" 2>> "%OUTDIR%\harvest.stderr.log"
