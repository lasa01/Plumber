pip install -t io_import_vmf/deps -r requirements.txt --upgrade
New-Item -Force -ItemType Directory -Path io_import_vmf/bin | Out-Null
Invoke-WebRequest -outf io_import_vmf/bin/CrowbarCommandLineDecomp.exe "https://github.com/UltraTechX/Crowbar-Command-Line/releases/latest/download/CrowbarCommandLineDecomp.exe"
Invoke-WebRequest -outf io_import_vmf/bin/CrowbarCommandLineDecomp-License "https://raw.githubusercontent.com/UltraTechX/Crowbar-Command-Line/master/License"
Invoke-WebRequest -outf io_import_vmf/bin/CrowbarX.zip "https://github.com/nonunknown/crowbarx/releases/download/0.1/Crowbar.zip"
python pack.py
