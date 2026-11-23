'''Where the data lives: one setting for the whole package.

The data folder comes from the environment variable KAP_DATA_DIR (default: data/, relative to the
working directory, as in v1). It is read once, when this module is first imported, so the entry
point (main.py) sets it before importing anything else: the sample mode points it to sample/data/.
No module changes the working directory.
'''
import os
from pathlib import Path


class Settings:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or os.environ.get('KAP_DATA_DIR', 'data'))

    def path(self, name):
        '''A file or pattern inside the data folder, as a string (DuckDB, open() and glob take strings).'''
        return str(self.data_dir / name)


settings = Settings()
