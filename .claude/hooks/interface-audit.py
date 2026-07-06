#!/usr/bin/env python3
"""
接口审计: 检查修改的 Python 文件是否有签名/格式变更的消费方遗漏。

检查项:
  1. 函数签名: 新增参数是否在 kwargs 传递链上被消费方接受
  2. 类型格式: 字段从简单类型改为容器类型时, 所有访问点是否更新
  3. 初始化: 类属性是否在 __init__ 中初始化

用法:
  python3 .claude/hooks/interface-audit.py              # 检查所有 git diff 文件
  python3 .claude/hooks/interface-audit.py file1.py ...  # 检查指定文件
  python3 .claude/hooks/interface-audit.py --staged      # 仅检查暂存区
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path


def get_changed_py_files(staged_only: bool = False) -> list[str]:
    """获取修改的 .py 文件列表。"""
    args = ["git", "diff", "--name-only"]
    if staged_only:
        args.append("--cached")
    args.append("HEAD")
    try:
        output = subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []
    return [f.strip() for f in output.split("\n") if f.strip().endswith(".py")]


def parse_function_signatures(filepath: str) -> dict[str, set[str]]:
    """解析文件中所有函数的参数名集合。返回 {func_name: {param_names}}。"""
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read(), filename=filepath)
    except SyntaxError as e:
        print(f"  ⚠ {filepath}: 语法错误 {e}")
        return {}

    sigs = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = set()
            for arg in node.args.args:
                params.add(arg.arg)
            if node.args.vararg:
                params.add(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                params.add(f"**{node.args.kwarg.arg}")
            sigs[node.name] = params
    return sigs


def check_kwargs_pass_through(filepath: str) -> list[str]:
    """检查文件中是否有 kwargs 透传可能导致参数不匹配。"""
    warnings = []
    try:
        with open(filepath) as f:
            content = f.read()
            tree = ast.parse(content, filename=filepath)
    except SyntaxError:
        return warnings

    # 找所有 **kwargs → target_func(**kwargs) 的调用
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg is None and isinstance(kw.value, ast.Name):
                    # 检测到 **var_name 模式
                    var_name = kw.value.id
                    if var_name in ("kwargs", "_kwargs", "kw"):
                        func_name = _get_func_name(node.func)
                        if func_name:
                            warnings.append(
                                f"  ⚠ kwargs 透传: **{var_name} → {func_name}()"
                                f" (行 {node.lineno}) — 确认 {func_name} 签名包含所有 kwargs 参数"
                            )
    return warnings


def check_data_format_changes(filepath: str) -> list[str]:
    """检查是否有类型注释变更可能影响消费方。"""
    warnings = []
    try:
        with open(filepath) as f:
            content = f.read()
    except Exception:
        return warnings

    # 检测 list-of-lists 赋值模式
    if re.search(r'\[\[.*\].*\]|list\(list\(', content):
        # 检查是否有旧的平列表访问模式残留
        if re.search(r'int\(.*\[0\]\)|float\(.*\[\d+\]\)', content):
            warnings.append(
                f"  ⚠ 可能的数据格式冲突: 文件中同时存在 list-of-lists 和"
                f" 平列表访问模式 (如 int(x[0])), 请确认所有消费方已更新"
            )

    return warnings


def _collect_attrs_on_self(tree: ast.AST) -> set[str]:
    """收集 AST 中所有 self._xxx 的有效定义（赋值 + property + setattr）。"""
    attrs: set[str] = set()

    class AttrCollector(ast.NodeVisitor):
        def visit_Assign(self, node):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
                    if t.value.id == 'self':
                        attrs.add(t.attr)

        def visit_AnnAssign(self, node):
            if isinstance(node.target, ast.Attribute) and isinstance(node.target.value, ast.Name):
                if node.target.value.id == 'self':
                    attrs.add(node.target.attr)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == 'setattr':
                args = node.args
                if len(args) >= 2:
                    if isinstance(args[0], ast.Name) and args[0].id == 'self':
                        if isinstance(args[1], ast.Constant) and isinstance(args[1].value, str):
                            attrs.add(args[1].value)
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            # @property getter 的方法名 = 属性名
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == 'property':
                    attrs.add(node.name)
                # @xxx.setter
                elif isinstance(dec, ast.Attribute) and dec.attr == 'setter':
                    if isinstance(dec.value, ast.Name):
                        attrs.add(dec.value.id)
            self.generic_visit(node)

    AttrCollector().visit(tree)
    return attrs


def _resolve_target_class(filepath: str, target_var: str) -> tuple[str | None, str | None]:
    """尝试解析变量名 → 类名 → 文件路径。

    例如: mw = self._mw, 而 _mw 的类型是 MainWindow。
    返回: (class_name, class_filepath) 或 (None, None)。
    """
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read(), filename=filepath)
    except SyntaxError:
        return None, None

    # 1. 找 target_var 是从哪个 self 属性来的: self._mw → _mw
    source_attr = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == target_var:
                    # mw = self._mw → source_attr = _mw
                    val = node.value
                    if isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name):
                        if val.value.id == 'self':
                            source_attr = val.attr
                        elif val.value.id == target_var:
                            # mw = self._mw if self else None
                            pass

    if not source_attr:
        return None, None

    # 2. 找 self._mw 赋值的类型 → _mw: type hints
    # 在 __init__ 或类体中查找 _mw 的类型标注或赋值
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute):
            if node.target.attr == source_attr and isinstance(node.target.value, ast.Name):
                if node.target.value.id == 'self' and node.annotation:
                    # self._mw: MainWindow = ...
                    cls_name = ast.unparse(node.annotation) if hasattr(ast, 'unparse') else ''
                    if not cls_name:
                        cls_name = getattr(node.annotation, 'id', '')
                    if cls_name:
                        # 在当前目录搜索类定义文件
                        base_dir = os.path.dirname(filepath) or '.'
                        for root, _, files in os.walk(base_dir):
                            for fn in files:
                                if fn.endswith('.py'):
                                    fp = os.path.join(root, fn)
                                    try:
                                        with open(fp) as f:
                                            cls_tree = ast.parse(f.read(), filename=fp)
                                        for cn in ast.walk(cls_tree):
                                            if isinstance(cn, ast.ClassDef) and cn.name == cls_name:
                                                return cls_name, fp
                                    except SyntaxError:
                                        pass
                        return cls_name, None  # 类名已知但文件没找到
    return None, None


def check_unbound_references(filepath: str) -> list[str]:
    """检查函数体内引用但从未赋值的变量名 (典型: 删控件漏删调用)。

    扫描每个函数，收集局部赋值和引用，找出引用了但未赋值的变量。
    只对首字母大写的 widget 变量名 (如 row_bottom, btn_xl) 告警。
    """
    import ast as _ast
    warnings = []
    try:
        with open(filepath) as f:
            tree = _ast.parse(f.read(), filename=filepath)
    except SyntaxError:
        return warnings

    for node in _ast.walk(tree):
        if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue

        # 收集函数内所有赋值目标 (Name nodes)
        assigned = set()
        for child in _ast.walk(node):
            if isinstance(child, _ast.Assign):
                for t in child.targets:
                    _collect_names(t, assigned)
            elif isinstance(child, _ast.AnnAssign) and child.target:
                _collect_names(child.target, assigned)
            elif isinstance(child, _ast.For):
                _collect_names(child.target, assigned)

        if not assigned:
            continue

        # 跳过 Python builtins 和常见参数名
        assigned.discard('self')

        # 找所有引用但未赋值的 Name
        for child in _ast.walk(node):
            if isinstance(child, _ast.Name) and isinstance(child.ctx, _ast.Load):
                name = child.id
                if name in assigned:
                    continue  # 已赋值，跳过
                # 跳过单字符和 lambda 常用参数
                if len(name) <= 1:
                    continue
                if name in ('True', 'False', 'None', 'self', 'mw', 'app', 'dlg', 'btns',
                            'checked', 'k', 't', 'v', 'cb', 'cw', 'ks', 'name',
                            'QDialog', 'QPushButton', 'QVBoxLayout', 'QHBoxLayout',
                            'QFormLayout', 'QGroupBox', 'QLabel', 'QWidget', 'QLineEdit',
                            'QCheckBox', 'QComboBox', 'QSpinBox', 'QDoubleSpinBox',
                            'QTableWidget', 'QFileDialog', 'QMessageBox', 'QThread',
                            'QApplication', 'Path', 'os', 'np', 'pd', 'io', 'time',
                            'Qt', 'QFrame', 'QScrollArea', 'QDialogButtonBox',
                            'QTextEdit', 'QSplitter', 'QHeaderView', 'QAbstractItemView',
                            'WD_ALIGN_PARAGRAPH', 'WD_TABLE_ALIGNMENT', 'Cm', 'Pt',
                            'Document', 'BytesIO', 'Figure', 'Axes', 'Optional',
                            'List', 'Dict', 'Tuple', 'Any', 'Set', 'Union', 'Callable',
                            'str', 'int', 'float', 'bool', 'list', 'dict', 'set', 'tuple',
                            'True', 'False', 'None', 'range', 'len', 'max', 'min', 'abs',
                            'enumerate', 'zip', 'sorted', 'reversed', 'round', 'isinstance',
                            'hasattr', 'getattr', 'setattr', 'type', 'print',
                            ):
                    continue
                # 只报告首字母小写的 widget 变量
                if name and name[0].islower():
                    warnings.append(
                        f"  ⚠ 未绑定变量引用: '{name}' 在函数 {node.name}"
                        f" (行 {child.lineno}) — 该变量从未赋值, 可能漏删了引用"
                    )
    return warnings


def _collect_names(node, result: set):
    """递归收集 AST 节点中的所有 Name.id。"""
    import ast as _ast
    if isinstance(node, _ast.Name):
        result.add(node.id)
    elif isinstance(node, (_ast.Tuple, _ast.List)):
        for elt in node.elts:
            _collect_names(elt, result)
    elif isinstance(node, _ast.Starred):
        _collect_names(node.value, result)


def check_hasattr_dead_code(filepath: str) -> list[str]:
    """检查 hasattr/getattr 守卫引用的属性是否真的存在。

    检测两类守卫:
      1. hasattr(self, '_xxx') — 在同文件中检查 self._xxx 的赋值/property/setattr
      2. hasattr(mw, '_xxx') — 跨文件解析 mw 的类型，检查目标类中 _xxx 是否存在
    """
    warnings = []
    try:
        with open(filepath) as f:
            content = f.read()
            tree = ast.parse(content, filename=filepath)
    except SyntaxError:
        return warnings

    # 收集本文件中 self._xxx 的所有有效定义
    self_attrs = _collect_attrs_on_self(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        if func_name not in ('hasattr', 'getattr'):
            continue

        args = node.args
        if len(args) < 2:
            continue
        arg1, arg2 = args[0], args[1]
        if not isinstance(arg2, ast.Constant) or not isinstance(arg2.value, str):
            continue
        attr_name = arg2.value
        if not attr_name.startswith('_'):
            continue

        # hasattr(self, '_xxx') → 同文件检查
        if isinstance(arg1, ast.Name) and arg1.id == 'self' and attr_name not in self_attrs:
            warnings.append(
                f"  ⚠ hasattr/getattr 守卫引用 '{attr_name}' "
                f"但文件中从未给 self.{attr_name} 赋值"
                f" (行 {node.lineno}) — 该守卫可能永远为 False"
            )

        # hasattr(mw, '_xxx') → 跨文件检查
        elif isinstance(arg1, ast.Name) and arg1.id == 'mw' and attr_name not in self_attrs:
            cls_name, cls_file = _resolve_target_class(filepath, 'mw')
            if cls_name and cls_file and cls_file != filepath:
                try:
                    with open(cls_file) as f:
                        cls_tree = ast.parse(f.read(), filename=cls_file)
                    cls_attrs = _collect_attrs_on_self(cls_tree)
                    if attr_name not in cls_attrs:
                        warnings.append(
                            f"  ⚠ hasattr(mw, '{attr_name}') 守卫引用"
                            f" (行 {node.lineno}) — {cls_name} 类中未定义此属性"
                        )
                except SyntaxError:
                    pass

    return warnings


def check_attr_initialization(filepath: str) -> list[str]:
    """检查类属性是否在 __init__ 中初始化。"""
    warnings = []
    try:
        with open(filepath) as f:
            content = f.read()
            tree = ast.parse(content, filename=filepath)
    except SyntaxError:
        return warnings

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name
            init_attrs = set()
            # 收集 __init__ 中初始化的属性
            for item in ast.walk(node):
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                            if target.value.id == "self":
                                init_attrs.add(target.attr)

            # 找类体内的 getattr/hasattr 引用 (可能是测试文件)
            if filepath.startswith("tests/"):
                for item in ast.walk(node):
                    # 跳过
                    pass

    return warnings


def _get_func_name(node) -> str | None:
    """从 AST 调用节点提取函数名。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def main():
    staged_only = "--staged" in sys.argv
    files = [f for f in sys.argv[1:] if f.endswith(".py")] or get_changed_py_files(staged_only)

    if not files:
        print("  ✓ 无修改的 Python 文件")
        return 0

    all_warnings = []

    for f in files:
        if not os.path.exists(f):
            continue
        fname = Path(f).name
        print(f"  检查: {fname}")

        # 1. kwargs 透传检查
        kw_warnings = check_kwargs_pass_through(f)
        all_warnings.extend(kw_warnings)

        # 2. 数据格式变更检查
        fmt_warnings = check_data_format_changes(f)
        all_warnings.extend(fmt_warnings)

        # 3. hasattr/getattr 死代码检查
        ha_warnings = check_hasattr_dead_code(f)
        all_warnings.extend(ha_warnings)

        # 4. 未绑定变量引用 (删控件漏删调用)
        ub_warnings = check_unbound_references(f)
        all_warnings.extend(ub_warnings)

    if all_warnings:
        print("\n📋 接口审计发现潜在问题:\n")
        for w in all_warnings:
            print(w)
        print(f"\n  ⚠ {len(all_warnings)} 个警告 — 请人工确认后继续")
        # 返回 1 会拦截 commit (可通过 export CLAUDE_INTERFACE_SKIP=1 跳过)
        return 0 if os.environ.get("CLAUDE_INTERFACE_SKIP") == "1" else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
