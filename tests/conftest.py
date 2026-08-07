"""Shared test fixtures for tublub."""

import json

import pytest
import tablib


def _write_json_book(path, sheets):
    """Write a JSON multi-sheet workbook: [(title, [row_dict, ...]), ...]."""
    book = [{"title": title, "data": rows} for title, rows in sheets]
    path.write_text(json.dumps(book))
    return path


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


@pytest.fixture
def one_sheet_xlsx(tmp_path):
    """Write a one-sheet XLSX workbook and return its path."""
    book = tablib.Databook()
    people = tablib.Dataset(headers=["name", "age"])
    people.append(["Alice", 30])
    people.append(["Bob", 25])
    people.title = "people"
    book.add_sheet(people)
    p = tmp_path / "single.xlsx"
    p.write_bytes(book.export("xlsx"))
    return p


@pytest.fixture
def empty_workbook(tmp_path):
    """Write a JSON workbook with zero sheets and return its path."""
    p = tmp_path / "empty.json"
    p.write_text(tablib.Databook().export("json"))
    return p


@pytest.fixture
def multi_sheet_xlsx(tmp_path):
    """Write a two-sheet XLSX file and return its path."""
    book = tablib.Databook()
    people = tablib.Dataset(headers=["name", "age"])
    people.append(["Alice", 30])
    people.append(["Bob", 25])
    people.title = "people"
    cities = tablib.Dataset(headers=["city", "population"])
    cities.append(["Stockholm", 975551])
    cities.append(["Gothenburg", 583056])
    cities.title = "cities"
    book.add_sheet(people)
    book.add_sheet(cities)
    p = tmp_path / "book.xlsx"
    p.write_bytes(book.export("xlsx"))
    return p


@pytest.fixture
def multi_sheet_json(tmp_path):
    """Write a three-sheet JSON workbook and return its path."""
    return _write_json_book(
        tmp_path / "book.json",
        [
            ("people", [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]),
            (
                "cities",
                [
                    {"city": "Stockholm", "population": 975551},
                    {"city": "Gothenburg", "population": 583056},
                ],
            ),
            ("products", [{"product": "Chair", "price": 499}]),
        ],
    )


@pytest.fixture
def dup_title_json(tmp_path):
    """Write a JSON workbook with two sheets both titled "Users"."""
    return _write_json_book(
        tmp_path / "dup.json",
        [
            ("Users", [{"name": "Alice"}]),
            ("Costs", [{"item": "Rent"}]),
            ("Users", [{"name": "Bob"}]),
        ],
    )


@pytest.fixture
def case_dup_json(tmp_path):
    """Write a JSON workbook whose sheet titles differ only by case."""
    return _write_json_book(
        tmp_path / "case.json",
        [
            ("users", [{"name": "Alice"}]),
            ("USERS", [{"name": "Bob"}]),
        ],
    )


@pytest.fixture
def year_title_json(tmp_path):
    """Write a JSON workbook with a single sheet titled "2024"."""
    return _write_json_book(
        tmp_path / "budget.json",
        [("2024", [{"month": "Jan", "total": 100}])],
    )


@pytest.fixture
def range_title_json(tmp_path):
    """Write a JSON workbook with a single sheet titled "1-5"."""
    return _write_json_book(
        tmp_path / "span.json",
        [("1-5", [{"month": "Jan", "total": 100}])],
    )


@pytest.fixture
def many_sheets_json(tmp_path):
    """Write a JSON workbook with more sheets than an error lists titles for."""
    return _write_json_book(
        tmp_path / "many.json",
        [(f"sheet{i:02d}", [{"n": i}]) for i in range(12)],
    )


@pytest.fixture
def untitled_sheets_json(tmp_path):
    """Write a JSON workbook whose sheets all have empty titles."""
    return _write_json_book(
        tmp_path / "untitled.json",
        [("", [{"name": "Alice"}]), ("", [{"name": "Bob"}])],
    )


@pytest.fixture
def empty_title_json(tmp_path):
    """Write a JSON workbook with an empty-titled sheet and a named one."""
    return _write_json_book(
        tmp_path / "untitled.json",
        [
            ("", [{"name": "Alice"}]),
            ("named", [{"name": "Bob"}]),
        ],
    )


@pytest.fixture
def existing_out(tmp_path):
    """Write a pre-existing output file with sentinel content, return its path."""
    p = tmp_path / "out.json"
    p.write_text("sentinel")
    return p
