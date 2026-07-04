Attribute VB_Name = "SDTTagInsertTool"
'============================================================================
' SDT Tag 插入侧边栏 — VBA UserForm
' 用法: 将本文件导入 Word VBA 工程, 运行 ShowSDTPanel 打开侧边栏
'============================================================================

Option Explicit

' ── 数据结构 ──

Private Type SDTTagInfo
    TagName As String
    Description As String
    Category As String
End Type

Private Tags() As SDTTagInfo
Private TagCount As Long

' ── 初始化 Tag 列表 ──

Private Sub InitTags()
    TagCount = 0
    ReDim Tags(0 To 200)

    ' 项目信息
    AddTag "meta_contract_no", "合同号", "项目信息"
    AddTag "meta_customer", "客户名称", "项目信息"
    AddTag "meta_project", "项目名称", "项目信息"
    AddTag "meta_antenna_model", "天线型号", "项目信息"
    AddTag "meta_test_lab", "测试实验室", "项目信息"
    AddTag "meta_test_engineer", "测试工程师", "项目信息"
    AddTag "meta_test_standard", "测试标准", "项目信息"
    AddTag "meta_test_start_date", "测试开始日期", "项目信息"
    AddTag "meta_test_end_date", "测试结束日期", "项目信息"
    AddTag "meta_approval", "审批信息", "项目信息"
    AddTag "meta_dut_info", "被测件信息", "项目信息"
    AddTag "meta_equipment", "检验设备", "项目信息"
    AddTag "meta_notes", "备注", "项目信息"

    ' 测试配置
    AddTag "config_gain_test", "增益测试要求", "测试配置"
    AddTag "config_eff_test", "效率测试要求", "测试配置"
    AddTag "config_freq_range", "频率范围", "测试配置"

    ' 数据表格
    AddTag "table_data", "通用数据表", "数据表格"

    ' 图片
    AddTag "img_3d_gain", "3D Gain 方向图", "图片"
    AddTag "img_3d_ar", "3D AR 方向图", "图片"
    AddTag "img_3d_directivity", "3D Directivity 方向图", "图片"
    AddTag "img_azimuth_gain", "方位面 Gain 切面", "图片"
    AddTag "img_azimuth_ar", "方位面 AR 切面", "图片"
    AddTag "img_gain_vs_freq", "Gain vs 频率曲线", "图片"
    AddTag "img_efficiency_vs_freq", "效率 vs 频率曲线", "图片"
    AddTag "img_directivity_vs_freq", "方向性 vs 频率曲线", "图片"
    AddTag "img_trp_vs_freq", "TRP vs 频率曲线", "图片"
    AddTag "img_ar_vs_freq", "AR vs 频率曲线", "图片"
    AddTag "img_dut_photo", "被测件照片", "图片"

    ' 循环组
    AddTag "img_group_start", "图片循环起始", "循环组"
    AddTag "img_group_end", "图片循环结束", "循环组"
End Sub

Private Sub AddTag(ByVal Name As String, ByVal Desc As String, ByVal Cat As String)
    Tags(TagCount).TagName = Name
    Tags(TagCount).Description = Desc
    Tags(TagCount).Category = Cat
    TagCount = TagCount + 1
End Sub

' ── UserForm 界面 ──

Private Sub UserForm_Initialize()
    InitTags
    PopulateTree
    Me.Caption = "SDT Tag 插入器"
    Me.Width = 300
    Me.Height = 500
End Sub

Private Sub PopulateTree()
    Dim i As Long, node As MSComctlLib.Node
    TreeView1.Nodes.Clear

    ' Add category nodes
    TreeView1.Nodes.Add , , "cat_meta", "项目信息 (" & CountByCat("项目信息") & ")"
    TreeView1.Nodes.Add , , "cat_config", "测试配置 (" & CountByCat("测试配置") & ")"
    TreeView1.Nodes.Add , , "cat_table", "数据表格 (" & CountByCat("数据表格") & ")"
    TreeView1.Nodes.Add , , "cat_img", "图片 (" & CountByCat("图片") & ")"
    TreeView1.Nodes.Add , , "cat_group", "循环组 (" & CountByCat("循环组") & ")"

    Dim catMap As Object
    Set catMap = CreateObject("Scripting.Dictionary")
    catMap("项目信息") = "cat_meta"
    catMap("测试配置") = "cat_config"
    catMap("数据表格") = "cat_table"
    catMap("图片") = "cat_img"
    catMap("循环组") = "cat_group"

    For i = 0 To TagCount - 1
        Dim parentKey As String
        parentKey = catMap(Tags(i).Category)
        TreeView1.Nodes.Add parentKey, tvwChild, "tag_" & i, _
            Tags(i).TagName & " — " & Tags(i).Description
    Next i
End Sub

Private Function CountByCat(ByVal cat As String) As Long
    Dim i As Long, cnt As Long
    cnt = 0
    For i = 0 To TagCount - 1
        If Tags(i).Category = cat Then cnt = cnt + 1
    Next i
    CountByCat = cnt
End Function

' ── 搜索 ──

Private Sub txtSearch_Change()
    Dim i As Long, txt As String
    txt = LCase(txtSearch.Text)
    If Len(txt) = 0 Then
        PopulateTree
        Exit Sub
    End If

    TreeView1.Nodes.Clear
    For i = 0 To TagCount - 1
        If InStr(1, LCase(Tags(i).TagName), txt) > 0 Or _
           InStr(1, LCase(Tags(i).Description), txt) > 0 Then
            TreeView1.Nodes.Add , , "tag_" & i, _
                Tags(i).TagName & " — " & Tags(i).Description & " [" & Tags(i).Category & "]"
        End If
    Next i
End Sub

' ── 双击插入 SDT ──

Private Sub TreeView1_DblClick()
    Dim node As MSComctlLib.Node
    Set node = TreeView1.SelectedItem
    If node Is Nothing Then Exit Sub

    Dim i As Long
    If Left(node.Key, 4) = "tag_" Then
        i = CLng(Mid(node.Key, 5))
        InsertSDT Tags(i).TagName, Tags(i).Description
    End If
End Sub

' ── 插入 SDT ──

Private Sub InsertSDT(ByVal tagName As String, ByVal tagTitle As String)
    Dim rng As Range
    Set rng = Selection.Range

    ' Create Rich Text Content Control
    Dim cc As ContentControl
    Set cc = ActiveDocument.ContentControls.Add(wdContentControlRichText, rng)

    ' Set tag ( stored in Title for VBA, but program reads w:tag )
    cc.Tag = tagName
    cc.Title = tagTitle

    ' Set placeholder text
    cc.Range.Text = "[" & tagName & "]"
    cc.Range.Font.Color = RGB(128, 128, 128)

    lblStatus.Caption = "✓ 已插入: " & tagName
End Sub

' ── 智能识别 ──

Private Sub btnAutoDetect_Click()
    Dim rng As Range
    Set rng = Selection.Range

    If rng.Tables.Count > 0 Then
        ' Selected area contains a table
        Dim tbl As Table
        Set tbl = rng.Tables(1)

        ' Read first row as header
        Dim headerText As String
        headerText = ""
        Dim cell As Cell
        For Each cell In tbl.Rows(1).Cells
            headerText = headerText & " " & cell.Range.Text
        Next cell

        ' Match by keywords
        If InStr(1, headerText, "Frequency", vbTextCompare) > 0 Then
            If InStr(1, headerText, "Gain", vbTextCompare) > 0 Or _
               InStr(1, headerText, "LAG", vbTextCompare) > 0 Then
                lblStatus.Caption = "→ 建议: table_data (Gain数据表)"
            ElseIf InStr(1, headerText, "AR", vbTextCompare) > 0 Then
                lblStatus.Caption = "→ 建议: table_data (AR数据表)"
            ElseIf InStr(1, headerText, "Efficiency", vbTextCompare) > 0 Then
                lblStatus.Caption = "→ 建议: table_data (效率表)"
            End If
        End If
    ElseIf rng.InlineShapes.Count > 0 Then
        lblStatus.Caption = "→ 建议: img_3d_gain (图片)"
    Else
        lblStatus.Caption = "→ 选中文本: """ & Left(rng.Text, 50) & """"
    End If
End Sub

' ── 复制 Tag 名 ──

Private Sub btnCopyTag_Click()
    Dim node As MSComctlLib.Node
    Set node = TreeView1.SelectedItem
    If node Is Nothing Then Exit Sub

    Dim i As Long
    If Left(node.Key, 4) = "tag_" Then
        i = CLng(Mid(node.Key, 5))
        ' Copy to clipboard using DataObject
        Dim dob As Object
        Set dob = CreateObject("MSForms.DataObject")
        dob.SetText Tags(i).TagName
        dob.PutInClipboard
        lblStatus.Caption = "✓ 已复制: " & Tags(i).TagName
    End If
End Sub

' ── 显示侧边栏 ──

Public Sub ShowSDTPanel()
    SDTPanel.Show vbModeless
End Sub
