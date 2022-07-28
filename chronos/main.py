import ast
import copy
import inspect
import logging
import typing
from collections import defaultdict

import click

FUNCTION_DEF_KEY_SUFFIX = "FUNC_DEF"


class debugger:
    def run(self, path):
        stack = [defaultdict()]

        try:
            with open(path, "r") as f:
                current_code = f.read()
        except IOError:
            raise SystemError(f"Cannot read path {path}")

        self._run(current_code, stack)

    def _run(self, current_code, stack):
        try:
            syntax_tree = ast.parse(current_code)
        except ValueError as e:
            raise SystemError(f"Cannot parse into abstract syntax tree, {e}")

        code_lines = current_code.splitlines()
        done = False
        cur = 0

        while not done and syntax_tree.body:
            node = syntax_tree.body[cur]

            cur += 1
            if cur == len(syntax_tree.body):
                done = True

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

            # wrong, check for function another way
            if hasattr(node, "value") and node.value.__class__ is ast.Call:
                if not stack[-1].get("locals"):
                    stack[-1]["locals"] = defaultdict()

                stack[-1]["locals"][
                    node.value.func.id + FUNCTION_DEF_KEY_SUFFIX
                ] = executable_str

            if step.lower().strip() == "i":

                if node.value.__class__ is ast.Call:

                    self._step_into(node, stack)
                    continue

            if step.lower().strip() == "o":
                frame = self._run_executor(executable_str.strip(), stack.pop())

                if frame:
                    stack.append(frame)

    def _run_executor(self, executable_str, frame):

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

    def _step_into(self, node, stack):
        # Create a new frame and _run it
        prev_frame = stack[-1]
        func_name = node.value.func.id + FUNCTION_DEF_KEY_SUFFIX

        cur_frame = defaultdict()
        cur_frame["globals"] = {**prev_frame["locals"], **prev_frame["globals"]}

        try:
            executable_str = self._resolve(prev_frame, func_name)
        except KeyError:
            raise SystemError(f"{func_name} not defined in calling frame")

        self._run(executable_str, stack + [cur_frame])
        # recursive might not work for if we want to step backwards.
        # bc frame will be lost once we are done with it

    def _resolve(self, frame, name):

        if "locals" in frame:
            if name in frame["locals"]:
                return frame["locals"][name]

        if "globals" in frame:
            if name in frame["globals"]:
                return frame["globals"][name]

        raise SystemError(f"Unable to resolve {name} in frame {frame}")

    def print_code(self, code):
        print("\n\n")
        print(code)
        print("\n\n")
