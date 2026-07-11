"""
反馈对话框 (UI)
===============
用户提交使用反馈 / bug。收集类型 + 正文 + 可选附带(日志/配置/截图),
自动附 app 版本 + machine_id, 经 feedback_client 提交 (后台线程, 不卡界面)。

隐私: 日志/配置/截图默认不勾, 明示后由用户自愿勾选附带。
逻辑/界面分离: 提交逻辑在 src/feedback_client.py, 本模块只负责 UI + 收集。
"""

from __future__ import annotations

import base64

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from src import __version__ as _APP_VERSION
from src import feedback_client


class _SubmitThread(QThread):
    """后台提交反馈, 避免网络等待卡住界面。"""
    done = Signal(bool, str)

    def __init__(self, payload: dict, parent=None):
        super().__init__(parent)
        self._payload = payload

    def run(self):
        ok, msg = feedback_client.submit_or_queue(self._payload)
        self.done.emit(ok, msg)


class FeedbackDialog(QDialog):
    """发送反馈对话框。

    Args:
        parent: 父窗口 (必须传, 避免成为独立顶层窗口)。
        log_text: 主窗口日志文本 (用户勾选「附带日志」时取尾部)。
        config_dict: 配置快照 (用户勾选「附带配置」时附带)。
    """

    def __init__(self, parent=None, log_text: str = "", config_dict: dict | None = None):
        super().__init__(parent)
        self._log_text = log_text or ""
        self._config_dict = config_dict or {}
        self._screenshot_path: str = ""
        self._thread: _SubmitThread | None = None

        self.setWindowTitle(self.tr("发送反馈"))
        self.setMinimumWidth(460)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._cmb_type = QComboBox()
        self._cmb_type.addItem(self.tr("Bug / 问题"), "bug")
        self._cmb_type.addItem(self.tr("功能建议"), "feature")
        self._cmb_type.addItem(self.tr("其他"), "other")
        form.addRow(self.tr("类型:"), self._cmb_type)
        layout.addLayout(form)

        layout.addWidget(QLabel(self.tr("描述 (请尽量写清操作步骤 / 期望结果):")))
        self._edit_text = QPlainTextEdit()
        self._edit_text.setPlaceholderText(
            self.tr("例: 出报告时底部状态栏多出一行冗余信息..."))
        self._edit_text.setMinimumHeight(140)
        layout.addWidget(self._edit_text)

        # ── 可选附带 (隐私: 默认不勾, 明示) ──
        self._chk_log = QCheckBox(self.tr("附带最近运行日志 (便于定位问题)"))
        self._chk_config = QCheckBox(self.tr("附带配置快照 (角度/输出设置等, 不含许可)"))
        self._chk_log.setChecked(False)
        self._chk_config.setChecked(False)
        if not self._log_text:
            self._chk_log.setEnabled(False)
        if not self._config_dict:
            self._chk_config.setEnabled(False)
        layout.addWidget(self._chk_log)
        layout.addWidget(self._chk_config)

        shot_row = QHBoxLayout()
        self._btn_shot = QPushButton(self.tr("附截图..."))
        self._btn_shot.clicked.connect(self._on_pick_screenshot)
        self._lbl_shot = QLabel(self.tr("(未选择)"))
        self._lbl_shot.setStyleSheet("color: gray;")
        shot_row.addWidget(self._btn_shot)
        shot_row.addWidget(self._lbl_shot, 1)
        layout.addLayout(shot_row)

        note = QLabel(self.tr(
            "提交将附带 app 版本与匿名机器码 (仅用于去重, 不含个人信息)。"))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(note)

        self._btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._btns.button(QDialogButtonBox.Ok).setText(self.tr("提交"))
        self._btns.button(QDialogButtonBox.Cancel).setText(self.tr("取消"))
        self._btns.accepted.connect(self._on_submit)
        self._btns.rejected.connect(self.reject)
        layout.addWidget(self._btns)

    def _on_pick_screenshot(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择截图"), "",
            self.tr("图片 (*.png *.jpg *.jpeg)"))
        if path:
            self._screenshot_path = path
            self._lbl_shot.setText(path.rsplit("/", 1)[-1])

    def _collect_attachments(self) -> dict:
        att: dict = {}
        if self._chk_log.isChecked() and self._log_text:
            att["log_tail"] = "\n".join(self._log_text.splitlines()[-200:])
        if self._chk_config.isChecked() and self._config_dict:
            # 剔除许可/敏感字段
            cfg = {k: v for k, v in self._config_dict.items()
                   if k not in ("license", "llm", "ai")}
            att["config"] = cfg
        if self._screenshot_path:
            try:
                with open(self._screenshot_path, "rb") as f:
                    raw = f.read()
                if len(raw) <= 2_000_000:  # ≤2MB
                    att["screenshot"] = base64.b64encode(raw).decode("ascii")
            except Exception:
                pass
        return att

    def _on_submit(self):
        text = self._edit_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, self.tr("提示"),
                                self.tr("请填写反馈描述。"))
            return
        payload = feedback_client.build_payload(
            self._cmb_type.currentData(), text,
            app_version=_APP_VERSION,
            attachments=self._collect_attachments(),
        )
        self._btns.button(QDialogButtonBox.Ok).setEnabled(False)
        self._btns.button(QDialogButtonBox.Ok).setText(self.tr("提交中..."))
        self._thread = _SubmitThread(payload, self)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _on_done(self, ok: bool, msg: str):
        if ok:
            QMessageBox.information(self, self.tr("已提交"),
                                    self.tr("感谢反馈！") + f"\n{msg}")
            self.accept()
        else:
            # 失败已存本地队列, 视为"已收下", 提示下次重发
            QMessageBox.information(self, self.tr("已保存"),
                                    self.tr("网络暂不可用, 反馈已保存,"
                                            "下次启动会自动重发。") + f"\n{msg}")
            self.accept()
