use std::{cmp::Ordering, path::PathBuf};

use log::{error, warn};
use pyo3::{
    exceptions::{PyIOError, PyTypeError, PyUnicodeDecodeError},
    prelude::*,
};

use plumber_core::{
    fs::{DirEntryType, FileSystem, GamePathBuf, OpenFileSystem, SearchPath},
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
}

fn to_search_path(search_path: (&str, &str)) -> PyResult<SearchPath> {
    let (kind, path) = search_path;

    match kind {
        "DIR" => Ok(SearchPath::Directory(PathBuf::from(path))),
        "VPK" => Ok(SearchPath::Vpk(PathBuf::from(path))),
        "WILDCARD" => Ok(SearchPath::Wildcard(PathBuf::from(path))),
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

#[pyclass(module = "plumber", name = "FileBrowser")]
pub struct PyFileBrowser {
    file_system: OpenFileSystem,
}

#[pymethods]
impl PyFileBrowser {
    fn read_dir(&self, dir: String) -> PyResult<Vec<PyFileBrowserEntry>> {
        let mut entries = Vec::new();

        for res in self.file_system.read_dir(&GamePathBuf::from(dir)) {
            let entry = res.map_err(|err| PyIOError::new_err(err.to_string()))?;

            entries.push(PyFileBrowserEntry {
                name: entry.name().to_string(),
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
#[derive(PartialEq)]
pub struct PyFileBrowserEntry {
    name: String,
    kind: DirEntryType,
}

#[pymethods]
impl PyFileBrowserEntry {
    fn name(&self) -> &str {
        &self.name
    }

    fn kind(&self) -> &str {
        match self.kind {
            DirEntryType::File => "FILE",
            DirEntryType::Directory => "DIR",
        }
    }
}
