
# ═══════════════════════════════════════════════════════════════
# Docx 模板 SDT 工具箱
# ═══════════════════════════════════════════════════════════════

class DocxTemplateToolbox(QDialog):
    """.docx 模板分析 + SDT tag 推荐 + 插入。"""

    def __init__(self, parent=None, docx_path=""):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Docx 模板 SDT 工具箱"))
        self.resize(1000, 700)
        self.setMinimumSize(800, 550)
        self._docx_path = docx_path
        self._positions = []
        self._setup_ui()
        if docx_path and Path(docx_path).exists():
            self._edit_path.setText(docx_path)
            self._scan()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        grp = QGroupBox(self.tr("Word 模板"))
        gr = QHBoxLayout(grp)
        self._edit_path = QLineEdit()
        self._edit_path.setPlaceholderText(self.tr("选择 .docx 模板文件..."))
        gr.addWidget(self._edit_path, 1)
        btn_browse = QPushButton(self.tr("浏览..."))
        btn_browse.clicked.connect(self._browse)
        gr.addWidget(btn_browse)
        btn_scan = QPushButton(self.tr("扫描"))
        btn_scan.clicked.connect(self._scan)
        gr.addWidget(btn_scan)
        layout.addWidget(grp)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            self.tr("#"), self.tr("位置"), self.tr("类型"), self.tr("示例文本"),
            self.tr("推荐 Tag"), self.tr("确认 Tag"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 40)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.setColumnWidth(1, 150)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._table.setColumnWidth(2, 70)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self._table.setColumnWidth(4, 160)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self._table.setColumnWidth(5, 160)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        self._lbl_summary = QLabel("")
        layout.addWidget(self._lbl_summary)

        btn_row = QHBoxLayout()
        btn_rule = QPushButton(self.tr("规则自动匹配"))
        btn_rule.clicked.connect(self._rule_match)
        btn_row.addWidget(btn_rule)
        btn_llm = QPushButton(self.tr("LLM 智能推荐"))
        btn_llm.clicked.connect(self._llm_suggest)
        btn_row.addWidget(btn_llm)
        btn_row.addStretch()
        btn_insert = QPushButton(self.tr("插入 SDT 并保存"))
        btn_insert.setStyleSheet("font-weight:bold;")
        btn_insert.clicked.connect(self._insert_and_save)
        btn_row.addWidget(btn_insert)
        btn_close = QPushButton(self.tr("关闭"))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择 Word 模板"), "",
            self.tr("Word 文档 (*.docx)"))
        if path:
            if path.lower().endswith('.doc') and not path.lower().endswith('.docx'):
                QMessageBox.warning(self, self.tr("格式不支持"),
                    self.tr("不支持 .doc 格式。请用 Word 另存为 .docx 后再使用。"))
                return
            self._edit_path.setText(path)
            self._docx_path = path
            self._scan()

    def _scan(self):
        path = self._edit_path.text().strip()
        if not path or not Path(path).exists():
            return
        try:
            from src.docx_sdt_inserter import scan_docx
            self._positions = scan_docx(path)
        except Exception as e:
            QMessageBox.warning(self, self.tr("扫描失败"), str(e))
            return
        self._populate_table()
        tables = sum(1 for p in self._positions if "table" in p.pos_type)
        images = sum(1 for p in self._positions if p.pos_type == "image")
        self._lbl_summary.setText(
            self.tr("共 {} 个表格, {} 张图片").format(tables, images))

    def _populate_table(self):
        self._table.setRowCount(len(self._positions))
        for i, p in enumerate(self._positions):
            self._table.setItem(i, 0, QTableWidgetItem(str(p.index + 1)))
            self._table.setItem(i, 1, QTableWidgetItem(p.location))
            self._table.setItem(i, 2, QTableWidgetItem(p.pos_type))
            self._table.setItem(i, 3, QTableWidgetItem(p.sample_text[:80]))
            self._table.setItem(i, 4, QTableWidgetItem(p.suggested_tag))
            self._table.setItem(i, 5, QTableWidgetItem(p.confirmed_tag))

    def _rule_match(self):
        try:
            from src.llm_tagger import rule_based_suggest
            n = rule_based_suggest(self._positions)
        except Exception as e:
            QMessageBox.warning(self, self.tr("匹配失败"), str(e))
            return
        self._populate_table()
        self._lbl_summary.setText(
            self.tr("规则匹配: {}/{} 个已推荐").format(n, len(self._positions)))

    def _llm_suggest(self):
        from src.config_manager import get_config_manager
        cfg = get_config_manager()
        llm = getattr(cfg.config, 'llm', None)
        if not llm or not llm.enabled:
            reply = QMessageBox.question(self, self.tr("LLM 未配置"),
                self.tr("尚未配置 AI API。是否打开系统设置？"),
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                p = self.parent()
                while p and not hasattr(p, '_data_file_paths'):
                    p = p.parent()
                from ui.dialogs import SystemSettingsDialog
                SystemSettingsDialog(p).exec()
            return
        try:
            from src.llm_tagger import suggest_tags_with_llm
            n = suggest_tags_with_llm(
                self._positions, llm.api_base,
                getattr(llm, '_api_key', ''), llm.model)
        except Exception as e:
            QMessageBox.warning(self, self.tr("LLM 失败"), str(e))
            return
        self._populate_table()
        self._lbl_summary.setText(self.tr("LLM: {} 个新推荐").format(n))

    def _insert_and_save(self):
        for i in range(self._table.rowCount()):
            item5 = self._table.item(i, 5)
            if item5 and item5.text().strip():
                self._positions[i].confirmed_tag = item5.text().strip()
            else:
                item4 = self._table.item(i, 4)
                if item4 and item4.text().strip():
                    self._positions[i].confirmed_tag = item4.text().strip()
        confirmed = [p for p in self._positions if p.confirmed_tag.strip()]
        if not confirmed:
            QMessageBox.information(self, self.tr("提示"),
                self.tr("请先确认至少一个 SDT tag。"))
            return
        out_path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存带 SDT 的模板"),
            str(Path(self._docx_path).parent /
                (Path(self._docx_path).stem + "_SDT.docx")),
            self.tr("Word 文档 (*.docx)"))
        if not out_path:
            return
        try:
            from src.docx_sdt_inserter import insert_sdt_tags
            insert_sdt_tags(self._docx_path, self._positions, out_path)
        except Exception as e:
            QMessageBox.warning(self, self.tr("插入失败"), str(e))
            return
        msg = self.tr("已插入 {} 个 SDT tag 到:").format(len(confirmed))
        QMessageBox.information(self, self.tr("完成"), msg + "\n" + out_path)
