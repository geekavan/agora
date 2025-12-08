# Changelog

All notable changes to the Agora AI Council project will be documented in this file.

## [Unreleased] - 2024

### 🔒 Security Fixes
- **Fixed path traversal vulnerability** in file write operations
  - Added absolute path validation to prevent writing outside project directory
  - Automatically creates parent directories safely
  - Location: `agora_telegram.py:button_callback()`

- **Fixed command injection vulnerability** in `/ls` command
  - Replaced `subprocess.getoutput()` with Python's built-in `os.listdir()`
  - Eliminates shell command injection risks
  - Location: `agora_telegram.py:cmd_ls()`

- **Improved exception handling**
  - Replaced bare `except:` with specific exception types
  - Added proper logging for debugging
  - Location: `agora_telegram.py:get_project_tree()`

### 🔧 Bug Fixes
- **Fixed hardcoded absolute path** in `install.sh`
  - Now automatically detects script location
  - Works from any installation directory
  - Supports GitHub repository cloning anywhere

### ✨ Improvements
- **Extracted duplicate code** into reusable function
  - Created `process_ai_response()` to handle AI response parsing
  - Eliminates code duplication between discussion and single-agent modes
  - Better maintainability and consistency

- **Optimized startup scripts**
  - `agora`: Global command for use anywhere
  - `start.sh`: Simplified local development script
  - Clear separation of concerns

### 📦 New Files
- **`.env.example`**: Configuration template with detailed comments
  - Helps users understand required environment variables
  - Documents optional configuration parameters
  - Includes AI CLI setup instructions

- **`.gitignore`**: Comprehensive ignore patterns
  - Protects sensitive `.env` files
  - Ignores Python cache and build artifacts
  - Excludes IDE-specific files

### 🛠️ Technical Improvements
- Better error logging throughout the codebase
- More robust fallback mechanisms for project tree generation
- Improved path handling for cross-platform compatibility
- Enhanced security validation for file operations

### 📚 Documentation
- Added detailed inline comments for regex patterns
- Improved function docstrings with type hints
- Enhanced error messages for better user experience

---

## Previous Versions

### [2.0] - Initial Enhanced Version
- Multi-AI roundtable discussion
- Intelligent agent detection
- Consensus detection mechanism
- File write confirmation system
- Real-time Telegram chat interface
- Discussion state management
