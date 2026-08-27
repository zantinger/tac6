# Natural Language SQL Interface

A web application that converts natural language queries to SQL using AI, built with FastAPI and Vite + TypeScript.

## Features

- 🗣️ Natural language to SQL conversion using OpenAI or Anthropic
- 📁 Drag-and-drop file upload (.csv, .json, and .jsonl)
- 📊 Interactive table results display
- 🔒 SQL injection protection
- ⚡ Fast development with Vite and uv

## Prerequisites

- Python 3.10+
- uv (Python package manager)
- Node.js 18+
- Bun (or your preferred npm tool: npm, yarn, etc.)
- OpenAI API key and/or Anthropic API key

## Setup

### 1. Install Dependencies

```bash
# Backend
cd app/server
uv sync --all-extras

# Frontend
cd app/client
bun install
```

### 2. Environment Configuration

Set up your API keys in the server directory:

```bash
cd app/server
cp .env.sample .env
# Edit .env and add your API keys
```

## Quick Start

Use the provided script to start both services:

```bash
./scripts/start.sh
```

Press `Ctrl+C` to stop both services.

The script will:
- Check that `.env` exists in `app/server/`
- Start the backend on http://localhost:8000
- Start the frontend on http://localhost:5173
- Handle graceful shutdown when you exit

## Manual Start (Alternative)

### Backend
```bash
cd app/server
# .env is loaded automatically by python-dotenv
uv run python server.py
```

### Frontend
```bash
cd app/client
bun run dev
```

## Usage

1. **Upload Data**: Click "Upload Data" to open the modal
   - Use sample data buttons for quick testing
   - Or drag and drop your own .csv, .json, or .jsonl files
   - Uploading a file with the same name will overwrite the existing table
2. **Query Your Data**: Type a natural language query like "Show me all users who signed up last week"
   - Press `Cmd+Enter` (Mac) or `Ctrl+Enter` (Windows/Linux) to run the query
3. **View Results**: See the generated SQL and results in a table format
4. **Manage Tables**: Click the × button on any table to remove it

### JSONL Support

A `.jsonl` file (one JSON object per line) becomes exactly one table, just like a `.csv`.
Because SQLite tables are flat, nested structures are flattened into one column per leaf value:

| JSONL value | Generated column(s) |
| --- | --- |
| `{"user": {"profile": {"name": "John"}}}` | `user__profile__name` |
| `{"items": ["a", "b"]}` | `items_0`, `items_1` |
| `{"tags": [{"name": "t1"}]}` | `tags_0__name` |
| `{"tags": []}` or `{"settings": {}}` | `tags` / `settings` with a `NULL` value |

Details worth knowing:

- **The whole file is scanned before the table is created.** The column set is the union of
  every field on every line, so a field that appears only on the last line is still a column —
  rows that lack it hold `NULL` instead of the upload failing or dropping data.
- **Column order is deterministic**, following the order fields first appear in the file.
- **Every line must be a JSON object.** A bare scalar or array line fails with a
  line-numbered error rather than creating a nameless column.
- **Colliding column names are de-duplicated** (`"Name"` and `"name"` become `name` and
  `name_2`), so keys that differ only by case or separator don't break the upload.
- **Both delimiters are configurable** in `app/server/core/constants.py`
  (`NESTED_DELIMITER = "__"`, `LIST_INDEX_DELIMITER = "_"`). Changing them there changes
  every generated column name with no other code edit.
- **Known ambiguity:** a literal key `"a__b"` is indistinguishable from nested
  `{"a": {"b": ...}}`, and a literal key `"items_0"` collides with index 0 of an `items`
  list. Such collisions are de-duplicated rather than escaped, keeping the common case readable.

## Development

### Backend Commands
```bash
cd app/server
uv run python server.py      # Start server with hot reload
uv run pytest               # Run tests
uv add <package>            # Add package to project
uv remove <package>         # Remove package from project
uv sync --all-extras        # Sync all extras
```

### Frontend Commands
```bash
cd app/client
bun run dev                 # Start dev server
bun run build              # Build for production
bun run preview            # Preview production build
```

## Project Structure

```
.
├── app/                    # Main application
│   ├── client/             # Vite + TypeScript frontend
│   └── server/             # FastAPI backend
│
├── adws/                   # AI Developer Workflow (ADW) - GitHub issue automation system
├── scripts/                # Utility scripts (start.sh, stop_apps.sh)
├── specs/                  # Feature specifications
├── ai_docs/                # AI/LLM documentation
├── agents/                 # Agent execution logging
└── logs/                   # Structured session logs
```

## API Endpoints

- `POST /api/upload` - Upload CSV/JSON/JSONL file
- `POST /api/query` - Process natural language query
- `GET /api/schema` - Get database schema
- `POST /api/insights` - Generate column insights
- `GET /api/health` - Health check

## Security

### SQL Injection Protection

The application implements comprehensive SQL injection protection through multiple layers:

1. **Centralized Security Module** (`core/sql_security.py`):
   - Identifier validation for table and column names
   - Safe query execution with parameterized queries
   - Proper escaping for identifiers using SQLite's square bracket notation
   - Dangerous operation detection and blocking

2. **Input Validation**:
   - All table and column names are validated against a whitelist pattern
   - SQL keywords cannot be used as identifiers
   - File names are sanitized before creating tables
   - User queries are validated for dangerous operations

3. **Query Execution Safety**:
   - Parameterized queries used wherever possible
   - Identifiers (table/column names) are properly escaped
   - Multiple statement execution is blocked
   - SQL comments are not allowed in queries

4. **Protected Operations**:
   - File uploads with malicious names are sanitized
   - Natural language queries cannot inject SQL
   - Table deletion uses validated identifiers
   - Data insights generation validates all inputs

### Security Best Practices for Development

When adding new SQL functionality:
1. Always use the `sql_security` module functions
2. Never concatenate user input directly into SQL strings
3. Use `execute_query_safely()` for all database operations
4. Validate all identifiers with `validate_identifier()`
5. For DDL operations, use `allow_ddl=True` explicitly

### Testing Security

Run the comprehensive security tests:
```bash
cd app/server
uv run pytest tests/test_sql_injection.py -v
```


### Additional Security Features

- CORS configured for local development only
- File upload validation (CSV, JSON, and JSONL only)
- Comprehensive error logging without exposing sensitive data
- Database operations are isolated with proper connection handling

## AI Developer Workflow (ADW)

The ADW system is a comprehensive automation framework that integrates GitHub issues with Claude Code CLI to classify issues, generate implementation plans, and automatically create pull requests. ADW processes GitHub issues by classifying them as `/chore`, `/bug`, or `/feature` commands and then implementing solutions autonomously.

### Prerequisites

Before using ADW, ensure you have the following installed and configured:

- **GitHub CLI**: `brew install gh` (macOS) or equivalent for your OS
- **Claude Code CLI**: Install from [Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code)
- **Python with uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **GitHub authentication**: `gh auth login`

### Environment Variables

Set these environment variables before running ADW:

```bash
export GITHUB_REPO_URL="https://github.com/owner/repository"
export ANTHROPIC_API_KEY="sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export CLAUDE_CODE_PATH="/path/to/claude"  # Optional, defaults to "claude"
export GITHUB_PAT="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # Optional, only if using different account than 'gh auth login'
```

### Usage Modes

ADW supports three main operation modes:

#### 1. Manual Processing
Process a single GitHub issue manually:
```bash
cd adws/
uv run adw_plan_build.py <issue-number>
```

#### 2. Automated Monitoring
Continuously monitor GitHub for new issues (polls every 20 seconds):
```bash
cd adws/
uv run trigger_cron.py
```

#### 3. Webhook Server
Start a webhook server for real-time GitHub event processing:
```bash
cd adws/
uv run trigger_webhook.py
```

### How ADW Works

1. **Issue Classification**: Analyzes GitHub issues and determines type (`/chore`, `/bug`, `/feature`)
2. **Planning**: Generates detailed implementation plans using Claude Code CLI
3. **Implementation**: Executes the plan by making code changes, running tests, and ensuring quality
4. **Integration**: Creates git commits and pull requests with semantic commit messages

### For More Information

For detailed technical documentation, configuration options, and troubleshooting, see [`adws/README.md`](adws/README.md).

## Troubleshooting

**Backend won't start:**
- Check Python version: `python --version` (requires 3.12+)
- Verify API keys are set: `echo $OPENAI_API_KEY`

**Frontend errors:**
- Clear node_modules: `rm -rf node_modules && bun install`
- Check Node version: `node --version` (requires 18+)

**CORS issues:**
- Ensure backend is running on port 8000
- Check vite.config.ts proxy settings