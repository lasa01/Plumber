pip install -t io_import_vmf/deps -r requirements.txt --upgrade
mkdir -p io_import_vmf/bin
wget -O io_import_vmf/bin/CrowbarCommandLineDecomp.exe "https://github.com/UltraTechX/Crowbar-Command-Line/releases/latest/download/CrowbarCommandLineDecomp.exe"
wget -O io_import_vmf/bin/CrowbarCommandLineDecomp-License "https://raw.githubusercontent.com/UltraTechX/Crowbar-Command-Line/master/License"
wget -O io_import_vmf/bin/CrowbarX.zip "https://github.com/nonunknown/crowbarx/releases/download/0.1/Crowbar.zip"
python pack.py
