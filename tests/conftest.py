'''Tests never see the real data/ folder: the data folder points to an empty temporary folder
before any kap_triage module is imported (module paths are read once, at import).
The folder is removed when the test run ends.'''
import atexit
import os
import shutil
import tempfile

import pytest

DATA_DIR=tempfile.mkdtemp(prefix='kap_test_data_')
os.environ['KAP_DATA_DIR']=DATA_DIR
atexit.register(shutil.rmtree,DATA_DIR,ignore_errors=True)


@pytest.fixture
def clean_data_dir():
    '''For a test that writes into the shared test data folder: empty it again afterwards,
    so the tests after it see an empty folder whatever the order.'''
    yield DATA_DIR
    shutil.rmtree(DATA_DIR,ignore_errors=True)
    os.mkdir(DATA_DIR)
