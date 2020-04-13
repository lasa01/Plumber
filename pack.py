from zipfile import ZipFile
import glob


with ZipFile("io_import_vmf.zip", 'w') as zip:
    for filename in glob.iglob("io_import_vmf/**/*.py", recursive=True):
        zip.write(filename)
    for filename in glob.iglob("io_import_vmf/**/*.dll", recursive=True):
        zip.write(filename)
    for filename in glob.iglob("io_import_vmf/bin/*"):
        zip.write(filename)
