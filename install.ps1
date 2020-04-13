pip install -t io_import_vmf/deps -r requirements.txt --upgrade
Invoke-WebRequest -outf io_import_vmf/bin/CrowbarCommandLineDecomp.exe "https://github.com/UltraTechX/Crowbar-Command-Line/releases/latest/download/CrowbarCommandLineDecomp.exe"
python pack.py
