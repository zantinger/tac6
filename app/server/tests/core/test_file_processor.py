import sqlite3
from pathlib import Path

import pytest
import core.file_processor as file_processor
from core.file_processor import (
    clean_column_names,
    convert_csv_to_sqlite,
    convert_json_to_sqlite,
    convert_jsonl_to_sqlite,
    discover_jsonl_fields,
    discover_jsonl_fields_ordered,
    flatten_json_object,
)


@pytest.fixture
def test_db():
    """Return path for in-memory test database"""
    return ':memory:'


@pytest.fixture
def test_assets_dir():
    """Get the path to test assets directory"""
    return Path(__file__).parent.parent / "assets"


class TestFileProcessor:
    
    def test_convert_csv_to_sqlite_success(self, test_db, test_assets_dir):
        # Load real CSV file
        csv_file = test_assets_dir / "test_users.csv"
        with open(csv_file, 'rb') as f:
            csv_data = f.read()
        
        table_name = "users"
        result = convert_csv_to_sqlite(csv_data, table_name, test_db)
        
        # Verify return structure
        assert result['table_name'] == table_name
        assert 'schema' in result
        assert 'row_count' in result
        assert 'sample_data' in result
        
        # Test the returned data
        assert result['row_count'] == 4  # 4 users in test file
        assert len(result['sample_data']) <= 5  # Should return up to 5 samples
        
        # Verify schema has expected columns (cleaned names)
        assert 'name' in result['schema']
        assert 'age' in result['schema'] 
        assert 'city' in result['schema']
        assert 'email' in result['schema']
        
        # Verify sample data structure and content
        john_data = next((item for item in result['sample_data'] if item['name'] == 'John Doe'), None)
        assert john_data is not None
        assert john_data['age'] == 25
        assert john_data['city'] == 'New York'
        assert john_data['email'] == 'john@example.com'
    
    def test_convert_csv_to_sqlite_column_cleaning(self, test_db, test_assets_dir):
        # Test column name cleaning with real file
        csv_file = test_assets_dir / "column_names.csv"
        with open(csv_file, 'rb') as f:
            csv_data = f.read()
        
        table_name = "test_users"
        result = convert_csv_to_sqlite(csv_data, table_name, test_db)
        
        # Verify columns were cleaned in the schema
        assert 'full_name' in result['schema']
        assert 'birth_date' in result['schema']
        assert 'email_address' in result['schema']
        assert 'phone_number' in result['schema']
        
        # Verify sample data has cleaned column names and actual content
        sample = result['sample_data'][0]
        assert 'full_name' in sample
        assert 'birth_date' in sample
        assert 'email_address' in sample
        assert sample['full_name'] == 'John Doe'
        assert sample['birth_date'] == '1990-01-15'
    
    def test_convert_csv_to_sqlite_with_inconsistent_data(self, test_db, test_assets_dir):
        # Test with CSV that has inconsistent row lengths - should raise error
        csv_file = test_assets_dir / "invalid.csv"
        with open(csv_file, 'rb') as f:
            csv_data = f.read()
        
        table_name = "inconsistent_table"
        
        # Pandas will fail on inconsistent CSV data
        with pytest.raises(Exception) as exc_info:
            convert_csv_to_sqlite(csv_data, table_name, test_db)
        
        assert "Error converting CSV to SQLite" in str(exc_info.value)
    
    def test_convert_json_to_sqlite_success(self, test_db, test_assets_dir):
        # Load real JSON file
        json_file = test_assets_dir / "test_products.json"
        with open(json_file, 'rb') as f:
            json_data = f.read()
        
        table_name = "products"
        result = convert_json_to_sqlite(json_data, table_name, test_db)
        
        # Verify return structure
        assert result['table_name'] == table_name
        assert 'schema' in result
        assert 'row_count' in result
        assert 'sample_data' in result
        
        # Test the returned data
        assert result['row_count'] == 3  # 3 products in test file
        assert len(result['sample_data']) == 3
        
        # Verify schema has expected columns
        assert 'id' in result['schema']
        assert 'name' in result['schema']
        assert 'price' in result['schema']
        assert 'category' in result['schema']
        assert 'in_stock' in result['schema']
        
        # Verify sample data structure and content
        laptop_data = next((item for item in result['sample_data'] if item['name'] == 'Laptop'), None)
        assert laptop_data is not None
        assert laptop_data['price'] == 999.99
        assert laptop_data['category'] == 'Electronics'
        assert laptop_data['in_stock']
    
    def test_convert_json_to_sqlite_invalid_json(self, test_db):
        # Test with invalid JSON
        json_data = b'invalid json'
        table_name = "test_table"
        
        with pytest.raises(Exception) as exc_info:
            convert_json_to_sqlite(json_data, table_name, test_db)
        
        assert "Error converting JSON to SQLite" in str(exc_info.value)
    
    def test_convert_json_to_sqlite_not_array(self, test_db):
        # Test with JSON that's not an array
        json_data = b'{"name": "John", "age": 25}'
        table_name = "test_table"
        
        with pytest.raises(Exception) as exc_info:
            convert_json_to_sqlite(json_data, table_name, test_db)
        
        assert "JSON must be an array of objects" in str(exc_info.value)
    
    def test_convert_json_to_sqlite_empty_array(self, test_db):
        # Test with empty JSON array
        json_data = b'[]'
        table_name = "test_table"
        
        with pytest.raises(Exception) as exc_info:
            convert_json_to_sqlite(json_data, table_name, test_db)
        
        assert "JSON array is empty" in str(exc_info.value)
    
    def test_flatten_json_object_nested_dict(self):
        """Test flattening nested dictionary objects"""
        obj = {
            "user": {
                "profile": {
                    "name": "John",
                    "age": 30
                }
            }
        }
        
        flattened = flatten_json_object(obj)
        
        assert flattened["user__profile__name"] == "John"
        assert flattened["user__profile__age"] == 30
    
    def test_flatten_json_object_array(self):
        """Test flattening arrays with indices"""
        obj = {
            "items": ["apple", "banana", "cherry"]
        }
        
        flattened = flatten_json_object(obj)
        
        assert flattened["items_0"] == "apple"
        assert flattened["items_1"] == "banana"
        assert flattened["items_2"] == "cherry"
    
    def test_flatten_json_object_complex(self):
        """Test flattening complex nested structure with arrays and objects"""
        obj = {
            "user": {
                "name": "Alice",
                "tags": ["admin", "user"]
            },
            "actions": [
                {"type": "login", "timestamp": "2023-01-01"},
                {"type": "logout", "timestamp": "2023-01-02"}
            ]
        }
        
        flattened = flatten_json_object(obj)
        
        assert flattened["user__name"] == "Alice"
        assert flattened["user__tags_0"] == "admin"
        assert flattened["user__tags_1"] == "user"
        assert flattened["actions_0__type"] == "login"
        assert flattened["actions_0__timestamp"] == "2023-01-01"
        assert flattened["actions_1__type"] == "logout"
        assert flattened["actions_1__timestamp"] == "2023-01-02"
    
    def test_flatten_json_object_primitive(self):
        """Test flattening primitive values"""
        assert flatten_json_object("hello") == {"": "hello"}
        assert flatten_json_object(42) == {"": 42}
        assert flatten_json_object(True) == {"": True}
        assert flatten_json_object(None) == {"": None}
    
    def test_discover_jsonl_fields_basic(self):
        """Test field discovery with basic JSONL content"""
        jsonl_content = b'{"name": "John", "age": 30}\n{"name": "Jane", "age": 25, "city": "NYC"}'
        
        fields = discover_jsonl_fields(jsonl_content)
        
        assert fields == {"name", "age", "city"}
    
    def test_discover_jsonl_fields_nested(self):
        """Test field discovery with nested structures"""
        jsonl_content = b'{"user": {"name": "John", "profile": {"age": 30}}}\n{"user": {"name": "Jane", "profile": {"city": "NYC"}}}'
        
        fields = discover_jsonl_fields(jsonl_content)
        
        assert fields == {"user__name", "user__profile__age", "user__profile__city"}
    
    def test_discover_jsonl_fields_arrays(self):
        """Test field discovery with arrays"""
        jsonl_content = b'{"items": ["a", "b"]}\n{"items": ["c", "d", "e"]}'
        
        fields = discover_jsonl_fields(jsonl_content)
        
        assert fields == {"items_0", "items_1", "items_2"}
    
    def test_discover_jsonl_fields_invalid_json(self):
        """Test field discovery with invalid JSON"""
        jsonl_content = b'{"valid": "json"}\n{invalid json}'
        
        with pytest.raises(ValueError) as exc_info:
            discover_jsonl_fields(jsonl_content)
        
        assert "Invalid JSON on line 2" in str(exc_info.value)
    
    def test_discover_jsonl_fields_empty_lines(self):
        """Test field discovery with empty lines"""
        jsonl_content = b'{"name": "John"}\n\n{"name": "Jane"}\n'
        
        fields = discover_jsonl_fields(jsonl_content)
        
        assert fields == {"name"}
    
    def test_convert_jsonl_to_sqlite_success(self, test_db, test_assets_dir):
        """Test successful JSONL to SQLite conversion with real file"""
        jsonl_file = test_assets_dir / "sample_data.jsonl"
        with open(jsonl_file, 'rb') as f:
            jsonl_data = f.read()
        
        table_name = "users"
        result = convert_jsonl_to_sqlite(jsonl_data, table_name, test_db)
        
        # Verify return structure
        assert result['table_name'] == table_name
        assert 'schema' in result
        assert 'row_count' in result
        assert 'sample_data' in result
        
        # Test the returned data
        assert result['row_count'] == 5  # 5 users in test file
        assert len(result['sample_data']) <= 5  # Should return up to 5 samples
        
        # Verify schema has expected columns (both flat and nested)
        assert 'id' in result['schema']
        assert 'name' in result['schema']
        assert 'email' in result['schema']
        assert 'age' in result['schema']
        assert 'active' in result['schema']
        assert 'profile__bio' in result['schema']
        assert 'profile__location' in result['schema']
        assert 'profile__skills_0' in result['schema']
        assert 'profile__skills_1' in result['schema']
        assert 'metadata__created_at' in result['schema']
        assert 'metadata__updated_at' in result['schema']
        
        # Verify sample data structure and content
        john_data = next((item for item in result['sample_data'] if item['name'] == 'John Doe'), None)
        assert john_data is not None
        assert john_data['id'] == 1
        assert john_data['email'] == 'john@example.com'
        assert john_data['age'] == 30
        assert john_data['active'] == 1  # SQLite stores boolean as integer
        
        # Verify flattened nested data
        alice_data = next((item for item in result['sample_data'] if item['name'] == 'Alice Brown'), None)
        assert alice_data is not None
        assert alice_data['profile__bio'] == 'Data scientist'
        assert alice_data['profile__location'] == 'SF'
        assert alice_data['profile__skills_0'] == 'Python'
        assert alice_data['profile__skills_1'] == 'Machine Learning'
    
    def test_convert_jsonl_to_sqlite_complex(self, test_db, test_assets_dir):
        """Test JSONL to SQLite conversion with complex nested structures"""
        jsonl_file = test_assets_dir / "complex_data.jsonl"
        with open(jsonl_file, 'rb') as f:
            jsonl_data = f.read()
        
        table_name = "events"
        result = convert_jsonl_to_sqlite(jsonl_data, table_name, test_db)
        
        # Verify return structure
        assert result['table_name'] == table_name
        assert result['row_count'] == 5  # 5 events in test file
        
        # Verify complex nested fields are flattened
        assert 'user__id' in result['schema']
        assert 'user__name' in result['schema']
        assert 'user__profile__email' in result['schema']
        assert 'user__profile__preferences__theme' in result['schema']
        assert 'user__profile__preferences__notifications' in result['schema']
        assert 'actions_0__type' in result['schema']
        assert 'actions_0__timestamp' in result['schema']
        assert 'actions_0__amount' in result['schema']
        assert 'tags_0' in result['schema']
        assert 'tags_1' in result['schema']
        assert 'metadata__source' in result['schema']
        assert 'metadata__device' in result['schema']
        assert 'nested__deep__very__nested__value' in result['schema']
        
        # Verify sample data with complex structures
        alice_event = next((item for item in result['sample_data'] if item['event_id'] == 'evt_001'), None)
        assert alice_event is not None
        assert alice_event['user__id'] == 123
        assert alice_event['user__name'] == 'Alice'
        assert alice_event['user__profile__email'] == 'alice@test.com'
        assert alice_event['user__profile__preferences__theme'] == 'dark'
        assert alice_event['user__profile__preferences__notifications'] == 1  # Boolean as integer
        assert alice_event['actions_0__type'] == 'click'
        assert alice_event['actions_1__type'] == 'view'
        assert alice_event['metadata__source'] == 'web'
        assert alice_event['metadata__device'] == 'desktop'
    
    def test_convert_jsonl_to_sqlite_invalid_json(self, test_db):
        """Test JSONL conversion with invalid JSON"""
        jsonl_data = b'{"valid": "json"}\n{invalid json}'
        table_name = "test_table"
        
        with pytest.raises(Exception) as exc_info:
            convert_jsonl_to_sqlite(jsonl_data, table_name, test_db)
        
        assert "Invalid JSON on line 2" in str(exc_info.value)
    
    def test_convert_jsonl_to_sqlite_empty_file(self, test_db):
        """Test JSONL conversion with empty file"""
        jsonl_data = b''
        table_name = "test_table"
        
        with pytest.raises(Exception) as exc_info:
            convert_jsonl_to_sqlite(jsonl_data, table_name, test_db)
        
        assert "No valid JSON objects found in JSONL file" in str(exc_info.value)
    
    def test_convert_jsonl_to_sqlite_blank_lines_only(self, test_db):
        """Test JSONL conversion with only blank lines"""
        jsonl_data = b'\n\n\n'
        table_name = "test_table"
        
        with pytest.raises(Exception) as exc_info:
            convert_jsonl_to_sqlite(jsonl_data, table_name, test_db)
        
        assert "No valid JSON objects found in JSONL file" in str(exc_info.value)
    
    def test_convert_jsonl_to_sqlite_inconsistent_schema(self, test_db):
        """Test JSONL conversion with inconsistent schema across lines"""
        jsonl_data = b'{"name": "John", "age": 30}\n{"name": "Jane", "city": "NYC", "profile": {"bio": "Engineer"}}'
        table_name = "test_table"
        
        result = convert_jsonl_to_sqlite(jsonl_data, table_name, test_db)
        
        # Should handle inconsistent schema by including all fields
        assert 'name' in result['schema']
        assert 'age' in result['schema']
        assert 'city' in result['schema']
        assert 'profile__bio' in result['schema']
        
        # First record should have None for missing fields
        john_data = next((item for item in result['sample_data'] if item['name'] == 'John'), None)
        assert john_data is not None
        assert john_data['age'] == 30
        assert john_data['city'] is None
        assert john_data['profile__bio'] is None
        
        # Second record should have None for missing fields
        jane_data = next((item for item in result['sample_data'] if item['name'] == 'Jane'), None)
        assert jane_data is not None
        assert jane_data['age'] is None
        assert jane_data['city'] == 'NYC'
        assert jane_data['profile__bio'] == 'Engineer'

class TestFlattenEmptyCollections:
    """Empty lists/objects must survive flattening as NULL columns (G2)"""

    def test_flatten_empty_list(self):
        assert flatten_json_object({"a": []}) == {"a": None}

    def test_flatten_empty_object(self):
        assert flatten_json_object({"b": {}}) == {"b": None}

    def test_flatten_empty_collections_alongside_primitive(self):
        assert flatten_json_object({"a": [], "b": {}, "c": 1}) == {
            "a": None,
            "b": None,
            "c": 1,
        }

    def test_flatten_nested_empty_collection(self):
        """An empty collection nested inside an object keeps its full path"""
        obj = {"user": {"profile": {"tags": [], "settings": {}}, "name": "John"}}

        flattened = flatten_json_object(obj)

        assert flattened["user__profile__tags"] is None
        assert flattened["user__profile__settings"] is None
        assert flattened["user__name"] == "John"

    def test_flatten_empty_collection_at_top_level_yields_no_fields(self):
        """With no prefix there is no field name to keep"""
        assert flatten_json_object({}) == {}
        assert flatten_json_object([]) == {}

    def test_flatten_regression_existing_shapes_unchanged(self):
        """The pre-existing flattening contract must not drift"""
        assert flatten_json_object({"user": {"profile": {"name": "John"}}}) == {
            "user__profile__name": "John"
        }
        assert flatten_json_object({"items": ["a", "b"]}) == {
            "items_0": "a",
            "items_1": "b",
        }
        assert flatten_json_object({"tags": [{"name": "t1"}]}) == {"tags_0__name": "t1"}
        assert flatten_json_object("hello") == {"": "hello"}
        assert flatten_json_object(42) == {"": 42}
        assert flatten_json_object(None) == {"": None}

    def test_flatten_uses_delimiter_constants(self, monkeypatch):
        """Delimiters come from the constants module, not from hardcoded literals"""
        monkeypatch.setattr(file_processor, "NESTED_DELIMITER", "::")
        monkeypatch.setattr(file_processor, "LIST_INDEX_DELIMITER", "#")

        flattened = flatten_json_object({"user": {"tags": ["a"]}})

        assert flattened == {"user::tags#0": "a"}


class TestDiscoverJsonlFieldsOrdered:
    """Deterministic, first-seen field ordering (G1)"""

    def test_ordered_fields_follow_file_order(self):
        jsonl_content = b'{"b": 1, "a": 2}\n{"c": 3, "a": 4}'

        assert discover_jsonl_fields_ordered(jsonl_content) == ["b", "a", "c"]

    def test_ordered_fields_deduplicate_repeated_fields(self):
        jsonl_content = b'{"name": "John"}\n{"name": "Jane"}\n{"name": "Bob"}'

        assert discover_jsonl_fields_ordered(jsonl_content) == ["name"]

    def test_ordered_fields_stable_across_calls(self, test_assets_dir):
        with open(test_assets_dir / "complex_data.jsonl", 'rb') as f:
            jsonl_data = f.read()

        first = discover_jsonl_fields_ordered(jsonl_data)
        second = discover_jsonl_fields_ordered(jsonl_data)

        assert first == second

    def test_discover_jsonl_fields_still_returns_a_set(self):
        """The set-returning contract other callers rely on is preserved"""
        jsonl_content = b'{"name": "John", "age": 30}\n{"name": "Jane", "city": "NYC"}'

        fields = discover_jsonl_fields(jsonl_content)

        assert isinstance(fields, set)
        assert fields == {"name", "age", "city"}

    def test_ordered_fields_skip_blank_lines(self):
        jsonl_content = b'{"a": 1}\n\n   \n{"b": 2}\n'

        assert discover_jsonl_fields_ordered(jsonl_content) == ["a", "b"]

    def test_ordered_fields_invalid_json_names_line_number(self):
        jsonl_content = b'{"valid": "json"}\n{"also": "valid"}\n{invalid json}'

        with pytest.raises(ValueError) as exc_info:
            discover_jsonl_fields_ordered(jsonl_content)

        assert "Invalid JSON on line 3" in str(exc_info.value)

    def test_ordered_fields_non_utf8_content(self):
        with pytest.raises(ValueError) as exc_info:
            discover_jsonl_fields_ordered(b'\xff\xfe{"a": 1}')

        assert "File is not valid UTF-8 encoded text" in str(exc_info.value)


class TestJsonlLinesMustBeObjects:
    """Non-object lines fail loudly instead of producing junk columns (G3)"""

    def test_scalar_line_raises_with_line_number(self):
        with pytest.raises(ValueError) as exc_info:
            discover_jsonl_fields_ordered(b'{"a": 1}\n5')

        message = str(exc_info.value)
        assert "Line 2" in message
        assert "must be JSON objects" in message
        assert "int" in message

    def test_array_line_raises_with_line_number(self):
        with pytest.raises(ValueError) as exc_info:
            discover_jsonl_fields_ordered(b'{"a": 1}\n[1, 2]')

        message = str(exc_info.value)
        assert "Line 2" in message
        assert "must be JSON objects" in message

    def test_string_line_raises(self):
        with pytest.raises(ValueError) as exc_info:
            discover_jsonl_fields_ordered(b'"just a string"')

        assert "Line 1" in str(exc_info.value)

    def test_conversion_rejects_non_object_lines(self, test_db):
        """No empty-name or bogus _0 column is ever created"""
        with pytest.raises(Exception) as exc_info:
            convert_jsonl_to_sqlite(b'{"a": 1}\n[1, 2]', "test_table", test_db)

        assert "must be JSON objects" in str(exc_info.value)


class TestCleanColumnNames:
    """Shared column-name normalization and de-duplication (G4)"""

    def test_lowercases_and_normalizes_separators(self):
        assert clean_column_names(["Full Name", "Birth-Date"]) == [
            "full_name",
            "birth_date",
        ]

    def test_replaces_exotic_characters(self):
        assert clean_column_names(["price$", "a.b", "c/d"]) == ["price_", "a_b", "c_d"]

    def test_empty_name_becomes_column(self):
        assert clean_column_names([""]) == ["column"]

    def test_digit_leading_name_is_prefixed(self):
        assert clean_column_names(["1st", "2024"]) == ["col_1st", "col_2024"]

    def test_deduplicates_collisions_in_order(self):
        assert clean_column_names(["Name", "name", "NAME"]) == [
            "name",
            "name_2",
            "name_3",
        ]

    def test_deduplicates_around_existing_suffix(self):
        assert clean_column_names(["name", "name_2", "name"]) == [
            "name",
            "name_2",
            "name_3",
        ]

    def test_space_and_dash_variants_collide_and_deduplicate(self):
        assert clean_column_names(["a b", "a-b"]) == ["a_b", "a_b_2"]

    def test_preserves_flattened_jsonl_names(self):
        """Flattened names are already SQLite-safe and must pass through intact"""
        columns = ["user__profile__name", "items_0", "tags_0__name"]

        assert clean_column_names(columns) == columns

    def test_colliding_keys_upload_successfully(self, test_db):
        result = convert_jsonl_to_sqlite(b'{"Name": 1, "name": 2}', "collisions", test_db)

        assert list(result['schema']) == ["name", "name_2"]
        assert result['row_count'] == 1
        assert result['sample_data'][0] == {"name": 1, "name_2": 2}


class TestConvertJsonlEdgeCases:
    """Hardening coverage driven by tests/assets/edge_cases.jsonl"""

    @pytest.fixture
    def edge_case_data(self, test_assets_dir):
        with open(test_assets_dir / "edge_cases.jsonl", 'rb') as f:
            return f.read()

    def test_edge_cases_fixture_converts(self, edge_case_data, test_db):
        result = convert_jsonl_to_sqlite(edge_case_data, "edge_cases", test_db)

        # One row per non-blank line
        assert result['row_count'] == 7
        # No nameless column leaked in
        assert "" not in result['schema']

    def test_edge_cases_every_discovered_field_is_a_column(self, edge_case_data, test_db):
        ordered_fields = discover_jsonl_fields_ordered(edge_case_data)
        result = convert_jsonl_to_sqlite(edge_case_data, "edge_cases", test_db)

        assert list(result['schema']) == ordered_fields

    def test_empty_collections_become_null_columns(self, edge_case_data, test_db):
        result = convert_jsonl_to_sqlite(edge_case_data, "edge_cases", test_db)

        # `tags: []` and `settings: {}` on line 1 keep the fields as NULL columns
        assert 'tags' in result['schema']
        assert 'settings' in result['schema']
        first_row = result['sample_data'][0]
        assert first_row['tags'] is None
        assert first_row['settings'] is None

    def test_explicit_null_and_boolean_values(self, edge_case_data, test_db):
        result = convert_jsonl_to_sqlite(edge_case_data, "edge_cases", test_db)

        first_row = result['sample_data'][0]
        assert first_row['note'] is None
        assert first_row['enabled'] == 1  # SQLite stores booleans as integers

    def test_deeply_nested_only_record(self, edge_case_data, test_db):
        result = convert_jsonl_to_sqlite(edge_case_data, "edge_cases", test_db)

        assert 'deep__level_two__level_three__level_four__value' in result['schema']

    def test_field_appearing_only_on_last_line_is_a_column(self, edge_case_data, test_db):
        result = convert_jsonl_to_sqlite(edge_case_data, "edge_cases", test_db)

        assert 'final_only' in result['schema']
        # Earlier rows hold NULL for it
        assert all(row['final_only'] is None for row in result['sample_data'])

    def test_mixed_types_across_lines_do_not_crash(self, edge_case_data, test_db):
        result = convert_jsonl_to_sqlite(edge_case_data, "edge_cases", test_db)

        assert 'score' in result['schema']

    def test_list_of_objects_is_index_flattened(self, edge_case_data, test_db):
        result = convert_jsonl_to_sqlite(edge_case_data, "edge_cases", test_db)

        assert 'items_0__sku' in result['schema']
        assert 'items_1__qty' in result['schema']


class TestConvertJsonlDeterminismAndOverwrite:

    def test_column_order_is_deterministic(self, test_assets_dir, test_db):
        with open(test_assets_dir / "complex_data.jsonl", 'rb') as f:
            jsonl_data = f.read()

        first = convert_jsonl_to_sqlite(jsonl_data, "events", test_db)
        second = convert_jsonl_to_sqlite(jsonl_data, "events", test_db)

        assert list(first['schema']) == list(second['schema'])

    def test_column_order_matches_pragma_table_info(self, test_assets_dir, tmp_path):
        with open(test_assets_dir / "complex_data.jsonl", 'rb') as f:
            jsonl_data = f.read()

        db_path = str(tmp_path / "order.db")
        result = convert_jsonl_to_sqlite(jsonl_data, "events", db_path)

        conn = sqlite3.connect(db_path)
        pragma_columns = [row[1] for row in conn.execute("PRAGMA table_info([events])")]
        conn.close()

        assert pragma_columns == list(result['schema'])

    def test_reupload_replaces_table(self, tmp_path):
        db_path = str(tmp_path / "replace.db")
        first_file = b'{"a": 1}\n{"a": 2}\n{"a": 3}'
        second_file = b'{"a": 9}'

        convert_jsonl_to_sqlite(first_file, "records", db_path)
        result = convert_jsonl_to_sqlite(second_file, "records", db_path)

        assert result['row_count'] == 1

        conn = sqlite3.connect(db_path)
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='records'"
            )
        ]
        conn.close()

        assert tables == ["records"]


class TestConvertJsonlLineHandling:

    def test_no_trailing_newline_keeps_last_record(self, test_db):
        result = convert_jsonl_to_sqlite(b'{"a": 1}\n{"a": 2}', "records", test_db)

        assert result['row_count'] == 2

    def test_interior_blank_lines_are_not_rows(self, test_db):
        result = convert_jsonl_to_sqlite(b'{"a": 1}\n\n{"a": 2}\n\n', "records", test_db)

        assert result['row_count'] == 2

    def test_crlf_line_endings(self, test_db):
        result = convert_jsonl_to_sqlite(
            b'{"name": "John"}\r\n{"name": "Jane"}\r\n', "records", test_db
        )

        assert result['row_count'] == 2
        assert list(result['schema']) == ["name"]
        assert result['sample_data'][0]['name'] == "John"

    def test_non_utf8_content(self, test_db):
        with pytest.raises(Exception) as exc_info:
            convert_jsonl_to_sqlite(b'\xff\xfe{"a": 1}', "records", test_db)

        assert "File is not valid UTF-8 encoded text" in str(exc_info.value)

    def test_hostile_filename_is_sanitized(self, test_db):
        result = convert_jsonl_to_sqlite(b'{"a": 1}', "drop table users;--", test_db)

        assert result['table_name'] == "drop_table_users___"
        assert result['row_count'] == 1
