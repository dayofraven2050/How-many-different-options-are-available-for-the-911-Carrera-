# 9921B2（zh-CN，未登录）配置组合数：规则抽取 → 约束建模 → 精确计数（N 收敛实验）

## 0. 目标（What）
- 计算：在“官网配置器规则约束”下，911 Carrera 基础款（9921B2）**可行配置总数**
- 不等于：简单乘法（颜色×轮毂×内饰×…），因为存在互斥/依赖/替换等规则
- 输出形式：一个大整数（可行配置数）

## 1. 口径与边界（Scope）
- 车型/地区/登录状态
  - 车型：9921B2
  - 语言/地区：zh-CN
  - 未登录
- 排除/剔除
  - PTS/PTSP 固定为 False：0UB.89.24931、0UD.89.24931
  - tequipment 售后/附件类 22 项剔除（不计入变量、不计入规则）
- 标配处理（避免与升级/替换冲突）
  - 仅当某 family 只有 1 个成员：标配固定 True
  - 如果 family 有替代成员：标配为默认值，但允许被替换（否则会把真实可行升级误判为不可行）

## 2. 核心思想（Idea）
- 官网不直接给“所有规则表”，但可以通过接口回答：
  - 在当前配置状态 S 下，尝试加入某选项 o，会发生什么？
- 通过大量“（S, o）探测”收集规则 → 把规则写成可计算的逻辑约束 → 精确计数满足约束的组合数

## 3. 数据输入与解析（Data In / Parse）
- 输入文件
  - configurator.porsche.com.har（HAR 抓包）
  - 配置 PDF / Porsche Code（用于校验）
- 难点：配置器 .data 返回常见“池引用 JSON”
  - 数字索引指向池数组；需解码为正常 JSON 才能提取选项结构
- 解析输出（结构化资产）
  - options.csv：选项目录（code、title、family、是否标配/默认选中、分组信息等）
  - seeds.json：HAR 中出现过的配置状态（作为探测种子）
  - feasibility_from_har.json：HAR 中已有的少量 added/removed 规则（补充材料）

## 4. Base states 生成与 N 的含义（Base States / N）
- Base state（S）定义
  - 一个“当前配置状态”：一组 option codes（通常是稳定闭包后的集合）
- N 的含义
  - N = base states 的数量（例如 N=1/10/30/100）
  - N 不是“手动配 N 台车”，而是程序生成 N 个“代表性配置状态”用于覆盖更多条件规则
- required_families（必选族）
  - 类似：外观色、轮毂、内饰等“必须选 1”的大类
- 生成策略（覆盖条件规则）
  - 每个 required family 选 K 个代表值（如 K=3）
  - pairwise 覆盖：不同必选族的代表值尽量成对出现（触发条件互斥/依赖）
  - 加入 seeds（真实默认路径）保证覆盖“官网常见基线”

## 5. 规则探测（Feasibility Probing）
- 对每个 base state S：
  - 扫描大量候选选项 o（过滤：非 tequipment、非 PTS/PTSP、按口径处理标配）
  - 发起 feasibility 请求：options=S，optionAdded=o
- 返回字段（规则信息来源）
  - engineAddedOptions：自动追加（选 o ⇒ 必须选 a）
  - removedOptions：自动移除/冲突（选 o ⇒ 不能选 r）
  - feasibleOptions / closure（如有）：稳定闭包集合（去重/校验用）
- 规则库输出
  - constraints.json：聚合所有（S, o）→ added/removed/closure 结果
- 工程要点
  - 节流（sleep）、缓存（避免重复请求）、失败请求记录（502/超时）

## 6. 约束建模（Modeling）
- 变量定义（Boolean）
  - 每个可计数选项对应一个 0/1 变量（选=1，不选=0）
  - tequipment 不建变量
  - PTS/PTSP 固定为 0（False）
  - 单成员且标配族固定为 1（True）
- 基础结构约束（来自 options.csv 的 family）
  - AtMostOne(family)：同一族最多选一个（互斥）
  - AtLeastOne(required family)：必选族至少选一个（通常与 AtMostOne 合起来 = ExactlyOne）
- 动态规则约束（来自 constraints.json）
  - o ⇒ a（自动追加依赖）
  - o ⇒ ¬r（自动移除冲突）
- 输出：CNF（布尔约束集合）
  - model.cnf（DIMACS）：全部约束编译成可计数的标准格式
  - varmap.json：选项 code ↔ 变量编号映射
  - required_families.json：必选族清单（用于复现与解释）

## 7. 精确计数（Exact Counting）
- 使用模型计数器（Model Counting）
  - 输入：model.cnf
  - 输出：满足所有约束的解的数量（精确整数）
- 结果文件
  - count_result.txt：该 N 覆盖规模下的“可行配置总数”（在当前规则覆盖下精确）

## 8. 收敛评估（Convergence）
- 为什么要做收敛
  - 规则是“探测获得的”，覆盖不全会漏掉条件规则 → 过计数（上界偏大）
- 观察指标
  - N ↑ → unique_rules ↑、cnf_clauses ↑、count ↓（通常单调收紧）
  - 若 N 继续增大时：新增规则趋近 0，count 变化很小 → 可认为“覆盖收敛”
- 本次收敛表（示例）
  - N=1：~9.42e39（rules 237，clauses 623）
  - N=10：~8.45e38（rules 1105，clauses 2811）
  - N=30：~5.10e38（rules 1363，clauses 7657）
  - N=100：~1.94e33（rules 2588，clauses 26017）
- 当前结论（基于上述表）
  - N=30→100 仍大幅下降（5.4 个数量级）→ 尚未收敛
  - 因此 N=100 的 1.94e33 是“当前规则覆盖下的精确计数”，可作为偏保守上界（真实值预计更小）

## 9. 校验与可信度（Validation）
- 用真实 Porsche Code / PDF 配置校验
  - 强制这些 codes 为 True，模型仍 SAT（可行）
- 随机抽样回放校验（可选）
  - 从 CNF 随机采样可行解，回放到官网接口
  - 若出现拒绝：说明漏规则；拒绝率可量化模型偏松程度
- 风险提示
  - 少量 HTTP 失败（502/超时）→ 局部规则缺失
  - 条件规则覆盖仍不足 → 过计数风险（上界偏大）

## 10. 文件与产物（Deliverables）
- 初始解析产物：options.csv、seeds.json、feasibility_from_har.json
- 每轮 N 的产物：runs/N*/base_states.json、constraints.json、model.cnf、count_result.txt、stats.json
- 汇总产物：convergence_table.md/csv、report_convergence.md
