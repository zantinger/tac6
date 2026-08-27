import json
import pandas as pd
import sqlite3
import io
import re
from typing import Dict, Any, Iterator, List, Set
from .sql_security import (
    execute_query_safely,
    validate_identifier,
    SQLSecurityError
)
from .constants import NESTED_DELIMITER, LIST_INDEX_DELIMITER

def sanitize_table_name(table_name: str) -> str:
    """
    Sanitize table name for SQLite by removing/replacing bad characters
    and validating against SQL injection
    """
    # Remove file extension if present
    if '.' in table_name:
        table_name = table_name.rsplit('.', 1)[0]
    
    # Replace bad characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', table_name)
    
    # Ensure it starts with a letter or underscore
    if sanitized and not sanitized[0].isalpha() and sanitized[0] != '_':
        sanitized = '_' + sanitized
    
    # Ensure it's not empty
    if not sanitized:
        sanitized = 'table'
    
    # Validate the sanitized name
    try:
        validate_identifier(sanitized, "table")
    except SQLSecurityError:
        # If validation fails, use a safe default
        sanitized = f"table_{hash(table_name) % 100000}"
    
    return sanitized

def clean_column_names(columns: List[str]) -> List[str]:
    """
    Normalize column names for SQLite and de-duplicate collisions.

    Lowercases, replaces spaces/dashes (and any other SQLite-hostile character)
    with underscores, guards against empty and digit-leading names, and appends
    _2, _3, ... to names that would otherwise collide.

    Args:
        columns: The raw column names, in order

    Returns:
        List of cleaned, unique column names in the same order
    """
    cleaned = []
    used = {}

    for column in columns:
        name = str(column).lower().replace(' ', '_').replace('-', '_')
        name = re.sub(r'[^a-z0-9_]', '_', name)

        # Guard against names SQLite/validate_identifier would reject
        if not name:
            name = 'column'
        if name[0].isdigit():
            name = f'col_{name}'

        # De-duplicate collisions (e.g. "Name" and "name" both clean to "name")
        if name in used:
            suffix = used[name]
            candidate = f'{name}_{suffix}'
            while candidate in used:
                suffix += 1
                candidate = f'{name}_{suffix}'
            used[name] = suffix + 1
            name = candidate
        used[name] = 2

        cleaned.append(name)

    return cleaned

def convert_csv_to_sqlite(csv_content: bytes, table_name: str, db_path: str = "db/database.db") -> Dict[str, Any]:
    """
    Convert CSV file content to SQLite table
    """
    try:
        # Sanitize table name
        table_name = sanitize_table_name(table_name)
        
        # Read CSV into pandas DataFrame
        df = pd.read_csv(io.BytesIO(csv_content))
        
        # Clean column names
        df.columns = clean_column_names(list(df.columns))
        
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        
        # Write DataFrame to SQLite
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        # Get schema information using safe query execution
        cursor_info = execute_query_safely(
            conn,
            "PRAGMA table_info({table})",
            identifier_params={'table': table_name}
        )
        columns_info = cursor_info.fetchall()
        
        schema = {}
        for col in columns_info:
            schema[col[1]] = col[2]  # column_name: data_type
        
        # Get sample data using safe query execution
        cursor_sample = execute_query_safely(
            conn,
            "SELECT * FROM {table} LIMIT 5",
            identifier_params={'table': table_name}
        )
        sample_rows = cursor_sample.fetchall()
        column_names = [col[1] for col in columns_info]
        sample_data = [dict(zip(column_names, row)) for row in sample_rows]
        
        # Get row count using safe query execution
        cursor_count = execute_query_safely(
            conn,
            "SELECT COUNT(*) FROM {table}",
            identifier_params={'table': table_name}
        )
        row_count = cursor_count.fetchone()[0]
        
        conn.close()
        
        return {
            'table_name': table_name,
            'schema': schema,
            'row_count': row_count,
            'sample_data': sample_data
        }
        
    except Exception as e:
        raise Exception(f"Error converting CSV to SQLite: {str(e)}")

def convert_json_to_sqlite(json_content: bytes, table_name: str, db_path: str = "db/database.db") -> Dict[str, Any]:
    """
    Convert JSON file content to SQLite table
    """
    try:
        # Sanitize table name
        table_name = sanitize_table_name(table_name)
        
        # Parse JSON
        data = json.loads(json_content.decode('utf-8'))
        
        # Ensure it's a list of objects
        if not isinstance(data, list):
            raise ValueError("JSON must be an array of objects")
        
        if not data:
            raise ValueError("JSON array is empty")
        
        # Convert to pandas DataFrame
        df = pd.DataFrame(data)
        
        # Clean column names
        df.columns = clean_column_names(list(df.columns))
        
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        
        # Write DataFrame to SQLite
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        # Get schema information using safe query execution
        cursor_info = execute_query_safely(
            conn,
            "PRAGMA table_info({table})",
            identifier_params={'table': table_name}
        )
        columns_info = cursor_info.fetchall()
        
        schema = {}
        for col in columns_info:
            schema[col[1]] = col[2]  # column_name: data_type
        
        # Get sample data using safe query execution
        cursor_sample = execute_query_safely(
            conn,
            "SELECT * FROM {table} LIMIT 5",
            identifier_params={'table': table_name}
        )
        sample_rows = cursor_sample.fetchall()
        column_names = [col[1] for col in columns_info]
        sample_data = [dict(zip(column_names, row)) for row in sample_rows]
        
        # Get row count using safe query execution
        cursor_count = execute_query_safely(
            conn,
            "SELECT COUNT(*) FROM {table}",
            identifier_params={'table': table_name}
        )
        row_count = cursor_count.fetchone()[0]
        
        conn.close()
        
        return {
            'table_name': table_name,
            'schema': schema,
            'row_count': row_count,
            'sample_data': sample_data
        }
        
    except Exception as e:
        raise Exception(f"Error converting JSON to SQLite: {str(e)}")

def flatten_json_object(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """
    Flatten a nested JSON object using delimiter constants.

    An empty list or object collapses to a single NULL leaf so that a field whose
    value is always empty still becomes a column instead of disappearing.

    Args:
        obj: The object to flatten (can be dict, list, or primitive)
        prefix: The current prefix for nested keys

    Returns:
        Dict with flattened key-value pairs
    """
    result = {}

    if isinstance(obj, dict):
        if not obj:
            # Empty object: keep the field as a NULL column
            if prefix:
                result[prefix] = None
            return result
        for key, value in obj.items():
            new_key = f"{prefix}{NESTED_DELIMITER}{key}" if prefix else key
            result.update(flatten_json_object(value, new_key))
    elif isinstance(obj, list):
        if not obj:
            # Empty list: keep the field as a NULL column
            if prefix:
                result[prefix] = None
            return result
        for i, value in enumerate(obj):
            new_key = f"{prefix}{LIST_INDEX_DELIMITER}{i}"
            result.update(flatten_json_object(value, new_key))
    else:
        # Primitive value (string, number, boolean, null)
        result[prefix] = obj

    return result

def iter_flattened_jsonl_records(jsonl_content: bytes) -> Iterator[Dict[str, Any]]:
    """
    Parse a JSONL file line by line and yield one flattened record per non-blank line.

    Single source of truth for JSONL parsing: both the field-discovery pass and the
    record-building pass go through here, so line numbering and error wording stay
    consistent between them.

    Args:
        jsonl_content: The raw JSONL file content

    Yields:
        Flattened {field_name: primitive} dict for each non-blank line

    Raises:
        ValueError: On non-UTF-8 content, invalid JSON, or a line that is not a
            JSON object. Errors name the 1-based line number.
    """
    try:
        content = jsonl_content.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError("File is not valid UTF-8 encoded text")

    for line_num, line in enumerate(content.split('\n'), 1):
        line = line.strip()
        if not line:
            continue

        try:
            json_obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON on line {line_num}: {str(e)}")

        # Only JSON objects can become table rows; a bare scalar or array would
        # otherwise produce a nameless "" column or bogus _0, _1 columns
        if not isinstance(json_obj, dict):
            raise ValueError(
                f"Line {line_num}: JSONL lines must be JSON objects, "
                f"got {type(json_obj).__name__}"
            )

        yield flatten_json_object(json_obj)

def discover_jsonl_fields_ordered(jsonl_content: bytes) -> List[str]:
    """
    Discover all possible field names by scanning the entire JSONL file, in
    first-seen order.

    Ordering matters: it pins the generated table's column order so that converting
    the same file twice always produces the same schema.

    Args:
        jsonl_content: The raw JSONL file content

    Returns:
        List of all flattened field names, in the order they first appear
    """
    # A dict preserves insertion order, giving us an ordered set
    ordered_fields: Dict[str, None] = {}

    for flattened in iter_flattened_jsonl_records(jsonl_content):
        for field in flattened:
            ordered_fields.setdefault(field, None)

    return list(ordered_fields)

def discover_jsonl_fields(jsonl_content: bytes) -> Set[str]:
    """
    Discover all possible field names by scanning the entire JSONL file.

    Args:
        jsonl_content: The raw JSONL file content

    Returns:
        Set of all flattened field names found in the file
    """
    return set(discover_jsonl_fields_ordered(jsonl_content))

def convert_jsonl_to_sqlite(jsonl_content: bytes, table_name: str, db_path: str = "db/database.db") -> Dict[str, Any]:
    """
    Convert JSONL file content to SQLite table with flattened structure.
    
    Args:
        jsonl_content: The raw JSONL file content
        table_name: Name for the SQLite table
        
    Returns:
        Dict containing table info, schema, row count, and sample data
    """
    conn = None
    try:
        # Sanitize table name
        table_name = sanitize_table_name(table_name)

        # First pass: discover all possible fields, in first-seen order so the
        # resulting column order is deterministic across runs
        ordered_fields = discover_jsonl_fields_ordered(jsonl_content)

        if not ordered_fields:
            raise ValueError("No valid JSON objects found in JSONL file")

        # Second pass: process each line and create consistent records
        records = []
        for flattened in iter_flattened_jsonl_records(jsonl_content):
            # Create record with all fields, filling missing ones with None
            records.append({field: flattened.get(field) for field in ordered_fields})

        if not records:
            raise ValueError("No valid records found in JSONL file")

        # Convert to pandas DataFrame, pinning the discovered column order
        df = pd.DataFrame(records, columns=ordered_fields)

        # Clean column names for SQLite compatibility
        df.columns = clean_column_names(list(df.columns))

        # Connect to SQLite database
        conn = sqlite3.connect(db_path)

        # Write DataFrame to SQLite
        df.to_sql(table_name, conn, if_exists='replace', index=False)

        # Get schema information using safe query execution
        cursor_info = execute_query_safely(
            conn,
            "PRAGMA table_info({table})",
            identifier_params={'table': table_name}
        )
        columns_info = cursor_info.fetchall()

        schema = {}
        for col in columns_info:
            schema[col[1]] = col[2]  # column_name: data_type

        # Get sample data using safe query execution
        cursor_sample = execute_query_safely(
            conn,
            "SELECT * FROM {table} LIMIT 5",
            identifier_params={'table': table_name}
        )
        sample_rows = cursor_sample.fetchall()
        column_names = [col[1] for col in columns_info]
        sample_data = [dict(zip(column_names, row)) for row in sample_rows]

        # Get row count using safe query execution
        cursor_count = execute_query_safely(
            conn,
            "SELECT COUNT(*) FROM {table}",
            identifier_params={'table': table_name}
        )
        row_count = cursor_count.fetchone()[0]

        return {
            'table_name': table_name,
            'schema': schema,
            'row_count': row_count,
            'sample_data': sample_data
        }

    except Exception as e:
        raise Exception(f"Error converting JSONL to SQLite: {str(e)}")
    finally:
        # Never leak a handle, even when a mid-file error aborts the conversion
        if conn is not None:
            conn.close()
