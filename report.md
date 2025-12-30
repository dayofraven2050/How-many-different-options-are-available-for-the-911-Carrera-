**范围与口径**
- 车型/地区：911 Carrera 基础款 9921B2，语言 zh-CN，未登录。
- 排除项：`0UB.89.24931` (PTS) 与 `0UD.89.24931` (PTSP) 固定为未选；`equipmentType=tequipment` 的售后/附件类 22 项整体剔除，不计入组合数。
- 标配处理：仅当 family 只有单一成员时将标配固定为 True。对于存在可替换成员的 family，标配视为默认值但可被其它成员取代（否则实车可行的升级轮毂等会与“标配固定 True”矛盾）。

**数据与解析**
- HAR 解析：`parse_har.py` 使用池引用解码（-7/-5→None，bool 优先于 int），导出 `data/options.csv`（245 项，去除 tequipment 后 223 项）与 `data/seeds.json`（6 个状态），`data/feasibility_from_har.json`（3 条 changeSet）。
- 选项清理：家庭互斥按 `family` 字段建模；tequipment 全部排除；价格/描述字段仅用于参考，不参与计数。

**约束建模**
- 变量：223 个可计数选项（含标配/禁止项，但 tequipment 已剔除）。PTS/PTSP 以单子句固定为 False；单成员标配以单子句固定 True。
- 互斥/必选：
  - 每个 `family` （去 tequipment）若成员>1：加入 AtMostOne。
  - 必选族（出现标配或当前默认选中的 family）：`AER, AUSSEN_FARBE, EPH, FRI, GSP, INNENAUSSTATTUNG, KMS, KSU, LEN, LSE, LSS, PGA, RAA, RAD, SIE, TKV, VOS, WSS, ZIN, ZUR`，对其成员加入 AtLeastOne。
- 规则来源：
  - HAR feasibility（3 条）。
  - 联网 probing（`probe_rules.py`，基于 `seeds[-2]` 状态，对 157 个 optionAdded 逐一调用 `feasibility-notification`，sleep 0.2s，缓存写入 `data/constraints.json`）。
  - 规则转 CNF：`optionAdded -> engineAddedOptions`，`optionAdded -> ¬removedOptions`。
- CNF：`build_cnf.py` 生成 `data/model.cnf`（223 vars, 632 clauses）与映射 `data/varmap.json`。

**计数**
- 计数器：`pysdd` 编译 SDD 后精确计数（`count.py`）。结果写入 `data/count_result.txt`。
- 最终组合数（不含 tequipment，禁用 PTS/PTSP）：  
  `10089857050288347202816384654041415680000`

**校验**
- 提供的 Porsche Codes：
  - PT2LNC34：从 porsche-code.com 抽取 96 个 codes，强制为 True 后模型可行（剩余自由变量计数 ≈ 1.30e32）。
  - PTYBQLH9：同上，集合一致，可行。
- 额外回测：用 `pycosat` 从 CNF 随机抽取 3 个可行解并请求 customer-configurator 接口，均返回 202/200（含重定向至 feasibility），未出现立即拒绝。

**文件结构**
- `parse_har.py`：HAR 解码与 options.csv / seeds.json / feasibility_from_har.json 导出。
- `probe_rules.py`：联网探测 feasibility，输出 `data/constraints.json`。
- `build_cnf.py`：生成 DIMACS、变量映射、必选族列表。
- `count.py`：SDD 精确计数。
- 数据：`data/options.csv`, `data/seeds.json`, `data/feasibility_from_har.json`, `data/constraints.json`, `data/model.cnf`, `data/varmap.json`, `data/required_families.json`, `data/count_result.txt`.

**注意与风险**
- 标配在可替换族中未硬固定为 True，以避免与实车升级/互斥规则矛盾（如标配 58X 轮毂与 59C 升级轮毂）。这可能与“标配固定 True”口径存在偏差，但否则实际可行配置会被判 UNSAT。
- 规则覆盖度：约 160 条 (S,o) 变更样本，尚可能遗漏条件互斥/依赖，组合数存在上界偏差风险。
- tequipment/附件类已全量剔除；如需计入售后产品需重新建模。
