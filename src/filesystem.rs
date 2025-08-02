use std::{
    cmp::Ordering,
    fs::{self, File},
    io::{BufRead, BufReader, Read, Write},
    path::{Path as StdPath, PathBuf as StdPathBuf},
    time::Instant,
};

use pyo3::{
    exceptions::{PyIOError, PyTypeError, PyUnicodeDecodeError, PyValueError},
    prelude::*,
};
use tracing::{error, info, warn};

use plumber_core::{
    fs::{
        DirEntryType, FileSystem, GameFile, GamePathBuf, OpenFileSystem, ReadDir, SearchPath,
        SourceAppsExt,
    },
    steam::Libraries,
};

#[pyclass(module = "plumber", name = "FileSystem")]
pub struct PyFileSystem {
    pub file_system: FileSystem,
}

impl From<FileSystem> for PyFileSystem {
    fn from(file_system: FileSystem) -> Self {
        Self { file_system }
    }
}

impl From<PyFileSystem> for FileSystem {
    fn from(f: PyFileSystem) -> Self {
        f.file_system
    }
}

#[pymethods]
impl PyFileSystem {
    #[new]
    fn new(name: String, search_paths: Vec<(&str, &str)>) -> PyResult<Self> {
        Ok(Self {
            file_system: FileSystem {
                name,
                search_paths: search_paths
                    .into_iter()
                    .map(to_search_path)
                    .collect::<PyResult<_>>()?,
            },
        })
    }

    #[staticmethod]
    fn empty() -> Self {
        Self {
            file_system: FileSystem {
                name: "None".to_owned(),
                search_paths: Vec::new(),
            },
        }
    }

    fn name(&self) -> &str {
        &self.file_system.name
    }

    fn search_paths(&self) -> PyResult<Vec<(&str, &str)>> {
        self.file_system
            .search_paths
            .iter()
            .map(from_search_path)
            .collect()
    }

    fn with_search_path(&self, search_path: (&str, &str)) -> PyResult<Self> {
        let path = to_search_path(search_path)?;

        Ok(Self {
            file_system: self.file_system.with_search_paths(vec![path]),
        })
    }

    fn browse(&self) -> PyResult<PyFileBrowser> {
        let opened = self
            .file_system
            .open()
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        Ok(PyFileBrowser {
            file_system: opened,
        })
    }

    fn read_file_text(&self, path: &str) -> PyResult<String> {
        let opened = self
            .file_system
            .open()
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        let path = GamePathBuf::from(path);
        let file = opened
            .open_file(&path)
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        let mut reader = BufReader::new(file);
        let mut content = String::new();

        reader
            .read_to_string(&mut content)
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        Ok(content)
    }

    fn read_file_bytes(&self, path: &str) -> PyResult<Vec<u8>> {
        let opened = self
            .file_system
            .open()
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        let path = GamePathBuf::from(path);
        let file = opened
            .open_file(&path)
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        let mut reader = BufReader::new(file);
        let mut content = Vec::new();

        reader
            .read_to_end(&mut content)
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        Ok(content)
    }

    fn file_exists(&self, path: &str) -> PyResult<bool> {
        let opened = self
            .file_system
            .open()
            .map_err(|e| PyIOError::new_err(e.to_string()))?;

        let path = GamePathBuf::from(path);

        // Try to open the file - if it exists, this will succeed
        match opened.open_file(&path) {
            Ok(_) => Ok(true),
            Err(_) => Ok(false),
        }
    }

    fn extract(&self, path: &str, is_dir: bool, target_path: &str) -> PyResult<()> {
        let start = Instant::now();
        info!("opening file system of game `{}`...", self.file_system.name);

        let opened = self
            .file_system
            .open()
            .map_err(|e| PyIOError::new_err((e.to_string(),)))?;

        info!(
            "file system opened in {:.2} s",
            start.elapsed().as_secs_f32()
        );

        let path = GamePathBuf::from(path);
        let target_path = StdPath::new(target_path);

        let start = Instant::now();
        info!("extracting...");

        if is_dir {
            extract_directory_recursive(opened.read_dir(&path), target_path)?;
        } else {
            extract_file(opened.open_file(&path)?, path.as_str(), target_path)?;
        }

        info!(
            "extraction finished in {:.2} s",
            start.elapsed().as_secs_f32()
        );

        Ok(())
    }
}

fn extract_file(file: GameFile, file_path: &str, target_path: &StdPath) -> PyResult<()> {
    let mut target_file = File::create(target_path)?;

    let mut reader = BufReader::new(file);

    loop {
        let data = reader.fill_buf()?;

        if data.is_empty() {
            break;
        }

        target_file.write_all(data)?;
        let amt = data.len();

        reader.consume(amt);
    }

    info!(
        "extracted file `{}` into `{}`",
        file_path,
        target_path.display()
    );

    Ok(())
}

fn extract_directory_recursive(read_dir: ReadDir, target_dir: &StdPath) -> PyResult<()> {
    if !target_dir.is_dir() {
        fs::create_dir(target_dir)?;
    }

    for res in read_dir {
        let entry = res?;

        match entry.entry_type() {
            DirEntryType::File => {
                if let Err(err) = extract_file(
                    entry.open()?,
                    entry.path().as_str(),
                    &target_dir.join(entry.name().as_str()),
                ) {
                    error!(
                        "error extracting file `{}` to `{}`: {}",
                        entry.path(),
                        entry.name(),
                        err
                    );
                }
            }
            DirEntryType::Directory => {
                if let Err(err) = extract_directory_recursive(
                    entry.read_dir(),
                    &target_dir.join(entry.name().as_str()),
                ) {
                    error!(
                        "error extracting directory `{}` to `{}`: {}",
                        entry.path(),
                        entry.name(),
                        err
                    );
                }
            }
        }
    }

    Ok(())
}

fn to_search_path(search_path: (&str, &str)) -> PyResult<SearchPath> {
    let (kind, path) = search_path;

    match kind {
        "DIR" => Ok(SearchPath::Directory(StdPathBuf::from(path))),
        "VPK" => Ok(SearchPath::Vpk(StdPathBuf::from(path))),
        "WILDCARD" => Ok(SearchPath::Wildcard(StdPathBuf::from(path))),
        _ => Err(PyTypeError::new_err("invalid search path enum value")),
    }
}

fn from_search_path(search_path: &SearchPath) -> PyResult<(&str, &str)> {
    match search_path {
        SearchPath::Vpk(path) => path.to_str().map(|path| ("VPK", path)),
        SearchPath::Directory(path) => path.to_str().map(|path| ("DIR", path)),
        SearchPath::Wildcard(path) => path.to_str().map(|path| ("WILDCARD", path)),
    }
    .ok_or_else(|| PyUnicodeDecodeError::new_err("search path is not valid utf8"))
}

pub fn discover() -> Vec<PyFileSystem> {
    let libraries = match Libraries::discover() {
        Ok(libraries) => libraries,
        Err(err) => {
            error!("could not discover games: {}", err);
            return Vec::new();
        }
    };

    libraries
        .apps()
        .source()
        .filesystems()
        .filter_map(|r| match r {
            Ok(f) => Some(f.into()),
            Err(e) => {
                warn!("could not discover a game: {}", e);
                None
            }
        })
        .collect()
}

pub fn from_gameinfo(path: &str) -> PyResult<PyFileSystem> {
    let game_info_path = StdPath::new(path);
    let root_path = game_info_path
        .parent()
        .and_then(StdPath::parent)
        .ok_or_else(|| PyValueError::new_err("gameinfo.txt directory doesn't have a parent"))?;

    let file_system = FileSystem::from_paths(root_path, game_info_path)
        .map_err(|e| PyIOError::new_err(e.to_string()))?;

    Ok(file_system.into())
}

#[pyclass(module = "plumber", name = "FileBrowser")]
pub struct PyFileBrowser {
    file_system: OpenFileSystem,
}

#[pymethods]
impl PyFileBrowser {
    fn read_dir(&self, dir: String) -> PyResult<Vec<PyFileBrowserEntry>> {
        let mut entries = Vec::new();

        for res in self.file_system.read_dir(&GamePathBuf::from(dir)) {
            let entry = res?;

            entries.push(PyFileBrowserEntry {
                name: entry.name().to_string(),
                path: entry.path().to_path_buf(),
                kind: entry.entry_type().clone(),
            });
        }

        entries.sort_unstable_by(|a, b| {
            if a.kind == b.kind {
                a.name.cmp(&b.name)
            } else if a.kind.is_directory() {
                Ordering::Less
            } else {
                Ordering::Greater
            }
        });

        entries.dedup();

        Ok(entries)
    }
}

#[pyclass(module = "plumber", name = "FileBrowserEntry")]
#[derive(PartialEq, Eq)]
pub struct PyFileBrowserEntry {
    name: String,
    path: GamePathBuf,
    kind: DirEntryType,
}

#[pymethods]
impl PyFileBrowserEntry {
    fn name(&self) -> &str {
        &self.name
    }

    fn path(&self) -> &str {
        self.path.as_str()
    }

    fn kind(&self) -> &str {
        match self.kind {
            DirEntryType::File => "FILE",
            DirEntryType::Directory => "DIR",
        }
    }
}
