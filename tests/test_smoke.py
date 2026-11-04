import pytest

import custom_paths as cp
from conftest import ALL_STORED


@pytest.mark.parametrize("name", ALL_STORED)
def test_stored_paths_normalize(stored, name):
    doc = stored(name)
    out = cp.normalize(doc["draft"])
    assert cp.step_count(out) == cp.step_count(doc["draft"])
