"""
项目管理 GUI
=============
三个对话框: ProjectManagerDialog, ProjectEditDialog, ImportFromJSONDialog
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

CATEGORIES = [
    ("antenna", "天线测试"),
    ("emc", "EMC 测试"),
    ("sar", "SAR 测试"),
    ("safety", "安规测试"),
]

SORTED_CATEGORIES = sorted(CATEGORIES, key=lambda x: x[1])


# ═══════════════════════════════════════════════════════════════
# ProjectManagerDialog
# ═══════════════════════════════════════════════════════════════

class ProjectManagerDialog(QDialog):
    """项目管理主窗口 — 搜索/浏览/打开/删除。"""

    open_project = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("项目管理"))
        self.resize(960, 680)
        self.setMinimumSize(700, 500)
        self._mw = parent
        self._db = None
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── 搜索栏 ──
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(self.tr("🔍 搜索:")))
        self._edit_search = QLineEdit()
        self._edit_search.setPlaceholderText(self.tr("客户/型号/操作员/日期..."))
        self._edit_search.returnPressed.connect(self._refresh)
        search_row.addWidget(self._edit_search, 1)

        search_row.addWidget(QLabel(self.tr(" 类别:")))
        self._cmb_cat = QComboBox()
        self._cmb_cat.addItem(self.tr("全部"), "")
        for cat, label in SORTED_CATEGORIES:
            self._cmb_cat.addItem(label, cat)
        self._cmb_cat.currentIndexChanged.connect(self._refresh)
        search_row.addWidget(self._cmb_cat)

        btn_search = QPushButton(self.tr("搜索"))
        btn_search.clicked.connect(self._refresh)
        search_row.addWidget(btn_search)
        layout.addLayout(search_row)

        # ── 表格 ──
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            self.tr("客户"), self.tr("型号"), self.tr("类别"), self.tr("测试日期"),
            self.tr("操作员"), self.tr("频段/文件名"), self.tr("ID"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.setColumnHidden(6, True)  # 隐藏 ID 列
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._on_open)
        layout.addWidget(self._table, 1)

        # ── 详情 ──
        self._lbl_detail = QLabel(self.tr("选择一条记录查看详情"))
        self._lbl_detail.setWordWrap(True)
        self._lbl_detail.setStyleSheet("color: #666; padding: 4px;")
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._lbl_detail)

        # ── 按钮栏 ──
        btn_row = QHBoxLayout()
        btn_new = QPushButton(self.tr("📂 新建"))
        btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(btn_new)

        btn_import = QPushButton(self.tr("📋 从 JSON 导入"))
        btn_import.clicked.connect(self._on_import_json)
        btn_row.addWidget(btn_import)

        btn_edit = QPushButton(self.tr("✏️ 编辑"))
        btn_edit.clicked.connect(self._on_edit)
        btn_row.addWidget(btn_edit)

        btn_del = QPushButton(self.tr("🗑 删除"))
        btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(btn_del)

        btn_row.addStretch()

        btn_open = QPushButton(self.tr("📄 打开项目出报告"))
        btn_open.setStyleSheet("font-weight:bold;")
        btn_open.clicked.connect(self._on_open)
        btn_row.addWidget(btn_open)

        btn_close = QPushButton(self.tr("关闭"))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    @property
    def db(self):
        if self._db is None:
            from src.project_db import get_db
            self._db = get_db()
        return self._db

    def _refresh(self):
        search = self._edit_search.text().strip()
        cat = self._cmb_cat.currentData() or ""
        tests = self.db.get_tests(search=search, category=cat)

        self._table.setRowCount(len(tests))
        for i, t in enumerate(tests):
            self._table.setItem(i, 0, QTableWidgetItem(t.get('customer_name', '')))
            self._table.setItem(i, 1, QTableWidgetItem(t.get('model', '')))
            cat_label = dict(CATEGORIES).get(t.get('category', ''), t.get('category', ''))
            self._table.setItem(i, 2, QTableWidgetItem(cat_label))
            self._table.setItem(i, 3, QTableWidgetItem(t.get('test_date', '')[:16]))
            self._table.setItem(i, 4, QTableWidgetItem(t.get('operator', '')))
            # 频段/文件名
            freq = t.get('metadata', {}).get('freq_range', '')
            files = t.get('data_files', [])
            fname = Path(files[0]).name if files else ''
            info = freq or fname or ''
            self._table.setItem(i, 5, QTableWidgetItem(info[:40]))
            self._table.setItem(i, 6, QTableWidgetItem(str(t.get('id', ''))))

        self._table.resizeRowsToContents()
        self._lbl_detail.setText(self.tr("共 {} 条记录").format(len(tests)))

    def _selected_id(self) -> int | None:
        rows = set(i.row() for i in self._table.selectedItems())
        if not rows:
            return None
        r = list(rows)[0]
        item = self._table.item(r, 6)
        return int(item.text()) if item else None

    def _selected_data(self) -> dict | None:
        tid = self._selected_id()
        return self.db.get_test_by_id(tid) if tid else None

    def _on_selection_changed(self):
        t = self._selected_data()
        if t:
            freq = t.get('metadata', {}).get('freq_range', '—')
            files = t.get('data_files', [])
            lines = [
                f"客户: {t.get('customer_name', '')}    天线: {t.get('model', '')}",
                f"频段: {freq}    测试日期: {t.get('test_date', '')[:16]}",
                f"数据文件: {', '.join(Path(f).name for f in files) if files else '(无)'}",
                f"模板: {Path(t.get('template_path', '')).name or '(无)'}",
                f"上次报告: {Path(t.get('report_path', '')).name or '(无)'}",
            ]
            self._lbl_detail.setText('\n'.join(lines))

    def _on_open(self):
        t = self._selected_data()
        if not t:
            QMessageBox.information(self, self.tr("提示"), self.tr("请先选择一条项目记录。"))
            return
        if self._mw:
            self._restore_to_main(t)
            self.accept()

    def _restore_to_main(self, t: dict):
        """回填项目数据到主窗口。"""
        mw = self._mw
        if not mw:
            return

        # 元数据
        from src.config_manager import get_config_manager
        cfg = get_config_manager()
        cfg.config.metadata = t.get('metadata', {})
        cfg._dirty = True
        cfg._save()

        # 数据文件
        files = t.get('data_files', [])
        if files and hasattr(mw, '_data_file_paths'):
            mw._data_file_paths = [f for f in files if Path(f).exists()]

        # 模板
        tpl = t.get('template_path', '')
        if tpl and Path(tpl).exists() and hasattr(mw, 'ui'):
            mw.ui.editTemplatePath.setText(tpl)

        # 输出目录
        out = t.get('output_dir', '')
        if out and Path(out).exists():
            mw.ui.editOutputDir.setText(out)

        mw._log(f"✓ 已加载项目: {t.get('customer_name')} — {t.get('model')}")

    def _on_new(self):
        dlg = ProjectEditDialog(self)
        if dlg.exec():
            self._refresh()

    def _on_import_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择 EMQuest JSON 文件"), "",
            self.tr("JSON 文件 (*.json)"))
        if not path:
            return
        tid = self.db.import_from_json(path)
        if tid:
            QMessageBox.information(self, self.tr("导入成功"),
                                    self.tr("已从 JSON 创建项目记录。"))
            self._refresh()
        else:
            QMessageBox.warning(self, self.tr("导入失败"),
                                self.tr("无法解析 JSON 文件，请确认是有效的 EMQuest 数据文件。"))

    def _on_edit(self):
        t = self._selected_data()
        if not t:
            QMessageBox.information(self, self.tr("提示"), self.tr("请先选择一条项目记录。"))
            return
        dlg = ProjectEditDialog(self, test=t)
        if dlg.exec():
            self._refresh()

    def _on_delete(self):
        tid = self._selected_id()
        if not tid:
            return
        t = self.db.get_test_by_id(tid)
        name = f"{t.get('customer_name', '')} — {t.get('model', '')}" if t else f"ID={tid}"
        r = QMessageBox.question(self, self.tr("确认删除"),
                                  self.tr("确定要删除项目:\n{}?").format(name),
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            self.db.delete_test(tid)
            self._refresh()


# ═══════════════════════════════════════════════════════════════
# ProjectEditDialog
# ═══════════════════════════════════════════════════════════════

class ProjectEditDialog(QDialog):
    """新建/编辑项目对话框。"""

    def __init__(self, parent=None, test: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("新建项目") if test is None else self.tr("编辑项目"))
        self.setMinimumSize(550, 520)
        self._test = test
        self._is_new = test is None
        self._db = None
        self._build_ui()
        if test:
            self._load(test)

    @property
    def db(self):
        if self._db is None:
            from src.project_db import get_db
            self._db = get_db()
        return self._db

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 1: 客户 + 被测物
        tab1 = QWidget()
        f1 = QFormLayout(tab1)
        f1.setSpacing(6)
        self._edit_customer = QLineEdit()
        self._edit_customer.setPlaceholderText(self.tr("如: 安费诺"))
        f1.addRow(self.tr("客户名称*:"), self._edit_customer)
        self._edit_contact = QLineEdit()
        self._edit_contact.setPlaceholderText(self.tr("联系人"))
        f1.addRow(self.tr("联系人:"), self._edit_contact)
        self._edit_model = QLineEdit()
        self._edit_model.setPlaceholderText(self.tr("如: GNSS L1/L5"))
        f1.addRow(self.tr("天线型号*:"), self._edit_model)
        self._edit_serial = QLineEdit()
        self._edit_serial.setPlaceholderText(self.tr("序列号 (可选)"))
        f1.addRow(self.tr("序列号:"), self._edit_serial)
        self._edit_dut_type = QComboBox()
        self._edit_dut_type.setEditable(True)
        self._edit_dut_type.addItems([self.tr("线极化"), self.tr("圆极化"), self.tr("有源"), ""])
        f1.addRow(self.tr("天线类型:"), self._edit_dut_type)
        tabs.addTab(tab1, self.tr("客户 & 被测物"))

        # Tab 2: 测试配置
        tab2 = QWidget()
        f2 = QFormLayout(tab2)
        f2.setSpacing(6)
        self._edit_category = QComboBox()
        for cat, label in CATEGORIES:
            self._edit_category.addItem(label, cat)
        f2.addRow(self.tr("测试类别:"), self._edit_category)
        self._edit_date = QLineEdit()
        self._edit_date.setPlaceholderText(self.tr("如: 2026-06-02"))
        f2.addRow(self.tr("测试日期:"), self._edit_date)
        self._edit_operator = QLineEdit()
        self._edit_operator.setPlaceholderText("HL")
        f2.addRow(self.tr("操作员:"), self._edit_operator)
        self._edit_freq = QLineEdit()
        self._edit_freq.setPlaceholderText(self.tr("如: 1549-1616 MHz"))
        f2.addRow(self.tr("频段:"), self._edit_freq)
        # 数据文件
        files_row = QHBoxLayout()
        self._edit_files = QLineEdit()
        self._edit_files.setPlaceholderText(self.tr("多个文件用分号 ; 分隔"))
        files_row.addWidget(self._edit_files, 1)
        btn_files = QPushButton(self.tr("浏览..."))
        btn_files.clicked.connect(self._browse_files)
        files_row.addWidget(btn_files)
        f2.addRow(self.tr("数据文件:"), files_row)
        # 模板
        tpl_row = QHBoxLayout()
        self._edit_tpl = QLineEdit()
        tpl_row.addWidget(self._edit_tpl, 1)
        btn_tpl = QPushButton(self.tr("浏览..."))
        btn_tpl.clicked.connect(self._browse_tpl)
        tpl_row.addWidget(btn_tpl)
        f2.addRow(self.tr("Word 模板:"), tpl_row)
        # 输出目录
        out_row = QHBoxLayout()
        self._edit_out = QLineEdit()
        out_row.addWidget(self._edit_out, 1)
        btn_out = QPushButton(self.tr("浏览..."))
        btn_out.clicked.connect(self._browse_out)
        out_row.addWidget(btn_out)
        f2.addRow(self.tr("输出目录:"), out_row)
        tabs.addTab(tab2, self.tr("测试配置"))

        # Tab 3: 备注
        tab3 = QWidget()
        f3 = QVBoxLayout(tab3)
        self._edit_notes = QPlainTextEdit()
        self._edit_notes.setPlaceholderText(self.tr("备注信息..."))
        f3.addWidget(self._edit_notes)
        tabs.addTab(tab3, self.tr("备注"))

        layout.addWidget(tabs)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load(self, t: dict):
        self._edit_customer.setText(t.get('customer_name', ''))
        self._edit_model.setText(t.get('model', ''))
        self._edit_serial.setText(t.get('serial_no', ''))
        self._edit_dut_type.setCurrentText(t.get('dut_type', ''))
        idx = self._edit_category.findData(t.get('category', 'antenna'))
        if idx >= 0:
            self._edit_category.setCurrentIndex(idx)
        self._edit_date.setText(t.get('test_date', '')[:10])
        self._edit_operator.setText(t.get('operator', ''))
        self._edit_freq.setText(t.get('metadata', {}).get('freq_range', ''))
        files = t.get('data_files', [])
        self._edit_files.setText('; '.join(files))
        self._edit_tpl.setText(t.get('template_path', ''))
        self._edit_out.setText(t.get('output_dir', ''))
        self._edit_notes.setPlainText(t.get('notes', ''))

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.tr("选择数据文件"), "",
            self.tr("所有支持格式 (*.json *.csv *.xlsx);;JSON (*.json)"))
        if paths:
            self._edit_files.setText('; '.join(paths))

    def _browse_tpl(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择 Word 模板"), "",
            self.tr("Word 文档 (*.docx)"))
        if path:
            self._edit_tpl.setText(path)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("选择输出目录"))
        if d:
            self._edit_out.setText(d)

    def _on_save(self):
        customer = self._edit_customer.text().strip()
        model = self._edit_model.text().strip()
        if not customer or not model:
            QMessageBox.warning(self, self.tr("必填"), self.tr("客户名称和天线型号为必填项。"))
            return

        # 客户
        if self._test:
            cid = self._test.get('dut_id')  # 关联现有客户
            existing_customers = self.db.get_customers(search=customer)
            cid_real = existing_customers[0]['id'] if existing_customers and existing_customers[0]['name'] == customer else self.db.add_customer(customer)
        else:
            cid = self.db.add_customer(customer, self._edit_contact.text().strip())

        # 被测物
        serial = self._edit_serial.text().strip()
        dut_type = self._edit_dut_type.currentText().strip()
        if self._test:
            did = self._test.get('dut_id', 0)
            self.db.update_dut(did, model=model, dut_type=dut_type, serial_no=serial)
        else:
            did = self.db.add_dut(cid, model, dut_type, serial)

        # 测试
        files = [f.strip() for f in self._edit_files.text().split(';') if f.strip()]
        metadata = {'freq_range': self._edit_freq.text().strip()}
        kwargs = dict(
            dut_id=did, category=self._edit_category.currentData() or 'antenna',
            test_date=self._edit_date.text().strip(),
            operator=self._edit_operator.text().strip(),
            metadata=metadata, data_files=files,
            template_path=self._edit_tpl.text().strip(),
            output_dir=self._edit_out.text().strip(),
            notes=self._edit_notes.toPlainText().strip(),
        )
        if self._test:
            self.db.update_test(self._test['id'], **kwargs)
        else:
            self.db.add_test(**kwargs)
        self.accept()


# ═══════════════════════════════════════════════════════════════
# ImportFromJSONDialog
# ═══════════════════════════════════════════════════════════════

class ImportFromJSONDialog(QDialog):
    """从 JSON 自动提取并导入项目。"""

    def __init__(self, parent=None, json_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle(self.tr("从 JSON 导入"))
        self.setMinimumSize(600, 480)
        self._db = None
        self._extracted: dict = {}
        self._build_ui()
        if json_path:
            self._edit_path.setText(json_path)
            self._extract()

    @property
    def db(self):
        if self._db is None:
            from src.project_db import get_db
            self._db = get_db()
        return self._db

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # JSON 文件
        grp = QGroupBox(self.tr("JSON 文件"))
        gr = QHBoxLayout(grp)
        self._edit_path = QLineEdit()
        self._edit_path.setPlaceholderText(self.tr("选择 EMQuest JSON 文件..."))
        gr.addWidget(self._edit_path, 1)
        btn_browse = QPushButton(self.tr("浏览..."))
        btn_browse.clicked.connect(self._browse)
        gr.addWidget(btn_browse)
        btn_extract = QPushButton(self.tr("提取"))
        btn_extract.clicked.connect(self._extract)
        gr.addWidget(btn_extract)
        layout.addWidget(grp)

        # 提取结果
        info = QLabel(self.tr("提取的元数据（可修改后保存）："))
        layout.addWidget(info)

        self._form = QFormLayout()
        self._form.setSpacing(6)
        fields = [
            ('customer', '客户名称'), ('model', '天线型号'),
            ('operator', '操作员'), ('freq_range', '频率范围'),
            ('test_method', '测试方法'), ('test_date', '测试日期'),
            ('serial', '序列号'),
        ]
        self._edits = {}
        for key, label in fields:
            edit = QLineEdit()
            self._form.addRow(label + ':', edit)
            self._edits[key] = edit
        layout.addLayout(self._form)

        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择 JSON 文件"), "",
            self.tr("JSON 文件 (*.json)"))
        if path:
            self._edit_path.setText(path)
            self._extract()

    def _extract(self):
        path = self._edit_path.text().strip()
        if not path or not Path(path).exists():
            return
        try:
            from src.json_reader import JsonDataSource
            ds = JsonDataSource(path)
            self._extracted = ds.get_metadata()
        except Exception as e:
            QMessageBox.warning(self, self.tr("提取失败"), str(e))
            return

        # 映射到表单
        mapping = {
            'customer': ('operator', self._extracted.get('operator', '')),
            'model': ('model', self._extracted.get('model', '') or Path(path).stem),
            'operator': ('operator', self._extracted.get('operator', '')),
            'freq_range': ('freq_range', self._extracted.get('freq_range', '')),
            'test_method': ('test_method', self._extracted.get('test_method', '')),
            'test_date': ('test_time', self._extracted.get('testtime', '') or self._extracted.get('test_time', '')),
            'serial': ('serial', self._extracted.get('serialno', '')),
        }
        for key, (src, val) in mapping.items():
            if key in self._edits and val:
                self._edits[key].setText(str(val))

    def _on_save(self):
        path = self._edit_path.text().strip()
        if not path:
            return
        tid = self.db.import_from_json(path)
        if tid:
            # 更新用户修改的字段
            updates = {}
            cust = self._edits['customer'].text().strip()
            model = self._edits['model'].text().strip()
            if cust or model:
                m = self._extracted.copy()
                m['operator'] = cust
                m['model'] = model
                m['freq_range'] = self._edits['freq_range'].text().strip()
                updates['metadata'] = m
            if updates:
                self.db.update_test(tid, **updates)
            QMessageBox.information(self, self.tr("导入成功"), self.tr("项目已保存。"))
            self.accept()
        else:
            QMessageBox.warning(self, self.tr("导入失败"), self.tr("无法解析 JSON 文件。"))
