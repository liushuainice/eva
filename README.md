# EVA — English Vocab Assistant

轻量、离线、本地化英汉词汇助手。适合阅读英文邮件、论文、文档时快速查词。

**核心理念**：不翻译整句，只列出你不认识的单词和短语（带音标 + 中文释义），迫使你自己理解句子，在真实语境中成长。

## 功能速览

- 输入英文文本 → 输出生词/短语列表（含音标、释义、词性、难度标签）
- 短语优先匹配（内置 218 条商务/学术短语，弥补 ECDICT 多词短语不足）
- 个人已知词汇表，手动增删，过滤已掌握词汇
- 完全离线，零网络请求
- 结果可输出到文件，自动命名，文件冲突自动编号
- 导出 CSV 兼容 Anki 等背词软件
- 命令行 + 可选图形界面

## 环境要求

- **Python 3.9+**（仅需标准库：sqlite3、tkinter、re、csv、argparse）
- macOS / Linux / Windows 均可

> Python 标准库已包含所有依赖，无需 `pip install`。

## 快速开始

### 1. 克隆项目

```bash
git clone <your-repo-url> eva
cd eva
```

### 2. 下载 ECDICT 词典数据库

词典来自开源项目 [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)（收录 770 万+ 词条）。

**方式 A：手动下载（推荐）**
1. 访问 https://github.com/skywind3000/ECDICT/releases
2. 下载最新的 `ecdict-sqlite-*.zip`（约 207MB）
3. 解压得到 `.db` 文件，放到本目录，重命名为 `ecdict.db`

**方式 B：脚本自动下载**
```bash
python3 init_db.py --download
```

### 3. 初始化数据库

```bash
python3 init_db.py
```

这将：
- 创建 `eva.db`，包含个人已知词汇表（预填 ~3000 个高频词）
- 创建内置短语表（218 条商务/学术常用短语）
- 词典规模：340 万词条

```bash
# 自定义词频阈值（如预填充前 5000 个常见词）
python3 init_db.py --threshold 5000

# 不预填充常见词（从空白已知词汇表开始）
python3 init_db.py --no-auto-fill

# 指定 ECDICT 数据库位置
python3 init_db.py --ecdict-db /path/to/ecdict.db
```

### 4. 开始使用

```bash
# 分析文件，结果自动保存到旁边
python3 eva.py 邮件.txt --save

# 管道输入
python3 eva.py < my_email.txt

# 图形界面
python3 eva_gui.py
```

---

## 使用示例

### 基本用法：分析邮件文件

```bash
# 从文件读取，结果打印到终端
python3 eva.py 邮件.txt

# 从文件读取，结果自动保存到 邮件_eva.txt
python3 eva.py 邮件.txt --save

# 结合词频过滤（只看 BNC 排名 > 2000 的生词）
python3 eva.py 邮件.txt --save --auto-filter 2000
```

`--save` 模式下的输出文件命名规则：

| 输入文件 | 输出文件 | 说明 |
|----------|----------|------|
| `邮件.txt` | `邮件_eva.txt` | 首次生成 |
| `邮件.txt` | `邮件_eva_1.txt` | 文件已存在，自动加序号 |
| `邮件.txt` | `邮件_eva_2.txt` | 继续递增 |

### 指定输出路径

```bash
# 显式指定输出文件（优先级高于 --save）
python3 eva.py 邮件.txt -o /path/to/result.txt

# 从管道读取，同时保存结果
python3 eva.py -o result.txt < 邮件.txt
```

### 配置文件（替代环境变量）

所有用户偏好通过 `eva_config.json` 管理，位于项目根目录。初始化时自动生成，也可手动创建：

```json
{
    "ecdict_db": "./ecdict.db",
    "eva_db": "./eva.db",
    "auto_save": false,
    "auto_filter": 0
}
```

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `ecdict_db` | 路径 | ECDICT 词典文件路径 |
| `eva_db` | 路径 | 用户数据库路径 |
| `auto_save` | bool | 设为 `true` 则文件输入默认自动保存到旁边 |
| `auto_filter` | int | 默认 BNC 过滤阈值（0=不过滤） |

**优先级**：命令行参数 > 配置文件 > 内置默认值。

```bash
# 示例：设为默认保存 + 默认过滤 2000 常见词
# 编辑 eva_config.json：
{
    "ecdict_db": "./ecdict.db",
    "eva_db": "./eva.db",
    "auto_save": true,
    "auto_filter": 2000
}

# 此后直接运行即可
python3 eva.py 邮件.txt          # → 邮件_eva.txt，自动过滤常见词
python3 eva.py 邮件.txt -o custom.txt  # -o 覆盖 auto_save
python3 eva.py 邮件.txt --auto-filter 0  # 覆盖 auto_filter
```

### 管道 / 交互输入

```bash
# 管道输入（输出到终端）
cat 邮件.txt | python3 eva.py

# 管道 + 保存到文件
cat 邮件.txt | python3 eva.py -o result.txt

# 交互模式（粘贴文本，按 Ctrl+D 结束）
python3 eva.py
```

### 过滤等级控制

```bash
# 不过滤，全靠已知词汇表
python3 eva.py 邮件.txt

# 过滤 BNC 前 1000 个最常见词
python3 eva.py 邮件.txt --auto-filter 1000

# 过滤 BNC 前 3000 词（适合中级学习者）
python3 eva.py 邮件.txt --auto-filter 3000

# 过滤 BNC 前 6000 词（只看真正的高级词汇）
python3 eva.py 邮件.txt --auto-filter 6000
```

| BNC 阈值 | 过滤范围 | 适合人群 |
|----------|----------|----------|
| 1000 | 最基础日常词汇 | 初学者 |
| 2000 | 高中水平 | 四级备考 |
| 4000 | CET-4 范围 | 六级备考 |
| 6000 | CET-6 范围 | 考研/托福/雅思 |
| 0（默认） | 不过滤 | 完全依赖个人词汇表 |

### 管理已知词汇

```bash
# 批量添加已知词汇（单词和短语都支持）
python3 eva.py --add "ubiquitous,paradigm shift,revert to"

# 移除已知词汇（让它重新出现在分析结果中）
python3 eva.py --remove "ubiquitous"

# 查看已知词汇表
python3 eva.py --list-known
```

### 导出 Anki CSV

```bash
# 分析并导出 Anki 兼容 CSV
python3 eva.py 邮件.txt --export anki_cards.csv

# 结合过滤：只导出中高级词汇
python3 eva.py 邮件.txt --export anki_cards.csv --auto-filter 2000

# 管道 + 导出
cat 邮件.txt | python3 eva.py --export anki_cards.csv
```

导出的 CSV 格式（UTF-8 BOM，Excel/Anki 可直接打开）：

| term | phonetic | translation | type | tag | collins |
|------|----------|-------------|------|-----|---------|
| ubiquitous | /juːˈbɪk.wɪ.təs/ | 无处不在的 | word | GRE | 0 |
| paradigm shift | | 范式转变 | phrase | | |

### 图形界面

```bash
python3 eva_gui.py
```

- 粘贴文本 → 点击「分析词汇」→ 表格展示结果
- 右键词汇 →「标记为已知」立即生效
-「管理已知词汇」按钮 → 查看/批量删除
-「导出 CSV」按钮 → 保存为 Anki 格式

### 完整工作流示例

```bash
# 1. 编辑 eva_config.json，设置默认行为
#    { "auto_save": true, "auto_filter": 2000 }

# 2. 分析邮件（自动保存到 工作邮件_eva.txt，且默认过滤常见词）
python3 eva.py 工作邮件.txt

# 3. 查看结果
cat 工作邮件_eva.txt

# 4. 将认识的词加入已知表
python3 eva.py --add "prompt,regarding,deliverables"

# 5. 导出不认识的词到 Anki 背诵
python3 eva.py 工作邮件.txt --export to_learn.csv

# 6. 随着词汇量增长，降低过滤阈值
python3 eva.py 工作邮件.txt --auto-filter 4000
```

---

## 词汇等级参考

| BNC 排名 | 词汇量级 | 对应考试 |
| -------- | -------- | -------- |
| 1 - 1000 | 最基础 | 初中 |
| 1001 - 2000 | 基础 | 高中 |
| 2001 - 4000 | 四级 | CET-4 |
| 4001 - 6000 | 六级 | CET-6 |
| 6001 - 8000 | 考研 | 考研 |
| 8001+ | 出国 | 托福/雅思/GRE |

`--auto-filter N` 表示「过滤掉 BNC 排名 ≤ N 的词」，即只显示排名 > N 的生词。

**建议路线**：
1. 初期 `--auto-filter 3000`，只看中等以上难度词汇
2. 逐步将认识的词加入 `known_words`
3. 随着词汇量增长，降低 `--auto-filter` 值（3000 → 2000 → 1000 → 0）
4. 最终目标：`--auto-filter 0`，完全依赖个人已知词汇表

---

## 命令行参数速查

| 参数 | 说明 |
|------|------|
| `FILE` | 输入文件路径（位置参数，可选） |
| `-o, --output FILE` | 输出结果到指定文件 |
| `--save` | 自动保存到输入文件旁边（`输入_eva.txt`） |
| `--auto-filter N` | 过滤 BNC 前 N 个常见词（0=不过滤） |
| `--export FILE` | 导出 Anki 兼容 CSV |
| `--add "w1,w2"` | 添加已知词汇（逗号分隔） |
| `--remove WORD` | 移除已知词汇 |
| `--list-known` | 列出已知词汇表 |
| `--brief` | 紧凑输出模式 |
| `--ecdict-db PATH` | 指定 ECDICT 数据库路径 |
| `--eva-db PATH` | 指定用户数据库路径 |

---

## 配置文件

所有设置集中在 `eva_config.json`（项目根目录）：

```json
{
    "ecdict_db": "./ecdict.db",
    "eva_db": "./eva.db",
    "auto_save": false,
    "auto_filter": 0
}
```

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `ecdict_db` | 路径 | ECDICT 词典文件路径（相对路径相对于项目目录） |
| `eva_db` | 路径 | 用户数据库路径 |
| `auto_save` | bool | 设为 `true` 则文件输入默认自动保存到旁边 |
| `auto_filter` | int | 默认 BNC 过滤阈值（0=不过滤，设为 2000 则默认过滤最常见 2000 词） |

修改后立即生效，无需重启终端。

---

## 项目结构

```
eva/
├── README.md           # 本文件
├── eva_config.json     # 用户配置文件
├── init_db.py          # 数据库初始化（一次性）
├── eva.py              # 核心引擎 + 命令行接口
├── eva_gui.py          # 图形界面（可选）
├── push.sh             # Git 提交推送脚本
├── ecdict.db           # ECDICT 词典（需自行下载，约 812MB，gitignore）
└── eva.db              # 个人数据库（自动生成，gitignore）
```

## 自行扩展

数据库表结构清晰，易于二次开发：

- **ECDICT 词典**（`stardict` 表，只读）：`word`, `sw`（检索键）, `phonetic`, `translation`, `pos`, `collins`, `oxford`, `bnc`, `frq`, `tag`, `exchange`, `detail`
- **已知词汇**（`known_words` 表）：`id`, `word`, `added_at`
- **内置短语**（`phrases` 表）：`id`, `phrase`, `translation` — 可直接 INSERT 补充

常见扩展方向：
- 调整 `MAX_PHRASE_LEN` 改变短语最长匹配长度
- 编辑 `_BUILTIN_PHRASES` 列表补充更多短语
- 利用 `exchange` 字段实现词形还原（respond ↔ response）
- 基于 `collins`/`oxford`/`tag` 字段做更精细的分级过滤
- 添加例句显示（ECDICT 的 `detail` 字段含丰富释义）

## License

MIT
