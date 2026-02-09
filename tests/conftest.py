"""Shared test fixtures for tublub."""

import json

import pytest
import tablib


@pytest.fixture
def sample_data():
    """A small Tablib Dataset for testing."""
    data = tablib.Dataset(headers=["name", "age", "city"])
    data.append(["Alice", 30, "Stockholm"])
    data.append(["Bob", 25, "Gothenburg"])
    return data


@pytest.fixture
def sample_csv(tmp_path):
    """Write a CSV file and return its path."""
    p = tmp_path / "data.csv"
    p.write_text("name,age,city\nAlice,30,Stockholm\nBob,25,Gothenburg\n")
    return p


@pytest.fixture
def sample_tsv(tmp_path):
    """Write a TSV file and return its path."""
    p = tmp_path / "data.tsv"
    p.write_text("name\tage\tcity\nAlice\t30\tStockholm\nBob\t25\tGothenburg\n")
    return p


@pytest.fixture
def sample_json(tmp_path):
    """Write a JSON file and return its path."""
    p = tmp_path / "data.json"
    rows = [
        {"name": "Alice", "age": 30, "city": "Stockholm"},
        {"name": "Bob", "age": 25, "city": "Gothenburg"},
    ]
    p.write_text(json.dumps(rows))
    return p


@pytest.fixture
def sample_yaml(tmp_path):
    """Write a YAML file and return its path."""
    p = tmp_path / "data.yaml"
    p.write_text(
        "- {name: Alice, age: 30, city: Stockholm}\n"
        "- {name: Bob, age: 25, city: Gothenburg}\n"
    )
    return p
