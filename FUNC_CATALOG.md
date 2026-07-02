# 函数目录 (Function Catalog)

> 自动生成于 `generate_func_catalog.py`。覆盖 `src/` 下 316 个公开函数。
> 每次 `git commit` 后自动更新。

## 复用等级

| 等级 | 含义 | 使用规则 |
|------|------|---------|
| **A** | 纯函数，高复用 | 新功能优先复用。修改需参数化，不破坏已有调用。 |
| **B** | 有副作用，模块级 | 同模块内复用。跨模块调用需评估。 |
| **C** | 内部实现 | 不直接复用。但如果有 ≥2 个类似 C 级函数，应提取为 A 级。 |

## activation

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `activate` | activation_code, machine_id, server_url | 向激活服务器请求许可。返回 (成功与否, 消息)。 |  |
| A | `get_machine_id` | — | 获取当前机器 ID（与 src/license.py 中的实现一致）。 |  |
| A | `get_server_url` | — | 获取激活服务器 URL。 |  |
| A | `set_server_url` | url | 持久化激活服务器 URL 到 QSettings。 |  |

## azimuth_config

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| A | `angles_ar_sorted` | — | 排序去重后的 AR 选定角度。 |  |
| A | `angles_lhcp_sorted` | — | 排序去重后的 LHCP 选定角度。 |  |
| A | `angles_rhcp_sorted` | — | 排序去重后的 RHCP 选定角度。 |  |
| A | `angles_sorted` | — | 排序去重后的 Gain 选定角度。 |  |
| A | `chart_output_path` | — | 完整的图表输出路径。 |  |
| A | `data_ar_output_path` | — | AR 中间数据完整输出路径。 |  |
| A | `data_gain_output_path` | — | Gain 中间数据完整输出路径。 |  |
| A | `from_dict` | cls, d | 从 dict 反序列化。 |  |
| A | `has_any_azimuth` | — | 是否启用了任一 azimuth 切面。 |  |
| A | `has_both` | — | 是否同时启用了 Gain 和 AR。 |  |
| A | `is_empty` | — | 是否没有任何方位面图表启用。 |  |
| A | `merge` | other | 合并两个配置（OR 逻辑），角度取并集，路径取 self 优先。 |  |
| A | `reset_to_defaults` | source_path | 根据源文件路径重置所有输出路径为默认值。 |  |
| A | `to_dict` | — | 序列化为 dict。 |  |

## azimuth_data_writer

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `write_azimuth_data` | freq_data, output_path, value_label | 将方位面切面中间数据写入 Excel。 |  |

## calculator

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| A | `compute_ar_at_angles` | ar_linear, theta_angles_deg, target_angles_deg | 批量计算多个 θ 角的 AR（取 phi 最大值，行业标准的 worst-case）。 |  |
| A | `compute_ar_range` | ar_linear, theta_angles_deg, theta_start, theta_end | 指定 θ 范围内的 AR 最大值（行业标准的 worst-case 覆盖空域性能）。 |  |
| A | `compute_average_gain_db` | gain_linear | 平均增益（线性域均值转 dB）。 |  |
| A | `compute_average_power_dbm` | gain_linear | 平均功率（线性域均值转 dBm）。 |  |
| A | `compute_axial_ratio` | theta_logmag, theta_phase, phi_logmag, phi_phase | 计算轴比 AR（线性值），基于极化椭圆。 |  |
| A | `compute_beamwidth` | gain_linear, theta_deg, phi_deg | 计算3dB波束宽度 (theta 和 phi 方向)。 |  |
| A | `compute_boresight` | gain_linear, theta_angles_deg, phi_angles_deg | 查找主波束指向（最大增益方向）。 |  |
| A | `compute_cp_xpi` | rhcp_gain, lhcp_gain | 计算圆极化交叉极化隔离度 CP-XPI (dB)。 |  |
| A | `compute_directivity` | gain_linear, theta_rad | 球面积分计算方向性系数。 |  |
| A | `compute_efficiency` | peak_gain_dbi, directivity_dbi | 从增益和方向性推算辐射效率。 |  |
| A | `compute_lag_at_angles` | gain_linear, theta_angles_deg, target_angles_deg | 批量计算多个 θ 角的 LAG。 |  |
| A | `compute_lag_range` | gain_linear, theta_angles_deg, theta_start, theta_end | 指定 θ 范围内的方位面平均增益的均值。 |  |
| A | `compute_lag_ranges` | gain_linear, theta_angles_deg, ranges | 批量计算多个 θ 范围的 LAG。 |  |
| A | `compute_lag_single` | gain_linear, theta_idx | 固定俯仰角 θ 上的方位面平均增益。 |  |
| A | `compute_lower_hemisphere_prp` | gain_linear, theta_rad | 下半球部分辐射功率 (Lower Hemisphere PRP)。 |  |
| A | `compute_min_power_dbm` | gain_linear | 方向图中非零功率最小值。 |  |
| A | `compute_nhprp` | gain_linear, theta_rad, edge_deg | CTIA 近地平线部分辐射功率 (NHPRP)，默认 ±45°。 |  |
| A | `compute_nhprp_flex` | gain_linear, theta_rad, edge_deg | 近地平线部分辐射功率 (NHPRP)，可指定任意边界角度。 |  |
| A | `compute_partial_prp` | gain_linear, theta_rad, theta_start_deg, theta_end_deg | 指定 θ 范围内的部分辐射功率 (Partial PRP)。 |  |
| A | `compute_peak_eirp` | eirp_linear | 峰值 EIRP (dBm)。 |  |
| A | `compute_phase_center` | theta_phase, phi_phase, theta_angles_deg, freq_mhz, ... | 计算相位中心偏移 (mm). |  |
| A | `compute_power_ratios` | max_power_dbm, min_power_dbm, avg_power_dbm | 计算功率比: Max/Min, Max/Avg, Min/Avg (dB)。 |  |
| A | `compute_prp_trp_ratio` | prp_dbm, trp_dbm | PRP 与 TRP 之比。 |  |
| A | `compute_rhcp_lhcp_gain` | theta_logmag, theta_phase, phi_logmag, phi_phase | 计算 RHCP 和 LHCP 增益 (dBi) 矩阵。 |  |
| A | `compute_total_efficiency` | efficiency_pct, s11_db | 计算总效率 = 辐射效率 × (1 - |S11|²). |  |
| A | `compute_total_gain_linear` | theta_logmag, phi_logmag | 计算总增益（Theta + Phi 极化合成）。 |  |
| A | `compute_trp` | eirp_linear, theta_rad | CTIA 全向辐射功率 (TRP)。 |  |
| A | `compute_upper_hemisphere_prp` | gain_linear, theta_rad | 上半球部分辐射功率 (Upper Hemisphere PRP)。 |  |
| A | `compute_xpi` | theta_logmag, phi_logmag | 计算交叉极化隔离度 (Cross-Polarization Isolation). |  |

## chart_config

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `has_any_a_class` | — | — |  |
| C | `has_any_b_class` | — | — |  |
| C | `has_any_c_class` | — | — |  |
| B | `from_template` | cls, template_path | 扫描模板文件：元数据行 + 列头 → 自动检测图形需求。 |  |
| B | `merge` | other | 合并两个配置（OR 逻辑），视角参数取 self 的值。 |  |
| A | `all_chart_keys` | cls | 返回所有图形 flag 的 key 列表（不含视角参数和角度列表）。 |  |
| A | `all_sub_angle_keys` | cls | 返回所有子角度列表的 key。 |  |
| A | `chart_categories` | cls | 返回图形分类: 类别名 → [chart_key, ...] |  |
| A | `chart_labels` | cls | 返回图形 key → 中文显示名称映射。 |  |
| A | `from_template_headers` | cls, headers, col_types | 从列头文本列表和 col_type 集合推导图形需求。 |  |
| A | `has_any_pattern_or_cut` | — | 是否有需要逐频点生成的图形（A 或 C 类）。 |  |

## chart_word_writer

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `write_chart_word_report` | image_groups, output_path, antenna_name, angles_str, ... | 将多组图表图片写入 Word 文档。 |  |
| B | `write_chart_word_report_by_freq` | freq_pairs, pair_order, pair_labels, output_path, ... | 按频点排列图表: 每频点一行 N 张图并排。 |  |

## column_mapping

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `effective_type` | — | — |  |
| C | `from_dict` | cls, d | — |  |
| C | `from_dict` | cls, d | — |  |
| C | `to_dict` | — | — |  |
| C | `to_dict` | — | — |  |
| B | `load_presets` | — | 从 templates.json 加载所有模板预设。 |  |
| B | `save_preset` | preset | 保存一个模板预设到 templates.json（合并写入）。 |  |
| A | `classify_header` | raw_header | 统一列头分类入口。JSON 模式优先 → 内置函数 fallback → regex fallback。 |  |
| A | `detect_columns_from_template` | template_path, header_row | 从模板文件检测所有列的 col_type。 |  |

## config_manager

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | — | — |  |
| C | `__new__` | cls | — |  |
| C | `config` | — | — |  |
| C | `to_license_dict` | — | — |  |
| B | `get_config` | — | 获取全局配置单例。 |  |
| B | `get_config_manager` | — | 获取配置管理器实例。 |  |
| B | `is_license_valid` | — | 检查当前许可是否有效。 |  |
| B | `load` | — | 加载配置。如果文件不存在，尝试从 QSettings 迁移。 |  |
| B | `save` | — | 保存配置到文件。 |  |
| B | `save_config` | — | 保存全局配置。 |  |
| B | `set_license` | license_json | 加载并验证许可字符串，成功后保存到配置文件。 |  |
| B | `start_trial` | — | 启动试用期。使用 build_date 作为试用窗口上限防止备份攻击。 |  |
| A | `decrypt_api_key` | ciphertext | 解密 ``encrypt_api_key()`` 的输出。 |  |
| A | `encrypt_api_key` | plaintext | 加密 API Key。 |  |
| A | `get_api_key` | which | 获取解密后的 API Key。 |  |
| A | `get_license_info` | — | 获取当前许可信息。 |  |
| A | `is_active` | — | 正式许可已激活（有 ECDSA 签名）。 |  |
| A | `is_trial` | — | 是否处于试用期。 |  |
| A | `is_trial_expired` | — | 试用期是否已过期。 |  |
| A | `set_api_key` | which, plaintext | 加密并存储 API Key。 |  |
| A | `trial_remaining` | — | 试用期剩余天数。负数表示已过期。 |  |
| A | `update` | **kwargs | 批量更新配置字段并自动保存。 |  |

## data_quality

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `auto_detect_and_repair` | csv_path, output_path, k_neighbors, q25_threshold, ... | 检测+修复 CSV 文件中的 phi 损坏数据。 |  |
| A | `detect_phi_anomalies` | sections, is_aborted, q25_threshold | 检测损坏的 phi 位置。 |  |
| A | `repair_phi_interpolation` | sections, bad_phis, k_neighbors, max_search | 逆距离加权 K 近邻插值修复。 |  |

## datasource

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | base, theta_stride, phi_stride | — |  |
| C | `close` | — | — |  |
| C | `frequencies` | — | — |  |
| C | `phi_angles` | — | — |  |
| C | `read_sections` | freq_index | — |  |
| C | `theta_angles` | — | — |  |
| B | `close` | — | 释放资源（子类可覆盖）。 |  |
| A | `frequencies` | — | 频点列表 (MHz)，按文件顺序。 |  |
| A | `from_path` | path | 根据文件扩展名自动创建合适的 DataSource。 |  |
| A | `phi_angles` | — | 方位角列表 (°)。 |  |
| A | `read_sections` | freq_index | 读取单个频点的全部 section 数据。 |  |
| A | `theta_angles` | — | 俯仰角列表 (°)。 |  |

## emquest_exporter

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `export_raw_files` | file_paths, export_format, output_dir, progress_callback | 使用 EMQuest CLI 将 .raw 文件批量导出为指定格式。 |  |
| A | `discover_raw_files` | root_dir, recursive | 扫描目录下所有 .raw 文件。 |  |

## excel_reader

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `read_template` | template_path | 读取输出模板，返回所有工作表信息。 |  |
| B | `reload_column_patterns` | — | 强制重新加载 JSON 模式（对话框保存后调用）。 |  |
| A | `classify_column` | header | 统一列头分类入口。按优先级匹配所有已注册列类型。 |  |
| A | `detect_ratio_column_type` | header | 检测比率列类型，返回带 db/pct 后缀的 column type。 |  |

## exporter

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `export_results` | template_path, output_path, sheet_results, **kwargs | 基于模板填充数据 + 嵌入图片。 |  |

## file_entry

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| A | `exists` | — | 文件是否存在。 |  |
| A | `file_size_mb` | — | 文件大小 (MB)，读取失败返回 0。 |  |
| A | `infer_mode_from_headers` | headers | 根据列头列表推断测试模式。 |  |
| A | `infer_mode_from_sheet` | sheet_name | 根据工作表名称推断测试模式。 |  |
| A | `mode_name` | mode | 返回测试模式的人类可读名称。 |  |
| A | `name` | — | 短文件名，用于 GUI 显示。 |  |
| A | `stem` | — | 无扩展名的文件名。 |  |

## finalsummary_reader

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__del__` | — | — |  |
| C | `__getitem__` | key | — |  |
| C | `__init__` | maxsize | — |  |
| C | `__init__` | path | — |  |
| C | `__setitem__` | key, value | — |  |
| C | `close` | — | — |  |
| C | `frequencies` | — | — |  |
| C | `phi_angles` | — | — |  |
| C | `read_sections` | freq_index | — |  |
| C | `theta_angles` | — | — |  |
| A | `read_batch` | freq_indices | 批量读取多个频点数据 — 复用打开的 workbook, 避免重复 XML 解析。 |  |

## fs_to_csv

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `convert_fs_to_csv` | src_path, out_path, progress_callback | 将 FinalSummary .xlsx 转换为 merged CSV。 |  |

## graph_data

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| A | `downsample_pattern` | data_2d, theta_angles, phi_angles, step_deg | 将 (n_phi, n_theta) 方向图降采样到指定步进。 |  |
| A | `extend_theta_to_180` | data, theta_arr | 将截断 theta (如 0-110°) 延伸到 180°，用指数衰减填充后半球。 |  |
| A | `extract_graph_data` | results, step_deg | 从处理结果中提取每个频点的图形数据。 |  |

## help_engine

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | k1, b | — |  |
| C | `__init__` | — | — |  |
| C | `__init__` | html_path | — |  |
| C | `available` | — | — |  |
| C | `build` | chunks | — |  |
| C | `build` | chunks | — |  |
| C | `chunk_count` | — | — |  |
| C | `rag_settings` | — | — |  |
| C | `search` | query, top_k | — |  |
| C | `semantic_available` | — | — |  |
| C | `set_rag_settings` | settings | — |  |
| B | `ask` | question, top_k | LLM RAG 问答。 |  |
| B | `chunk_document` | html_path | 将 USER_GUIDE.html 按 <h2> 标签拆分为章节块。 |  |
| A | `search` | query, top_k | BM25 搜索，返回 (chunk, score) 列表。 |  |
| A | `search` | query, top_k, use_semantic | 搜索帮助文档。 |  |

## json_reader

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | path | — |  |
| C | `frequencies` | — | — |  |
| C | `num_frequencies` | — | — |  |
| C | `num_phi` | — | — |  |
| C | `num_theta` | — | — |  |
| C | `phi_angles` | — | — |  |
| C | `theta_angles` | — | — |  |
| B | `get_metadata` | — | 提取测试元数据: 方法、时间、设备、参数等。 |  |
| B | `read_sections` | freq_index | 读取指定频率的 4 个 section 数据。 |  |

## lag_config

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `add_range` | start, end | — |  |
| C | `add_single` | angle | — |  |
| C | `clear` | — | — |  |
| C | `from_dict` | cls, d | — |  |
| C | `is_empty` | — | — |  |
| C | `load_preset` | cls, path | — |  |
| C | `remove_range` | start, end | — |  |
| C | `remove_single` | angle | — |  |
| C | `save_preset` | path | — |  |
| C | `to_dict` | — | — |  |
| A | `from_ar_headers` | cls, headers | 从 Excel 列头自动解析 AR (Axial Ratio) 角度需求。 |  |
| A | `from_start_step` | cls, start, end, step | 起始+步进快速生成单角度列表。 |  |
| A | `from_template_headers` | cls, headers | 从 Excel 列头自动解析 LAG 需求。 |  |
| A | `normalize_header` | text | 统一列头格式，消除无关差异。 |  |
| A | `ranges_sorted` | — | 排序后的范围列表。 |  |
| A | `singles_sorted` | — | 去重排序后的单角度列表。 |  |

## llm_assist

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `save` | — | 保存 LLM 设置到统一配置文件。 |  |
| A | `from_qsettings` | cls | 从统一配置文件加载 LLM 设置。 |  |
| A | `suggest_file_matches` | sheet_names, data_files, current_matches, logger | 对自动匹配后仍未匹配的工作表/文件, 使用 LLM 给出建议。 |  |
| A | `suggest_template_params` | template_path, logger | 模板规则匹配检测到 <2 类型时, 调用 LLM 辅助识别。 |  |

## nf2ff.probe

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `from_calibration` | cls, cal_path | 从校准文件加载探头系数 (CSV: s, Re{R_te}, Im{R_te}, Re{R_tm}, Im{R_tm}). |  |
| A | `__init__` | r_te, r_tm | Args: |  |
| A | `apply` | n | 获取第 n 阶的探头系数 (R_te, R_tm). |  |
| A | `default` | cls | 理想电偶极子探头 (开放式波导近似). |  |
| A | `wigner_d_small` | n, m, theta_rad | Wigner d_{mn}(θ) — 坐标旋转函数，连接探头坐标系与AUT坐标系。 |  |

## nf2ff.probe_cal

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `from_file` | cls, path | 从校准文件加载系数 (CSV: probe_index, amplitude_dB, phase_deg). |  |
| B | `save` | path | 保存校准系数到文件. |  |
| A | `__init__` | cal_coeffs | Args: |  |
| A | `apply` | e_raw | 应用校准系数到原始测量数据。 |  |
| A | `apply_polarization` | e_theta, e_phi | 分别对 Theta 和 Phi 极化应用校准系数。 |  |
| A | `from_boresight` | cls, e_measured, expected_gain_dbi | 从 boresight 方向测量数据估计校准系数。 |  |

## nf2ff.transform

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | freq_mhz, radius_m, n_max, reg_alpha, ... | — |  |
| C | `n_modes` | — | — |  |
| C | `transform` | e_theta, e_phi, theta_deg, phi_deg, ... | — |  |

## nf2ff.utils

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| A | `estimate_n_max` | freq_mhz, radius_m, margin | 根据工作频率和天线外接球半径估算截断阶数 N_max. |  |
| A | `spherical_grid` | theta_deg, phi_deg | 生成球面网格坐标, 返回 (theta_mesh, phi_mesh) 弧度. |  |

## nf2ff.vector_wave

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| A | `build_vector_transfer_matrix` | theta_deg, phi_deg, n_max, k, ... | 构建矢量传输矩阵: E_measured = A · Q. |  |
| A | `synthesize_farfield_vector` | q_coeffs, theta_far_deg, phi_far_deg, n_max, ... | 从球波系数合成矢量远场 (IEEE 1720 渐近形式). |  |
| A | `vector_spherical_harmonics_theta_phi` | n, m, theta, phi | 计算矢量球谐函数的 θ 和 φ 分量。 |  |

## parser

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | path | — |  |
| C | `num_frequencies` | — | — |  |
| C | `num_phi` | — | — |  |
| C | `num_theta` | — | — |  |
| B | `close` | — | 释放缓存文件句柄。 |  |
| A | `frequencies` | — | Return list of frequency values in MHz, in file order. |  |
| A | `phi_angles` | — | Return list of phi angles in degrees. |  |
| A | `read_all_sections_for_freq` | freq_index | Read all 4 sections for a given frequency. |  |
| A | `read_section_block` | section_name, freq_index | Read one frequency block from a section. |  |
| A | `read_sections` | freq_index | DataSource 接口: 返回 ndarray 格式的数据。 |  |
| A | `theta_angles` | — | Return list of theta angles in degrees. |  |

## pipeline

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `run_pipeline` | datasource, template_path, output_path | 执行完整处理管线。 |  |
| A | `extrapolate_theta` | theta_deg, data, method | 将 Theta 范围外推到 0-180°。 |  |
| A | `run_batch_pipeline` | csv_path, template_path, output_path | 旧版 pipeline: 接受 CSV 路径，内部创建 MergedCSVParser。 |  |

## plot_config

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | — | — |  |

## plotter

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `get_renderer` | — | — |  |
| A | `generate_2d_polar_cut` | angles_deg, gain_dbi, freq_mhz | 生成 2D 极坐标切面图。 |  |
| A | `generate_2d_rectangular_cut` | angles_deg, gain_dbi, freq_mhz | 生成 2D 直角坐标切面图。 |  |
| A | `generate_3d_pattern` | theta_deg, phi_deg, gain_dbi, freq_mhz | 生成 3D 球面辐射方向图 PNG。委托给当前渲染器。 |  |
| A | `generate_all_for_frequency` | theta_deg, phi_deg, gain_dbi, freq_mhz, ... | 根据 ChartConfig 为一个频点生成所有需要的图形。 |  |
| A | `generate_azimuth_polar_cut` | phi_deg, curves, freq_mhz | 生成方位面极坐标切面图（多条 Theta 曲线叠加）。 |  |
| A | `generate_gain_vs_theta` | theta_deg, gain_dbi, freq_mhz | 生成 Gain vs Theta 2D Cartesian 线图 (θ=0-70° 峰值增益)。 |  |
| A | `set_renderer` | renderer | 切换渲染引擎。 |  |

## raw_converter

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `apply_path_loss_calibration` | input_path, rsp_h_path, rsp_v_path, output_path, ... | 对 CSV 文件应用路径损耗补偿 (RSP 校准)。 |  |
| B | `batch_check_and_convert` | file_paths, output_dir, rsp_h_path, rsp_v_path, ... | 批量检查文件格式，并将实部/虚部格式文件转换为对数域标准格式。 |  |
| B | `convert_aborted_to_normal` | input_path, output_path, progress_callback | 将实部/虚部格式 (线性域) CSV 转换为对数域标准格式。 |  |
| B | `merge_csv_files` | file_paths, output_path, rsp_h_path, rsp_v_path, ... | 合并多个分段测量 CSV 为完整 360° 覆盖文件。 |  |
| A | `batch_check_rsp_coverage` | file_paths, rsp_h, rsp_v, only_fmt | 批量检查 RSP 校准数据是否覆盖所有文件的频率范围。 |  |
| A | `extract_freq_range` | file_path | 提取 CSV 文件的频率范围 (min, max MHz)。 |  |

## renderer

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | endpoint, api_key, max_workers, timeout | — |  |
| C | `is_configured` | — | — |  |
| C | `render_2d_polar` | angles_deg, gain_dbi, freq_mhz | — |  |
| C | `render_2d_rect` | angles_deg, gain_dbi, freq_mhz | — |  |
| C | `render_3d_pattern` | theta_deg, phi_deg, gain_dbi, freq_mhz | — |  |
| C | `render_azimuth_polar` | phi_deg, curves, freq_mhz | — |  |
| C | `render_gain_vs_theta` | theta_deg, values, freq_mhz | — |  |
| B | `close` | — | 释放渲染器资源（可选覆盖）。 |  |
| B | `detect_available_renderers` | — | 检测当前环境可用的渲染器。 |  |
| B | `render_2d_polar` | angles_deg, gain_dbi, freq_mhz | 2D 极坐标切面图。 |  |
| B | `render_2d_rect` | angles_deg, gain_dbi, freq_mhz | 2D 直角坐标切面图。 |  |
| B | `render_3d_pattern` | theta_deg, phi_deg, gain_dbi, freq_mhz | EMQuest 风格 3D 球面方向图。 |  |
| B | `render_azimuth_polar` | phi_deg, curves, freq_mhz | 方位面极坐标切面图：Phi 角轴 + 多条 Theta 曲线。 |  |
| B | `render_freq_curve` | freqs, values | 渲染频点 vs 参数 Cartesian 线图 (B 类图表 Word 输出)。 |  |
| B | `render_freq_curve_dual` | freqs, v1, label1, v2, ... | 渲染双Y轴频点曲线 (B 类图表 Word 输出)。 |  |
| B | `render_gain_vs_theta` | theta_deg, values, freq_mhz | 渲染 Gain vs Theta 2D Cartesian 线图 (θ=0-70° 峰值增益)。 |  |
| A | `render_2d_polar` | angles_deg, gain_dbi, freq_mhz | 渲染 2D 极坐标切面图。 |  |
| A | `render_2d_rect` | angles_deg, gain_dbi, freq_mhz | 渲染 2D 直角坐标切面图。 |  |
| A | `render_3d_pattern` | theta_deg, phi_deg, gain_dbi, freq_mhz | 渲染 3D 球面方向图。 |  |
| A | `render_azimuth_polar` | phi_deg, curves, freq_mhz | 渲染方位面极坐标切面图。 |  |
| A | `render_gain_vs_theta` | theta_deg, values, freq_mhz | 渲染 Gain vs Theta 2D Cartesian 线图 (θ=0-70° 峰值增益)。 |  |

## report_exporter

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `export_full_report` | output_path, sheet_results | 生成完整天线指标报告。 |  |
| B | `validate_report_data` | rows, sheet_name | 验证报告数据是否符合 JSON 中定义的规则。 |  |
| A | `export_full_report_with_validation` | output_path, sheet_results, **kwargs | 生成报告 + 数据验证，返回 (success, validation_result)。 |  |

## rsp_calibration

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| A | `check_rsp_coverage` | rsp_data, file_freqs, tolerance_mhz | 检查 RSP 校准数据是否覆盖文件的频率范围。 |  |
| A | `parse_rsp_csv` | path | 解析 EMQuest 导出的 .rsp 文件第2列 (Response dB)。 |  |
| A | `parse_rsp_phase` | path | 解析 RSP 文件的 Phase 列 (Response Phase, 第3列)。 |  |

## rsp_preset_manager

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | config_path | — |  |
| C | `defaults` | — | — |  |
| C | `from_dict` | cls, d | — |  |
| C | `get_by_name` | name | — |  |
| C | `load` | — | — |  |
| C | `names` | — | — |  |
| C | `presets` | — | — |  |
| C | `save` | — | — |  |
| C | `to_dict` | — | — |  |
| B | `add_or_update` | preset | 添加或更新预设（按名称匹配）。成功返回 True。 |  |
| B | `delete` | name | 按名称删除预设。同时清除关联的默认值。成功返回 True。 |  |
| B | `set_default` | test_mode, preset_name | 设置某测试模式的默认 RSP 预设。preset_name 为 None 则清除。 |  |
| A | `get_best_match` | test_mode | 返回最匹配的预设。 |  |
| A | `get_by_test_mode` | test_mode | 返回匹配指定测试模式的预设（包括 MODE_ANY 通用预设）。 |  |
| A | `get_default` | test_mode | 获取某测试模式的默认预设名。 |  |

## scale_manager

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `factor` | cls | — |  |
| A | `apply_full_qss` | cls, window, base_qss | 拼接 base QSS + 动态缩放 QSS, 仅设到 QApplication（子控件自动继承）。 |  |
| A | `dynamic_qss` | cls | 生成完整的动态 QSS 样式表 — 所有尺寸通过 factor 计算。 |  |
| A | `init_scale_manager` | base_width | 初始化缩放管理器。在 __init__ 中调用。 |  |
| A | `resizeEvent` | event | 窗口缩放 — 防抖刷新 QSS. |  |
| A | `set_base_qss` | qss | 保存基础 QSS 并应用 (app + window)。 |  |
| A | `update` | cls, window_width | 根据窗口宽度更新缩放因子。 |  |

## sheet_file_matcher

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| A | `auto_match` | sheet_names, file_paths | 自动将工作表名称匹配到数据文件路径。 |  |
| A | `extract_key` | name | 从工作表名称或文件名中提取规范化标识键。 |  |
| A | `sanitize_sheet_name` | name, max_len | 清理字符串使其符合 Excel 工作表名规则。 |  |

## step_resampler

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `resample_merged_csv` | input_path, output_path, theta_step_deg, phi_step_deg | 将 merged CSV 重采样到指定步进。 |  |
| A | `batch_resample` | input_path, output_dir, steps | 批量重采样：对同一源文件生成多个步进的输出。 |  |

## task_package

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `load_task_package` | path | 加载 .ant 任务包，返回 task.json 内容。 |  |
| B | `next_available_filename` | directory, base_name | 生成不重复的任务包文件名。委托给 ui_utils 统一实现。 |  |
| B | `save_task_package` | output_path, task_name, data_file_paths, template_path, ... | 保存任务包到 .ant 文件。 |  |
| A | `verify_data_integrity` | task_meta | 验证任务包中的数据文件是否与原文件一致。 |  |

## template_manager

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | name, path, default_output_dir, manufacturer | — |  |
| C | `__init__` | config_path | — |  |
| C | `get_all_templates` | — | — |  |
| C | `get_templates` | manufacturer | — |  |
| C | `load` | — | — |  |
| C | `manufacturers` | — | — |  |
| C | `save` | — | — |  |
| C | `to_dict` | — | — |  |
| B | `add_template` | manufacturer, name, path, default_output_dir | 添加或更新模板预设。 |  |
| A | `generate_output_filename` | template_name | 生成输出文件名: {模板名}_{日期}_{序号}.xlsx |  |
| A | `next_available_filename` | base_dir, template_name | 在 base_dir 中查找下一个可用序号。委托给 ui_utils 统一实现。 |  |

## ui_utils

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| B | `next_available_filename` | directory, base_name, ext, mkdir, ... | 生成不重复的文件名: {name}_{YYYYMMDD}_{seq:02d}{ext} |  |
| A | `build_param_summary_text` | test_mode, required_params, extra_params, lag_config, ... | 构建天线参数摘要字符串。 |  |
| A | `merge_params_from_columns` | column_types | 从模板列类型推断需要的计算参数。 |  |

## word_reporter

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | — | — |  |
| C | `__init__` | template_path | — |  |
| C | `filled_count` | — | — |  |
| C | `has_content` | — | — |  |
| C | `template_info` | — | — |  |
| B | `insert_images_at_bookmarks` | bookmark_images, max_width_inches | 在书签位置插入图片（使用 tempfile + add_picture）。 |  |
| B | `save` | output_path | 保存填充后的文档。 |  |
| A | `fill_all` | sheet_results, single_values, bookmark_images, progress_callback | 执行全部填充操作。 |  |
| A | `fill_content_controls` | data | 按 tag 名匹配内容控件并填入值。 |  |
| A | `fill_metadata` | metadata | 填充元数据: 内容控件 + 占位符，统一入口。 |  |
| A | `fill_placeholders` | data | 搜索替换 {{variable}} 占位符。 |  |
| A | `fill_tables` | sheet_results, progress_callback | 将计算结果填入模板中的表格。 |  |
| A | `scan` | — | 扫描模板，收集所有可填入位置的信息。 |  |

## worker

| Lv | 函数 | 参数 | 说明 | 关联 |
|----|------|------|------|------|
| C | `__init__` | csv_path, template_path, output_path | — |  |
| C | `cancel` | — | — |  |
| C | `run` | — | — |  |

---
**统计**: A 级 159 · B 级 59 · C 级 98 · 共 316

> 💡 **写新函数前**：先在此目录搜索关键词，查看是否已有类似实现。
> 搜索示例：`grep -i 'axial_ratio' FUNC_CATALOG.md`