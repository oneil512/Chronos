import ast
import copy
import inspect
import logging
from collections import defaultdict
from typing import Dict, List, Tuple, Type

import click

FUNCTION_DEF_KEY_SUFFIX = "FUNC_DEF"

logger = logging.getLogger(__name__)


class Debugger:
    def __init__(self):
        self.states_across_time = []

    def run(self, path: str) -> None:
        """Read file to execute and execute it."""
        stack = [defaultdict()]

        try:
            with open(path, "r") as f:
                current_code = f.read()
        except IOError:
            raise SystemError(f"Cannot read path {path}")

        self._run(current_code, stack)

    def _run(self, current_code: str, stack: List[Dict]) -> None:
        """Parse code into tree and execute whole tree."""
        try:
            syntax_tree = ast.parse(current_code)
        except ValueError as e:
            raise SystemError(f"Cannot parse into abstract syntax tree, {e}")

        code_lines = current_code.splitlines()
        ast_stack = list(reversed(syntax_tree.body))

        self.states_across_time.append((copy.deepcopy(ast_stack), copy.deepcopy(stack)))

        while ast_stack:
            node = ast_stack.pop()

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

            self.print_code(executable_str)
            step = click.prompt("Enter: o, i, b, out", type=str)

            if type(node) is ast.FunctionDef:
                if not stack[-1].get("locals"):
                    stack[-1]["locals"] = defaultdict()

                stack[-1]["locals"][
                    node.name + FUNCTION_DEF_KEY_SUFFIX
                ] = executable_str

            if step.lower().strip() == "b":
                self.states_across_time.pop()
                ast_stack, stack = self.states_across_time.pop()
                continue

            if step.lower().strip() == "i":

                if type(node.value) is ast.Call:

                    inner_ast, frame = self._step_into(node, stack)
                    ast_stack.extend(reversed(inner_ast))

                else:
                    print("Can't step into non function call. Stepping over.")
                    step = "o"

            if step.lower().strip() == "o":
                frame = self._run_executor(executable_str.strip(), stack.pop())

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

    def _step_into(
        self, node: Type[ast.mod], stack: List[Dict]
    ) -> Tuple(Type[ast.AST, Dict]):
        """Step into a new call frame."""
        prev_frame = stack[-1]
        func_name = node.value.func.id + FUNCTION_DEF_KEY_SUFFIX

        cur_frame = defaultdict()
        cur_frame["globals"] = {**prev_frame["locals"], **prev_frame["globals"]}

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
