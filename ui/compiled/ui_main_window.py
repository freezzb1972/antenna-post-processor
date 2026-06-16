# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar,
    QPushButton, QSizePolicy, QSpacerItem, QSpinBox,
    QStatusBar, QTabWidget, QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1050, 700)
        MainWindow.setMinimumSize(QSize(850, 600))
        self.centralWidget = QWidget(MainWindow)
        self.centralWidget.setObjectName(u"centralWidget")
        self.rootVBox = QVBoxLayout(self.centralWidget)
        self.rootVBox.setSpacing(6)
        self.rootVBox.setObjectName(u"rootVBox")
        self.rootVBox.setContentsMargins(12, 8, 12, 8)
        self.toolbarLayout = QHBoxLayout()
        self.toolbarLayout.setObjectName(u"toolbarLayout")
        self.lblAppTitle = QLabel(self.centralWidget)
        self.lblAppTitle.setObjectName(u"lblAppTitle")

        self.toolbarLayout.addWidget(self.lblAppTitle)

        self.toolbarSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.toolbarLayout.addItem(self.toolbarSpacer)

        self.lblTheme = QLabel(self.centralWidget)
        self.lblTheme.setObjectName(u"lblTheme")

        self.toolbarLayout.addWidget(self.lblTheme)

        self.cmbThemeSelector = QComboBox(self.centralWidget)
        self.cmbThemeSelector.setObjectName(u"cmbThemeSelector")
        self.cmbThemeSelector.setMinimumSize(QSize(150, 28))

        self.toolbarLayout.addWidget(self.cmbThemeSelector)

        self.btnLangToggle = QPushButton(self.centralWidget)
        self.btnLangToggle.setObjectName(u"btnLangToggle")
        self.btnLangToggle.setMinimumSize(QSize(48, 30))

        self.toolbarLayout.addWidget(self.btnLangToggle)


        self.rootVBox.addLayout(self.toolbarLayout)

        self.tabConfig = QTabWidget(self.centralWidget)
        self.tabConfig.setObjectName(u"tabConfig")
        self.tabFile = QWidget()
        self.tabFile.setObjectName(u"tabFile")
        self.vTabFile = QVBoxLayout(self.tabFile)
        self.vTabFile.setSpacing(10)
        self.vTabFile.setObjectName(u"vTabFile")
        self.groupInput = QGroupBox(self.tabFile)
        self.groupInput.setObjectName(u"groupInput")
        self.formInput = QFormLayout(self.groupInput)
        self.formInput.setSpacing(8)
        self.formInput.setObjectName(u"formInput")
        self.lblCsv = QLabel(self.groupInput)
        self.lblCsv.setObjectName(u"lblCsv")

        self.formInput.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblCsv)

        self.hboxLayout = QHBoxLayout()
        self.hboxLayout.setObjectName(u"hboxLayout")
        self.editCsvPath = QLineEdit(self.groupInput)
        self.editCsvPath.setObjectName(u"editCsvPath")

        self.hboxLayout.addWidget(self.editCsvPath)

        self.btnBrowseCsv = QPushButton(self.groupInput)
        self.btnBrowseCsv.setObjectName(u"btnBrowseCsv")

        self.hboxLayout.addWidget(self.btnBrowseCsv)


        self.formInput.setLayout(0, QFormLayout.ItemRole.FieldRole, self.hboxLayout)

        self.lblTemplate = QLabel(self.groupInput)
        self.lblTemplate.setObjectName(u"lblTemplate")

        self.formInput.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblTemplate)

        self.hboxLayout1 = QHBoxLayout()
        self.hboxLayout1.setObjectName(u"hboxLayout1")
        self.editTemplatePath = QLineEdit(self.groupInput)
        self.editTemplatePath.setObjectName(u"editTemplatePath")

        self.hboxLayout1.addWidget(self.editTemplatePath)

        self.btnBrowseTemplate = QPushButton(self.groupInput)
        self.btnBrowseTemplate.setObjectName(u"btnBrowseTemplate")

        self.hboxLayout1.addWidget(self.btnBrowseTemplate)


        self.formInput.setLayout(1, QFormLayout.ItemRole.FieldRole, self.hboxLayout1)


        self.vTabFile.addWidget(self.groupInput)

        self.groupOutput = QGroupBox(self.tabFile)
        self.groupOutput.setObjectName(u"groupOutput")
        self.formOutput = QFormLayout(self.groupOutput)
        self.formOutput.setSpacing(8)
        self.formOutput.setObjectName(u"formOutput")
        self.lblOutputDir = QLabel(self.groupOutput)
        self.lblOutputDir.setObjectName(u"lblOutputDir")

        self.formOutput.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblOutputDir)

        self.hboxLayout2 = QHBoxLayout()
        self.hboxLayout2.setObjectName(u"hboxLayout2")
        self.editOutputDir = QLineEdit(self.groupOutput)
        self.editOutputDir.setObjectName(u"editOutputDir")

        self.hboxLayout2.addWidget(self.editOutputDir)

        self.btnBrowseOutput = QPushButton(self.groupOutput)
        self.btnBrowseOutput.setObjectName(u"btnBrowseOutput")

        self.hboxLayout2.addWidget(self.btnBrowseOutput)


        self.formOutput.setLayout(0, QFormLayout.ItemRole.FieldRole, self.hboxLayout2)

        self.lblOutputName = QLabel(self.groupOutput)
        self.lblOutputName.setObjectName(u"lblOutputName")

        self.formOutput.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblOutputName)

        self.editOutputName = QLineEdit(self.groupOutput)
        self.editOutputName.setObjectName(u"editOutputName")

        self.formOutput.setWidget(1, QFormLayout.ItemRole.FieldRole, self.editOutputName)

        self.checkFullReport = QCheckBox(self.groupOutput)
        self.checkFullReport.setObjectName(u"checkFullReport")

        self.formOutput.setWidget(2, QFormLayout.ItemRole.LabelRole, self.checkFullReport)

        self.lblFullReportPath = QLabel(self.groupOutput)
        self.lblFullReportPath.setObjectName(u"lblFullReportPath")

        self.formOutput.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblFullReportPath)

        self.hboxLayout3 = QHBoxLayout()
        self.hboxLayout3.setObjectName(u"hboxLayout3")
        self.editFullReportPath = QLineEdit(self.groupOutput)
        self.editFullReportPath.setObjectName(u"editFullReportPath")

        self.hboxLayout3.addWidget(self.editFullReportPath)

        self.btnBrowseFullReport = QPushButton(self.groupOutput)
        self.btnBrowseFullReport.setObjectName(u"btnBrowseFullReport")

        self.hboxLayout3.addWidget(self.btnBrowseFullReport)


        self.formOutput.setLayout(3, QFormLayout.ItemRole.FieldRole, self.hboxLayout3)


        self.vTabFile.addWidget(self.groupOutput)

        self.spFile = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.vTabFile.addItem(self.spFile)

        self.tabConfig.addTab(self.tabFile, "")
        self.tabLag = QWidget()
        self.tabLag.setObjectName(u"tabLag")
        self.vTabLag = QVBoxLayout(self.tabLag)
        self.vTabLag.setSpacing(10)
        self.vTabLag.setObjectName(u"vTabLag")
        self.groupQuickSingle = QGroupBox(self.tabLag)
        self.groupQuickSingle.setObjectName(u"groupQuickSingle")
        self.hQuickSingle = QHBoxLayout(self.groupQuickSingle)
        self.hQuickSingle.setObjectName(u"hQuickSingle")
        self.btnQuick0 = QPushButton(self.groupQuickSingle)
        self.btnQuick0.setObjectName(u"btnQuick0")
        self.btnQuick0.setCheckable(True)

        self.hQuickSingle.addWidget(self.btnQuick0)

        self.btnQuick30 = QPushButton(self.groupQuickSingle)
        self.btnQuick30.setObjectName(u"btnQuick30")
        self.btnQuick30.setCheckable(True)

        self.hQuickSingle.addWidget(self.btnQuick30)

        self.btnQuick60 = QPushButton(self.groupQuickSingle)
        self.btnQuick60.setObjectName(u"btnQuick60")
        self.btnQuick60.setCheckable(True)
        self.btnQuick60.setChecked(True)

        self.hQuickSingle.addWidget(self.btnQuick60)

        self.btnQuick70 = QPushButton(self.groupQuickSingle)
        self.btnQuick70.setObjectName(u"btnQuick70")
        self.btnQuick70.setCheckable(True)
        self.btnQuick70.setChecked(True)

        self.hQuickSingle.addWidget(self.btnQuick70)

        self.btnQuick80 = QPushButton(self.groupQuickSingle)
        self.btnQuick80.setObjectName(u"btnQuick80")
        self.btnQuick80.setCheckable(True)
        self.btnQuick80.setChecked(True)

        self.hQuickSingle.addWidget(self.btnQuick80)

        self.btnQuick90 = QPushButton(self.groupQuickSingle)
        self.btnQuick90.setObjectName(u"btnQuick90")
        self.btnQuick90.setCheckable(True)
        self.btnQuick90.setChecked(True)

        self.hQuickSingle.addWidget(self.btnQuick90)

        self.spQuick = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.hQuickSingle.addItem(self.spQuick)

        self.lblCustomAngle = QLabel(self.groupQuickSingle)
        self.lblCustomAngle.setObjectName(u"lblCustomAngle")

        self.hQuickSingle.addWidget(self.lblCustomAngle)

        self.spinCustomAngle = QDoubleSpinBox(self.groupQuickSingle)
        self.spinCustomAngle.setObjectName(u"spinCustomAngle")
        self.spinCustomAngle.setValue(0.000000000000000)
        self.spinCustomAngle.setMaximum(180.000000000000000)

        self.hQuickSingle.addWidget(self.spinCustomAngle)

        self.btnAddCustomAngle = QPushButton(self.groupQuickSingle)
        self.btnAddCustomAngle.setObjectName(u"btnAddCustomAngle")

        self.hQuickSingle.addWidget(self.btnAddCustomAngle)


        self.vTabLag.addWidget(self.groupQuickSingle)

        self.groupStepGen = QGroupBox(self.tabLag)
        self.groupStepGen.setObjectName(u"groupStepGen")
        self.hStepGen = QHBoxLayout(self.groupStepGen)
        self.hStepGen.setObjectName(u"hStepGen")
        self.lblStepStart = QLabel(self.groupStepGen)
        self.lblStepStart.setObjectName(u"lblStepStart")

        self.hStepGen.addWidget(self.lblStepStart)

        self.spinStepStart = QDoubleSpinBox(self.groupStepGen)
        self.spinStepStart.setObjectName(u"spinStepStart")
        self.spinStepStart.setValue(0.000000000000000)
        self.spinStepStart.setMaximum(180.000000000000000)

        self.hStepGen.addWidget(self.spinStepStart)

        self.lblStepEnd = QLabel(self.groupStepGen)
        self.lblStepEnd.setObjectName(u"lblStepEnd")

        self.hStepGen.addWidget(self.lblStepEnd)

        self.spinStepEnd = QDoubleSpinBox(self.groupStepGen)
        self.spinStepEnd.setObjectName(u"spinStepEnd")
        self.spinStepEnd.setValue(90.000000000000000)
        self.spinStepEnd.setMaximum(180.000000000000000)

        self.hStepGen.addWidget(self.spinStepEnd)

        self.lblStepBy = QLabel(self.groupStepGen)
        self.lblStepBy.setObjectName(u"lblStepBy")

        self.hStepGen.addWidget(self.lblStepBy)

        self.spinStepBy = QDoubleSpinBox(self.groupStepGen)
        self.spinStepBy.setObjectName(u"spinStepBy")
        self.spinStepBy.setValue(10.000000000000000)
        self.spinStepBy.setMinimum(0.500000000000000)
        self.spinStepBy.setMaximum(90.000000000000000)

        self.hStepGen.addWidget(self.spinStepBy)

        self.btnStepGenerate = QPushButton(self.groupStepGen)
        self.btnStepGenerate.setObjectName(u"btnStepGenerate")

        self.hStepGen.addWidget(self.btnStepGenerate)


        self.vTabLag.addWidget(self.groupStepGen)

        self.groupRange = QGroupBox(self.tabLag)
        self.groupRange.setObjectName(u"groupRange")
        self.hRange = QHBoxLayout(self.groupRange)
        self.hRange.setObjectName(u"hRange")
        self.lblRStart = QLabel(self.groupRange)
        self.lblRStart.setObjectName(u"lblRStart")

        self.hRange.addWidget(self.lblRStart)

        self.spinRStart = QDoubleSpinBox(self.groupRange)
        self.spinRStart.setObjectName(u"spinRStart")
        self.spinRStart.setValue(0.000000000000000)
        self.spinRStart.setMaximum(180.000000000000000)

        self.hRange.addWidget(self.spinRStart)

        self.lblREnd = QLabel(self.groupRange)
        self.lblREnd.setObjectName(u"lblREnd")

        self.hRange.addWidget(self.lblREnd)

        self.spinREnd = QDoubleSpinBox(self.groupRange)
        self.spinREnd.setObjectName(u"spinREnd")
        self.spinREnd.setValue(90.000000000000000)
        self.spinREnd.setMaximum(180.000000000000000)

        self.hRange.addWidget(self.spinREnd)

        self.btnAddRange = QPushButton(self.groupRange)
        self.btnAddRange.setObjectName(u"btnAddRange")

        self.hRange.addWidget(self.btnAddRange)

        self.spRange = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.hRange.addItem(self.spRange)


        self.vTabLag.addWidget(self.groupRange)

        self.groupConfigured = QGroupBox(self.tabLag)
        self.groupConfigured.setObjectName(u"groupConfigured")
        self.vConfigured = QVBoxLayout(self.groupConfigured)
        self.vConfigured.setSpacing(6)
        self.vConfigured.setObjectName(u"vConfigured")
        self.configItemsWidget = QWidget(self.groupConfigured)
        self.configItemsWidget.setObjectName(u"configItemsWidget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.configItemsWidget.sizePolicy().hasHeightForWidth())
        self.configItemsWidget.setSizePolicy(sizePolicy)

        self.vConfigured.addWidget(self.configItemsWidget)

        self.hConfigButtons = QHBoxLayout()
        self.hConfigButtons.setObjectName(u"hConfigButtons")
        self.btnLoadFromTemplate = QPushButton(self.groupConfigured)
        self.btnLoadFromTemplate.setObjectName(u"btnLoadFromTemplate")

        self.hConfigButtons.addWidget(self.btnLoadFromTemplate)

        self.btnClearConfig = QPushButton(self.groupConfigured)
        self.btnClearConfig.setObjectName(u"btnClearConfig")

        self.hConfigButtons.addWidget(self.btnClearConfig)

        self.btnSavePreset = QPushButton(self.groupConfigured)
        self.btnSavePreset.setObjectName(u"btnSavePreset")

        self.hConfigButtons.addWidget(self.btnSavePreset)

        self.btnLoadPreset = QPushButton(self.groupConfigured)
        self.btnLoadPreset.setObjectName(u"btnLoadPreset")

        self.hConfigButtons.addWidget(self.btnLoadPreset)

        self.spConfig = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.hConfigButtons.addItem(self.spConfig)


        self.vConfigured.addLayout(self.hConfigButtons)


        self.vTabLag.addWidget(self.groupConfigured)

        self.tabConfig.addTab(self.tabLag, "")
        self.tabPlot = QWidget()
        self.tabPlot.setObjectName(u"tabPlot")
        self.vTabPlot = QVBoxLayout(self.tabPlot)
        self.vTabPlot.setSpacing(10)
        self.vTabPlot.setObjectName(u"vTabPlot")
        self.groupGenImg = QGroupBox(self.tabPlot)
        self.groupGenImg.setObjectName(u"groupGenImg")
        self.vboxLayout = QVBoxLayout(self.groupGenImg)
        self.vboxLayout.setSpacing(4)
        self.vboxLayout.setObjectName(u"vboxLayout")
        self.checkEmbedExcel = QCheckBox(self.groupGenImg)
        self.checkEmbedExcel.setObjectName(u"checkEmbedExcel")
        self.checkEmbedExcel.setChecked(True)

        self.vboxLayout.addWidget(self.checkEmbedExcel)

        self.checkSavePng = QCheckBox(self.groupGenImg)
        self.checkSavePng.setObjectName(u"checkSavePng")

        self.vboxLayout.addWidget(self.checkSavePng)


        self.vTabPlot.addWidget(self.groupGenImg)

        self.groupView = QGroupBox(self.tabPlot)
        self.groupView.setObjectName(u"groupView")
        self.formView = QFormLayout(self.groupView)
        self.formView.setSpacing(8)
        self.formView.setObjectName(u"formView")
        self.lblElev = QLabel(self.groupView)
        self.lblElev.setObjectName(u"lblElev")

        self.formView.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblElev)

        self.spinElev = QDoubleSpinBox(self.groupView)
        self.spinElev.setObjectName(u"spinElev")
        self.spinElev.setValue(30.000000000000000)
        self.spinElev.setMinimum(-90.000000000000000)
        self.spinElev.setMaximum(90.000000000000000)

        self.formView.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinElev)

        self.lblAzim = QLabel(self.groupView)
        self.lblAzim.setObjectName(u"lblAzim")

        self.formView.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblAzim)

        self.spinAzim = QDoubleSpinBox(self.groupView)
        self.spinAzim.setObjectName(u"spinAzim")
        self.spinAzim.setValue(-60.000000000000000)
        self.spinAzim.setMinimum(-180.000000000000000)
        self.spinAzim.setMaximum(180.000000000000000)

        self.formView.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinAzim)

        self.lblDpi = QLabel(self.groupView)
        self.lblDpi.setObjectName(u"lblDpi")

        self.formView.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblDpi)

        self.spinDpi = QSpinBox(self.groupView)
        self.spinDpi.setObjectName(u"spinDpi")
        self.spinDpi.setValue(150)
        self.spinDpi.setMinimum(72)
        self.spinDpi.setMaximum(300)

        self.formView.setWidget(2, QFormLayout.ItemRole.FieldRole, self.spinDpi)


        self.vTabPlot.addWidget(self.groupView)

        self.spPlot = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.vTabPlot.addItem(self.spPlot)

        self.tabConfig.addTab(self.tabPlot, "")
        self.tabCalc = QWidget()
        self.tabCalc.setObjectName(u"tabCalc")
        self.vTabCalc = QVBoxLayout(self.tabCalc)
        self.vTabCalc.setSpacing(10)
        self.vTabCalc.setObjectName(u"vTabCalc")
        self.tabConfig.addTab(self.tabCalc, "")

        self.rootVBox.addWidget(self.tabConfig)

        self.hProgress = QHBoxLayout()
        self.hProgress.setObjectName(u"hProgress")
        self.progressBar = QProgressBar(self.centralWidget)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(100)

        self.hProgress.addWidget(self.progressBar)

        self.lblProgressMsg = QLabel(self.centralWidget)
        self.lblProgressMsg.setObjectName(u"lblProgressMsg")
        self.lblProgressMsg.setMinimumSize(QSize(320, 0))

        self.hProgress.addWidget(self.lblProgressMsg)


        self.rootVBox.addLayout(self.hProgress)

        self.logOutput = QPlainTextEdit(self.centralWidget)
        self.logOutput.setObjectName(u"logOutput")
        self.logOutput.setReadOnly(True)
        self.logOutput.setMaximumBlockCount(5000)

        self.rootVBox.addWidget(self.logOutput)

        self.hButtons = QHBoxLayout()
        self.hButtons.setObjectName(u"hButtons")
        self.spBtnLeft = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.hButtons.addItem(self.spBtnLeft)

        self.btnStart = QPushButton(self.centralWidget)
        self.btnStart.setObjectName(u"btnStart")
        self.btnStart.setMinimumSize(QSize(140, 36))

        self.hButtons.addWidget(self.btnStart)

        self.btnStop = QPushButton(self.centralWidget)
        self.btnStop.setObjectName(u"btnStop")
        self.btnStop.setMinimumSize(QSize(100, 36))
        self.btnStop.setEnabled(False)

        self.hButtons.addWidget(self.btnStop)


        self.rootVBox.addLayout(self.hButtons)

        self.statusBar = QStatusBar(self.centralWidget)
        self.statusBar.setObjectName(u"statusBar")
        self.statusBar.setSizeGripEnabled(False)

        self.rootVBox.addWidget(self.statusBar)

        MainWindow.setCentralWidget(self.centralWidget)

        self.retranslateUi(MainWindow)

        self.tabConfig.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"\u5929\u7ebf\u53c2\u6570\u540e\u5904\u7406\u5de5\u5177 \u2014 Antenna Post-Processor", None))
        self.lblAppTitle.setText(QCoreApplication.translate("MainWindow", u"\U0001f4e1 \U00005929\U00007ebf\U000053c2\U00006570\U0000540e\U00005904\U00007406\U00005de5\U00005177", None))
        self.lblAppTitle.setStyleSheet(QCoreApplication.translate("MainWindow", u"font-size: 18px; font-weight: bold;", None))
        self.lblTheme.setText(QCoreApplication.translate("MainWindow", u"\U0001f3a8 \U00004e3b\U00009898\U0000ff1a", None))
#if QT_CONFIG(tooltip)
        self.cmbThemeSelector.setToolTip(QCoreApplication.translate("MainWindow", u"\u5207\u6362 Material Design \u4e3b\u9898", None))
#endif // QT_CONFIG(tooltip)
        self.btnLangToggle.setText(QCoreApplication.translate("MainWindow", u"EN", None))
#if QT_CONFIG(tooltip)
        self.btnLangToggle.setToolTip(QCoreApplication.translate("MainWindow", u"Switch Language / \u5207\u6362\u8bed\u8a00", None))
#endif // QT_CONFIG(tooltip)
        self.groupInput.setTitle(QCoreApplication.translate("MainWindow", u"\u8f93\u5165", None))
        self.lblCsv.setText(QCoreApplication.translate("MainWindow", u"\u8f93\u5165\u6587\u4ef6\uff1a", None))
        self.editCsvPath.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u652f\u6301 .csv .xlsx .xls ...", None))
        self.btnBrowseCsv.setText(QCoreApplication.translate("MainWindow", u"\u6d4f\u89c8...", None))
        self.lblTemplate.setText(QCoreApplication.translate("MainWindow", u"\u6a21\u677f Excel\uff1a", None))
        self.editTemplatePath.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u9009\u62e9\u6a21\u677f .xlsx ...", None))
        self.btnBrowseTemplate.setText(QCoreApplication.translate("MainWindow", u"\u6d4f\u89c8...", None))
        self.groupOutput.setTitle(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa", None))
        self.lblOutputDir.setText(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa\u76ee\u5f55\uff1a", None))
        self.editOutputDir.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u9ed8\u8ba4: ./output", None))
        self.btnBrowseOutput.setText(QCoreApplication.translate("MainWindow", u"\u6d4f\u89c8...", None))
        self.lblOutputName.setText(QCoreApplication.translate("MainWindow", u"\u6587\u4ef6\u540d\uff1a", None))
        self.editOutputName.setText(QCoreApplication.translate("MainWindow", u"antenna_report.xlsx", None))
        self.checkFullReport.setText(QCoreApplication.translate("MainWindow", u"\u751f\u6210\u5b8c\u6574\u62a5\u544a\uff08\u72ec\u7acb\u6587\u4ef6\uff0c\u542b\u5168\u90e8\u6307\u6807 + 2D/3D \u56fe\uff09", None))
        self.lblFullReportPath.setText(QCoreApplication.translate("MainWindow", u"\u62a5\u544a\u8def\u5f84\uff1a", None))
        self.editFullReportPath.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u9ed8\u8ba4: ./output/full_report.xlsx", None))
        self.btnBrowseFullReport.setText(QCoreApplication.translate("MainWindow", u"\u6d4f\u89c8...", None))
        self.tabConfig.setTabText(self.tabConfig.indexOf(self.tabFile), QCoreApplication.translate("MainWindow", u"\U0001f4c2 \U00006587\U00004ef6\U00008bbe\U00007f6e", None))
        self.groupQuickSingle.setTitle(QCoreApplication.translate("MainWindow", u"\u5feb\u6377\u5355\u89d2\u5ea6\uff08\u70b9\u51fb\u5207\u6362\uff09", None))
        self.btnQuick0.setText(QCoreApplication.translate("MainWindow", u"0\u00b0", None))
        self.btnQuick30.setText(QCoreApplication.translate("MainWindow", u"30\u00b0", None))
        self.btnQuick60.setText(QCoreApplication.translate("MainWindow", u"60\u00b0", None))
        self.btnQuick70.setText(QCoreApplication.translate("MainWindow", u"70\u00b0", None))
        self.btnQuick80.setText(QCoreApplication.translate("MainWindow", u"80\u00b0", None))
        self.btnQuick90.setText(QCoreApplication.translate("MainWindow", u"90\u00b0", None))
        self.lblCustomAngle.setText(QCoreApplication.translate("MainWindow", u"\u81ea\u5b9a\u4e49\uff1a", None))
        self.spinCustomAngle.setSuffix(QCoreApplication.translate("MainWindow", u"\u00b0", None))
        self.btnAddCustomAngle.setText(QCoreApplication.translate("MainWindow", u"+", None))
        self.groupStepGen.setTitle(QCoreApplication.translate("MainWindow", u"\u6b65\u8fdb\u6279\u91cf\u751f\u6210", None))
        self.lblStepStart.setText(QCoreApplication.translate("MainWindow", u"\u8d77\u59cb\uff1a", None))
        self.spinStepStart.setSuffix(QCoreApplication.translate("MainWindow", u"\u00b0", None))
        self.lblStepEnd.setText(QCoreApplication.translate("MainWindow", u"\u7ed3\u675f\uff1a", None))
        self.spinStepEnd.setSuffix(QCoreApplication.translate("MainWindow", u"\u00b0", None))
        self.lblStepBy.setText(QCoreApplication.translate("MainWindow", u"\u6b65\u8fdb\uff1a", None))
        self.spinStepBy.setSuffix(QCoreApplication.translate("MainWindow", u"\u00b0", None))
        self.btnStepGenerate.setText(QCoreApplication.translate("MainWindow", u"\u751f\u6210 >>", None))
        self.groupRange.setTitle(QCoreApplication.translate("MainWindow", u"\u6dfb\u52a0\u89d2\u5ea6\u8303\u56f4 LAG\uff08\u53d6\u8303\u56f4\u5185\u6240\u6709 \u03b8 \u7684 LAG \u5747\u503c\uff09", None))
        self.lblRStart.setText(QCoreApplication.translate("MainWindow", u"\u8d77\u59cb\uff1a", None))
        self.spinRStart.setSuffix(QCoreApplication.translate("MainWindow", u"\u00b0", None))
        self.lblREnd.setText(QCoreApplication.translate("MainWindow", u"\u7ed3\u675f\uff1a", None))
        self.spinREnd.setSuffix(QCoreApplication.translate("MainWindow", u"\u00b0", None))
        self.btnAddRange.setText(QCoreApplication.translate("MainWindow", u"\u6dfb\u52a0\u8303\u56f4", None))
        self.groupConfigured.setTitle(QCoreApplication.translate("MainWindow", u"\u5df2\u914d\u7f6e\u9879", None))
        self.btnLoadFromTemplate.setText(QCoreApplication.translate("MainWindow", u"\U0001f4e5 \U00004ece\U00006a21\U0000677f\U000052a0\U00008f7d", None))
        self.btnClearConfig.setText(QCoreApplication.translate("MainWindow", u"\U0001f5d1 \U00006e05\U00007a7a", None))
        self.btnSavePreset.setText(QCoreApplication.translate("MainWindow", u"\U0001f4be \U00004fdd\U00005b58\U00009884\U00008bbe", None))
        self.btnLoadPreset.setText(QCoreApplication.translate("MainWindow", u"\U0001f4c2 \U000052a0\U00008f7d\U00009884\U00008bbe", None))
        self.tabConfig.setTabText(self.tabConfig.indexOf(self.tabLag), QCoreApplication.translate("MainWindow", u"\U0001f4d0 \U00005904\U00007406\U000053c2\U00006570\U0000914d\U00007f6e", None))
        self.groupGenImg.setTitle(QCoreApplication.translate("MainWindow", u"\u751f\u6210\u9009\u9879", None))
        self.checkEmbedExcel.setText(QCoreApplication.translate("MainWindow", u"\u5d4c\u5165 Excel \u5de5\u4f5c\u8868", None))
        self.checkSavePng.setText(QCoreApplication.translate("MainWindow", u"\u5355\u72ec\u4fdd\u5b58 PNG \u6587\u4ef6\uff08\u5230\u8f93\u51fa\u76ee\u5f55\u4e0b\u7684 png/ \u6587\u4ef6\u5939\uff09", None))
        self.groupView.setTitle(QCoreApplication.translate("MainWindow", u"3D \u89c6\u89d2\u8bbe\u7f6e", None))
        self.lblElev.setText(QCoreApplication.translate("MainWindow", u"\u4ef0\u89d2 Elevation\uff1a", None))
        self.spinElev.setSuffix(QCoreApplication.translate("MainWindow", u"\u00b0", None))
        self.lblAzim.setText(QCoreApplication.translate("MainWindow", u"\u65b9\u4f4d\u89d2 Azimuth\uff1a", None))
        self.spinAzim.setSuffix(QCoreApplication.translate("MainWindow", u"\u00b0", None))
        self.lblDpi.setText(QCoreApplication.translate("MainWindow", u"\u5206\u8fa8\u7387 DPI\uff1a", None))
        self.tabConfig.setTabText(self.tabConfig.indexOf(self.tabPlot), QCoreApplication.translate("MainWindow", u"\U0001f4ca 3D \U000056fe\U00005f62", None))
        self.tabConfig.setTabText(self.tabConfig.indexOf(self.tabCalc), QCoreApplication.translate("MainWindow", u"\U0001f9ee \U000053c2\U00006570\U00008bbe\U00007f6e", None))
        self.progressBar.setFormat(QCoreApplication.translate("MainWindow", u"%p%", None))
        self.lblProgressMsg.setText(QCoreApplication.translate("MainWindow", u"\u5c31\u7eea", None))
        self.logOutput.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u5904\u7406\u65e5\u5fd7\u5c06\u5728\u6b64\u663e\u793a...", None))
        self.btnStart.setText(QCoreApplication.translate("MainWindow", u"\u25b6 \u5f00\u59cb\u5904\u7406", None))
        self.btnStart.setStyleSheet(QCoreApplication.translate("MainWindow", u"font-weight: bold; font-size: 14px;", None))
        self.btnStop.setText(QCoreApplication.translate("MainWindow", u"\u23f9 \u505c\u6b62", None))
    # retranslateUi

