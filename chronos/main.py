import ast
import copy
import inspect
import logging
from collections import defaultdict
from typing import Dict, List, Tuple, Type

import click

FUNCTION_DEF_KEY_SUFFIX = "FUNC_DEF"

STEP_OVER = "o"
STEP_INTO = "i"
STEP_BACK = "b"

logger = logging.getLogger(__name__)


class Debugger:
    def __init__(self):
        self.states_across_time = []

    def run(self, path: str) -> None:
        """Read file to execute and execute it."""
        stack = []
        frame = defaultdict()

        frame["locals"] = {}
        frame["globals"] = {}

        stack.append(frame)

        try:
            with open(path, "r") as f:
                current_code = f.read()
        except IOError:
            raise SystemError(f"Cannot read path {path}")

        self._run(current_code, stack)

    def get_executable_str(self, node: Type[ast.mod], code_lines: List[str]) -> str:
        executable_str = ""

        line_start = node.lineno - 1
        line_end = node.end_lineno
        col_offset = end_col_offset = 0

        for i in range(line_start, line_end):

            if i == line_start:
                col_offset = node.col_offset
            if i == line_end - 1:
                end_col_offset = node.end_col_offset

            end = end_col_offset + 1 if end_col_offset else len(code_lines[i])
            executable_str += code_lines[i][col_offset:end] + "\n"
            col_offset = end_col_offset = 0

        return executable_str

    def _run(self, current_code: str, stack: List[Dict]) -> None:
        """Parse code into tree and execute whole tree."""

        try:
            syntax_tree = ast.parse(current_code)
        except ValueError as e:
            print(f"Cannot parse into abstract syntax tree, {e}")

        ast_stack = list(reversed(syntax_tree.body))
        self.states_across_time.append((copy.deepcopy(ast_stack), copy.deepcopy(stack)))

        # Execute code until exception
        while ast_stack:

            node = ast_stack.pop()
            executable_str = self.get_executable_str(node, current_code.splitlines())

            # Save function def in stack
            if type(node) is ast.FunctionDef:
                stack[-1]["locals"][
                    node.name + FUNCTION_DEF_KEY_SUFFIX
                ] = executable_str

            try:
                frame = self._step_over(executable_str, stack)
                stack.append(frame)

                self.states_across_time.append(
                    (copy.deepcopy(ast_stack), copy.deepcopy(stack))
                )
                continue
            except Exception as e:
                print(f"Encountered exception {e}. Starting interactive session.")
                self.interactive_session(ast_stack, current_code, stack)

    def interactive_session(
        self, ast_stack: List[Type[ast.mod]], current_code: str, stack: List[Dict]
    ) -> None:
        """Get instructions from user and execute them."""
        while ast_stack:
            node = ast_stack.pop()
            executable_str = self.get_executable_str(node, current_code.splitlines())
            action = click.prompt("Enter: o, i, b, out", type=str)

            self.print_code(executable_str)

            # Save function def in stack
            if type(node) is ast.FunctionDef:
                stack[-1]["locals"][
                    node.name + FUNCTION_DEF_KEY_SUFFIX
                ] = executable_str

            # Step back
            if action.lower().strip() == STEP_BACK:
                ast_stack, stack = self._step_back()

            # Step into
            if action.lower().strip() == STEP_INTO:
                if type(node.value) is ast.Call:
                    inner_ast, frame = self._step_into(node, stack)
                    ast_stack.extend(reversed(inner_ast))
                else:
                    print("Can't step into non function call. Stepping over.")
                    action = STEP_OVER

            # Step over
            if action.lower().strip() == STEP_OVER:
                frame = self._step_over(executable_str, stack)

            # Update states
            if frame:
                stack.append(frame)

            self.states_across_time.append(
                (copy.deepcopy(ast_stack), copy.deepcopy(stack))
            )

    def _run_executor(self, executable_str: str, frame: Dict) -> Dict:
        """Execute code."""
        try:
            exec(executable_str, frame.get("globals", None), frame.get("locals", None))
        except Exception as e:
            print(f"Exception executing str {executable_str}, {e}")

        _locals = copy.deepcopy(inspect.currentframe().f_locals)

        del _locals["frame"]
        del _locals["self"]

        frame["locals"] = {**frame.get("locals", {}), **_locals}
        frame["globals"] = {**frame.get("globals", {}), **_locals}

        return frame

    def _step_back(self) -> Tuple[List[Type[ast.mod]], List[Dict]]:
        """Step back to the previous code and state."""
        self.states_across_time.pop()
        ast_stack, stack = self.states_across_time.pop()
        return ast_stack, stack

    def _step_over(self, executable_str: str, stack: List[Dict]) -> Dict:
        """Execute current line."""
        return self._run_executor(executable_str.strip(), stack.pop())

    def _step_into(
        self, node: Type[ast.mod], stack: List[Dict]
    ) -> Tuple[Type[ast.AST], Dict]:
        """Step into a new call frame."""
        prev_frame = stack[-1]
        func_name = node.value.func.id + FUNCTION_DEF_KEY_SUFFIX

        cur_frame = defaultdict()
        cur_frame["globals"] = {**prev_frame["locals"], **prev_frame["globals"]}
        cur_frame["locals"] = {}

        try:
            executable_str = self._resolve(prev_frame, func_name)
        except KeyError:
            raise SystemError(f"{func_name} not defined in calling frame.")

        return ast.parse(executable_str), cur_frame

    def _resolve(self, frame: Dict, name: str) -> str:
        """Resolve name in frame in order of expanding scope."""
        if "locals" in frame:
            if name in frame["locals"]:
                return frame["locals"][name]

        if "globals" in frame:
            if name in frame["globals"]:
                return frame["globals"][name]

        raise SystemError(f"Unable to resolve {name} in frame {frame}")

    def print_code(self, code: str) -> None:
        """Print code in a readable manner."""
        print("\n\n")
        print(code)
        print("\n\n")
