**实验设置**
- 口径保持：车型 9921B2 zh-CN 未登录；PTS/PTSP 固定 False；tequipment 22 项剔除；标配仅在单成员 family 时固定 True；必选族与现有 required_families.json 一致。
- base states 生成：`converge_probe.py` 基于 required families 代表值 (K=3) + seeds，构造默认态并做 pairwise 覆盖；输出 runs/N*/base_states.json。
- probing：对每个 base state 扫描全部非标配、非 tequipment、非 PTS/PTSP 选项；sleep=0.2s，带缓存；失败请求跳过（N=100 时 2 条 502 报警）。
- 规则→CNF：`run_convergence.py` 聚合 probing + HAR feasibility，调用 `build_cnf.py` 与 `count.py`（pysdd 精确计数）。

**结果汇总（runs/convergence_table.md）**

|N|probed|(rules)|vars|clauses|count|log10|ratio_to_prev|delta_log10|
|-|-|-|-|-|-|-|-|
|1|204|237|223|623|9416026041864817077626169811009536000000|39.97|||
|10|1836|1105|223|2811|845027978116073327479271649705984000000|38.93|0.08974|-1.0470|
|30|3672|1363|223|7657|510003772881228748272267370797465600000|38.71|0.6035|-0.2193|
|100|11014|2588|223|26017|1941629313630751847482392576000000|33.29|3.807e-06|-5.4194|

**结论**
- 计数明显未收敛：从 N=30 到 N=100，新增规则 1225（unique_rules 1363→2588），总数急剧下降 5.4 个数量级；ratio_to_prev≈3.8e-6，仍在大幅收紧。
- 因此当前 1.94e33 依然是偏大的上界，距离官网完整规则下的真实值尚未知；需要继续扩大覆盖或改进 base state 构造。
- 风险点：N=100 有 2 个请求 502（G7、5HD 变体），相关规则缺失会进一步影响精度。

**下一步建议**
1) 提升 base state 覆盖：增大 N（200+），并提高每个 required family 的代表值 K（如 5）；对大族（车身色/内饰/轮毂涂装）可做更多组合或拉丁方覆盖。
2) 重试失败请求并引入简单重试机制；对无响应的 (S,o) 标记并单独补采。
3) 可选：对 N=100 模型做随机 SAT 采样 + 在线可行性回放，测拒绝率，进一步校验漏约束。
