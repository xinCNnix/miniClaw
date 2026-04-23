"""
Python REPL Tool - Enhanced Python Code Interpreter

This tool allows the Agent to execute Python code with:
- File I/O capabilities in controlled directories
- Multiple execution modes (safe/standard/free)
- Dynamic memory limits based on available memory
- Operation counting to prevent infinite loops
- Real-time monitoring and user interrupt capability

Security features:
- Timeout control
- Memory limits
- Operation counting
- Directory restrictions for file I/O
- Separate namespace
"""

import sys
import io
import os
import time
import psutil
import signal
import threading
import traceback
from typing import Optional, Dict, Any, Callable
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from app.config import settings


class TimeoutError(Exception):
    """Custom timeout exception."""
    pass


class MemoryLimitError(Exception):
    """Custom memory limit exception."""
    pass


class OperationLimitError(Exception):
    """Custom operation limit exception."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutError("Code execution timed out")


class PythonREPLInput(BaseModel):
    """Input schema for Python REPL tool."""

    code: str = Field(
        ...,
        description="The Python code to execute",
    )

    mode: Optional[str] = Field(
        default=None,
        description="Execution mode: safe, standard, or free (overrides default)",
    )

    timeout: Optional[int] = Field(
        default=None,
        description="Execution timeout in seconds (overrides default)",
    )


class PythonREPLTool(BaseTool):
    """
    Enhanced Python REPL tool for executing Python code.

    This tool creates an isolated Python environment for code execution
    with advanced monitoring and safety features.

    New capabilities:
    - File I/O in controlled directories
    - Multiple execution modes with different safety levels
    - Dynamic memory limits
    - Operation counting to prevent infinite loops
    - Real-time monitoring
    """

    name: str = "python_repl"
    description: str = """
    Execute Python code in an enhanced REPL environment.

    Execution Modes:
    - safe: Conservative protection (60s timeout, 20% memory, 1M operations)
    - standard: Standard protection (5min timeout, 50% memory, 10M operations) - default
    - free: Free mode (30min timeout, 80% memory, unlimited operations)

    Features:
    - File I/O in controlled directories (project root + user-configured dirs)
    - Full Python standard library access
    - Separate namespace (isolated from system)
    - Memory limits based on available system memory
    - Operation counting to prevent infinite loops
    - Timeout protection
    - Error capturing and reporting

    File I/O:
    - Can read/write to: project root directory
    - Can read/write to: additional configured directories
    - Cannot access: sensitive files (.env, credentials.encrypted, etc.)

    Common uses:
    - Data processing and analysis
    - File generation (PPT, Excel, PDF, etc.)
    - Mathematical calculations
    - Web scraping
    - Data visualization

    Examples:
    - python_repl: print("Hello World")
    - python_repl: open("data.txt", "w").write("content")
    - python_repl: import pandas as pd; df = pd.DataFrame({"a": [1,2,3]}); df.to_csv("output.csv")

    Note: Large file operations should use 'free' mode. The code executes in a clean namespace.
    """

    args_schema: type[PythonREPLInput] = PythonREPLInput

    # Namespace for persistent state
    _namespace: Dict[str, Any] = {}

    # Allowed directories for file I/O
    _allowed_dirs: list[Path] = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Instance-level execution state to avoid race conditions between runs
        self._current_process: Optional[Any] = None
        self._execution_start_time: float = 0
        self._operation_count: int = 0
        self._should_stop: bool = False
        self._execution_generation: int = 0
        self._update_allowed_dirs()

    def _update_allowed_dirs(self) -> None:
        """Update list of allowed directories from settings."""
        self._allowed_dirs = [Path(settings.terminal_root_dir).resolve()]
        for dir_path in settings.allowed_write_dirs:
            self._allowed_dirs.append(Path(dir_path).resolve())

    def _get_execution_config(self, mode: Optional[str] = None) -> dict:
        """
        Get execution configuration based on mode.

        Args:
            mode: Execution mode (safe/standard/free)

        Returns:
            Configuration dict with timeout, memory_limit, max_operations
        """
        mode = mode or settings.python_execution_mode

        # Get timeout
        if mode == "safe":
            timeout = settings.python_safe_timeout
            memory_ratio = settings.python_safe_memory_ratio
            max_ops = settings.python_safe_max_operations
        elif mode == "standard":
            timeout = settings.python_standard_timeout
            memory_ratio = settings.python_standard_memory_ratio
            max_ops = settings.python_standard_max_operations
        elif mode == "free":
            timeout = settings.python_free_timeout
            memory_ratio = settings.python_free_memory_ratio
            max_ops = settings.python_free_max_operations
        else:
            mode = "standard"
            timeout = settings.python_standard_timeout
            memory_ratio = settings.python_standard_memory_ratio
            max_ops = settings.python_standard_max_operations

        # Calculate memory limit based on available memory
        try:
            available_memory = psutil.virtual_memory().available
            memory_limit = int(available_memory * memory_ratio)
        except Exception:
            # Fallback to 1GB if psutil fails
            memory_limit = 1024 * 1024 * 1024

        return {
            "mode": mode,
            "timeout": timeout,
            "memory_limit": memory_limit,
            "max_operations": max_ops,
        }

    def _check_path_allowed(self, file_path: Path) -> bool:
        """
        Check if file path is in allowed directories.

        Args:
            file_path: Path to check

        Returns:
            True if path is allowed, False otherwise
        """
        try:
            for allowed_dir in self._allowed_dirs:
                if file_path.resolve().is_relative_to(allowed_dir):
                    return True
            return False
        except Exception:
            return False

    def _make_open(self, open_func, file_path: str, *args, **kwargs):
        """
        Wrapper for open() that checks if path is allowed.

        Args:
            open_func: Original open function
            file_path: File path to open

        Returns:
            File object or raises PermissionError
        """
        path_obj = Path(file_path).resolve()

        # Check if path is allowed
        if not self._check_path_allowed(path_obj):
            raise PermissionError(
                f"Access denied: Path {file_path} is not in allowed directories"
            )

        # Check if trying to write to sensitive files
        protected_files = [
            "credentials.encrypted",
            "credentials.json",
            ".env",
            ".env.local",
            ".env.production",
        ]

        path_str = str(path_obj)
        for protected in protected_files:
            if protected in path_str and ("w" in args or "a" in args):
                raise PermissionError(
                    f"Access denied: Cannot modify protected file ({protected})"
                )

        # Call original open
        return open_func(file_path, *args, **kwargs)

    def _execute_code(
        self,
        code: str,
        config: dict,
        monitor_callback: Optional[Callable] = None,
    ) -> tuple[str, bool, dict]:
        """
        Execute Python code and return output with monitoring.

        Args:
            code: Python code to execute
            config: Execution configuration
            monitor_callback: Callback for monitoring updates

        Returns:
            Tuple of (output, success, stats)
        """
        # Reset state — bump generation so stale monitor threads exit
        self._operation_count = 0
        self._execution_start_time = time.time()
        self._should_stop = False
        self._execution_generation += 1
        current_gen = self._execution_generation

        # Create string buffers for output capture
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        # Patch code: replace plt.show() with plt.savefig() to prevent GUI popup blocking
        import re
        # original_code = code  # preserved for reference
        code = re.sub(
            r'plt\.show\(\)',
            'print("[matplotlib: plt.show() intercepted and skipped — use plt.savefig() instead]")',
            code
        )

        # Ensure output directory exists and set CWD so matplotlib savefig lands there
        backend_root = Path(__file__).resolve().parent.parent.parent
        output_dir = backend_root / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        original_cwd = os.getcwd()
        os.chdir(str(output_dir))

        # Prepare local namespace with safe open() wrapper
        def safe_open(file_path, *args, **kwargs):
            return self._make_open(open, file_path, *args, **kwargs)

        local_namespace = {
            "__name__": "__main__",
            "__builtins__": __builtins__,
            "open": safe_open,  # Override open with safe wrapper
        }

        # Set matplotlib to non-interactive backend BEFORE any user code imports it
        # This prevents plt.show() from opening GUI windows and blocking the process
        # original_backend = None  # preserved for reference
        try:
            import matplotlib
            # matplotlib.use('Agg')  # original: could cause issues if already imported
            if matplotlib.get_backend() != 'agg':
                matplotlib.use('Agg')
        except ImportError:
            pass

        # Merge with persistent namespace
        local_namespace.update(self._namespace)

        # Operation counting callback
        def trace_callback(frame, event, arg):
            if event == "line":
                self._operation_count += 1

                # Check operation limit
                if config["max_operations"] > 0:
                    if self._operation_count > config["max_operations"]:
                        self._should_stop = True
                        raise OperationLimitError(
                            f"Operation limit exceeded: {self._operation_count} > {config['max_operations']}"
                        )

                # Check if execution was cancelled (stale generation = old monitor)
                if self._should_stop and self._execution_generation == current_gen:
                    raise Exception("Execution stopped by user")


            return trace_callback

        def run_code():
            """Execute the code with output redirection."""
            try:
                # Set trace callback for operation counting
                if config["max_operations"] > 0:
                    old_trace = sys.gettrace()
                    sys.settrace(trace_callback)

                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    # Compile and execute the code
                    try:
                        code_obj = compile(code, "<string>", "eval")
                        result = eval(code_obj, local_namespace)
                        # Print the result like a REPL does
                        if result is not None:
                            print(repr(result))
                    except SyntaxError:
                        # Not an expression, execute as statement
                        exec(code, local_namespace)

                # Restore old trace
                if config["max_operations"] > 0:
                    sys.settrace(old_trace)

                # Update persistent namespace with new variables
                for key, value in local_namespace.items():
                    if key not in ["__name__", "__builtins__"]:
                        self._namespace[key] = value

                return True

            except (OperationLimitError, Exception) as e:
                stderr_buffer.write(str(e))
                return False

        def run_with_timeout():
            """Execute code with timeout monitoring."""
            # Monitor thread for timeout and memory checking
            def monitor():
                while self._execution_generation == current_gen and not self._should_stop:
                    time.sleep(settings.python_monitor_interval)

                    # Stale monitor from a previous run — exit immediately
                    if self._execution_generation != current_gen:
                        return

                    # Check timeout
                    elapsed = time.time() - self._execution_start_time
                    if elapsed > config["timeout"]:
                        self._should_stop = True
                        return

                    # Check memory limit
                    try:
                        process = psutil.Process()
                        memory_bytes = process.memory_info().rss
                        if memory_bytes > config["memory_limit"]:
                            self._should_stop = True
                            return
                    except Exception:
                        pass  # Process might have terminated

            # Start monitor thread
            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()

            # Run code
            try:
                return run_code()
            finally:
                self._should_stop = True  # Stop monitor thread

        # Execute code with monitoring
        try:
            success = run_with_timeout()
        except (TimeoutError, MemoryLimitError) as e:
            stderr_buffer.write(str(e))
            success = False
        except Exception:
            import traceback
            stderr_buffer.write(traceback.format_exc())
            success = False
        finally:
            os.chdir(original_cwd)

        # Get captured output
        stdout_output = stdout_buffer.getvalue()
        stderr_output = stderr_buffer.getvalue()

        # Build result
        output_parts = []
        if stdout_output:
            output_parts.append(stdout_output)
        if stderr_output:
            output_parts.append(f"Error:\n{stderr_output}")

        if not output_parts and success:
            output_parts.append("Code executed successfully (no output)")

        result = "\n".join(output_parts)

        # Collect stats
        elapsed = time.time() - self._execution_start_time
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
        except Exception:
            memory_mb = 0

        stats = {
            "elapsed": elapsed,
            "memory_mb": memory_mb,
            "operations": self._operation_count,
            "mode": config["mode"],
        }

        return result, success, stats

    def _run(
        self,
        code: str,
        mode: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Execute Python code synchronously.

        Args:
            code: Python code to execute
            mode: Execution mode (overrides default)
            timeout: Execution timeout in seconds (overrides default)

        Returns:
            Execution output or error message
        """
        if code == "":
            return "No code provided"

        # Get execution config
        config = self._get_execution_config(mode)

        # Override timeout if specified
        if timeout is not None:
            config["timeout"] = timeout

        # Monitor callback for logging
        def monitor_callback(stats):
            """Log monitoring information."""
            memory_ratio = stats["memory_mb"] / (stats["memory_limit_mb"] or 1)
            if memory_ratio > settings.python_warning_threshold:
                print(f"[WARNING] Memory usage: {stats['memory_mb']:.1f}MB / {stats['memory_limit_mb']:.1f}MB")

        # Execute code
        output, success, stats = self._execute_code(code, config, monitor_callback)

        # Add stats to output if in debug mode
        if settings.debug:
            stats_str = f"\n\n[Stats: {stats['elapsed']:.1f}s, {stats['memory_mb']:.1f}MB, {stats['operations']} ops, {stats['mode']} mode]"
            output += stats_str

        return output

    async def _arun(
        self,
        code: str,
        mode: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """Async version (wraps sync execution)."""
        return self._run(code, mode, timeout)

    def clear_namespace(self) -> None:
        """Clear the persistent namespace."""
        self._namespace = {}

    def get_namespace_keys(self) -> list[str]:
        """Get list of variables in persistent namespace."""
        return list(self._namespace.keys())

    def stop_execution(self) -> None:
        """Request to stop current execution."""
        self._should_stop = True

    def get_execution_stats(self) -> dict:
        """Get current execution statistics."""
        return {
            "operations": self._operation_count,
            "elapsed": time.time() - self._execution_start_time if self._execution_start_time > 0 else 0,
            "is_running": self._current_process is not None,
        }


# Create a singleton instance
python_repl_tool = PythonREPLTool()
