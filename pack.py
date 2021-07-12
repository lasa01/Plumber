from zipfile import ZipFile
import glob


with ZipFile("io_import_vmf-windows.zip", 'w') as zip:
    for filename in glob.iglob("io_import_vmf/*.py"):
        zip.write(filename)
    for filename in glob.iglob("io_import_vmf/deps/**/*.py", recursive=True):
        zip.write(filename)
    for filename in glob.iglob("io_import_vmf/deps/**/*.dll", recursive=True):
        zip.write(filename)
    zip.write("io_import_vmf/bin/CrowbarCommandLineDecomp-License")
    zip.write("io_import_vmf/bin/CrowbarCommandLineDecomp.exe")
    zip.write("LICENSE", "io_import_vmf/LICENSE")


with ZipFile("io_import_vmf/bin/CrowbarX.zip", 'r') as crowbar_x_zip:
    crowbar_x_zip.extract("crowbar.dll", "io_import_vmf/bin")
    crowbar_x_zip.extract("crowbar.runtimeconfig.json", "io_import_vmf/bin")


with ZipFile("io_import_vmf-linux.zip", 'w') as zip:
    for filename in glob.iglob("io_import_vmf/*.py"):
        zip.write(filename)
    for filename in glob.iglob("io_import_vmf/deps/**/*.py", recursive=True):
        zip.write(filename)
    for filename in glob.iglob("io_import_vmf/deps/**/*.so", recursive=True):
        zip.write(filename)
    zip.write("io_import_vmf/bin/crowbar.dll")
    zip.write("io_import_vmf/bin/crowbar.runtimeconfig.json")
    zip.write("LICENSE", "io_import_vmf/LICENSE")
