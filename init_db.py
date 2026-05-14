#!/usr/bin/env python3
"""
EVA 数据库初始化脚本
────────────────────────
功能：
  1. 定位/下载 ECDICT 开源词典数据库
  2. 创建个人已知词汇表（known_words）
  3. 可选：根据词频自动预填充常见词汇

ECDICT 数据库获取方式：
  - 手动下载（推荐）：https://github.com/skywind3000/ECDICT/releases
    下载 ecdict-sqlite-*.zip，解压出 .db 文件放到本目录
  - 程序自动下载（约 200MB，耗时取决于网络）

使用：
  python3 init_db.py                          # 交互式初始化
  python3 init_db.py --ecdict-db ecdict.db    # 指定 ECDICT 数据库路径
  python3 init_db.py --no-auto-fill           # 不预填充常见词汇
"""

import sqlite3
import os
import sys
import json
import argparse

# ─── 配置 ───────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ECDICT_DB_FILENAME = "ecdict.db"
EVA_DB_FILENAME = "eva.db"

# BNC 词频阈值：排名 <= 此值的单词视为"常见词汇"，可预填充到 known_words
# BNC (British National Corpus) 排名越小越常见
# 3000 以内 ≈ 高中毕业水平词汇量
COMMON_WORD_BNC_THRESHOLD = 3000


def get_db_path(filename):
    return os.path.join(PROJECT_DIR, filename)


def check_ecdict_db(path):
    """验证 ECDICT 数据库是否存在且包含 stardict 表"""
    if not os.path.exists(path):
        return False
    try:
        conn = sqlite3.connect(path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stardict'"
        )
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except sqlite3.Error:
        return False


def init_eva_database(ecdict_db_path):
    """创建 EVA 数据库，包含 known_words 表"""
    eva_db_path = get_db_path(EVA_DB_FILENAME)

    if os.path.exists(eva_db_path):
        print(f"⚠  EVA 数据库已存在: {eva_db_path}")
        resp = input("是否重新创建？（已有数据将丢失）[y/N]: ").strip().lower()
        if resp != 'y':
            print("已取消")
            return None
        os.remove(eva_db_path)

    conn = sqlite3.connect(eva_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE known_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX idx_known_word ON known_words(word)")

    # 内置短语表（弥补 ECDICT 缺少多词短语的不足）
    conn.execute("""
        CREATE TABLE phrases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phrase TEXT NOT NULL UNIQUE,
            translation TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX idx_phrase ON phrases(phrase)")
    conn.commit()
    print(f"✓ 已创建 EVA 数据库: {eva_db_path}")
    return conn


# ECDICT 中 BNC 为 NULL/0 但实际是基础功能词的列表
_FUNCTION_WORDS = [
    'i', 'you', 'he', 'she', 'it', 'we', 'they',
    'me', 'him', 'her', 'us', 'them',
    'my', 'your', 'his', 'its', 'our', 'their',
    'a', 'an', 'the', 'this', 'that', 'these', 'those',
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'do', 'does', 'did', 'have', 'has', 'had',
    'can', 'could', 'will', 'would', 'shall', 'should',
    'may', 'might', 'must', 'not', 'no', 'yes',
    'and', 'or', 'but', 'if', 'so', 'yet',
    'at', 'in', 'on', 'to', 'of', 'from', 'with', 'by', 'as',
    'than', 'then', 'when', 'where', 'what', 'who', 'whom',
    'which', 'how', 'why', 'also', 'very', 'too', 'just',
    'only', 'some', 'any', 'many', 'much', 'more', 'most',
    'up', 'down', 'out', 'off', 'over', 'under', 'about',
    'into', 'onto', 'upon', 'after', 'before', 'between',
    'each', 'every', 'all', 'both', 'few', 'other', 'such',
    'now', 'here', 'there', 'well', 'back', 'still',
    'one', 'two', 'first', 'last', 'new', 'old', 'good', 'high',
    'get', 'make', 'know', 'think', 'take', 'see', 'come',
    'go', 'say', 'look', 'give', 'use', 'find', 'tell',
    'ask', 'try', 'leave', 'call', 'keep', 'let', 'begin',
    'seem', 'help', 'show', 'hear', 'play', 'run', 'move',
    'live', 'believe', 'hold', 'bring', 'happen', 'write',
    'provide', 'sit', 'stand', 'lose', 'pay', 'meet',
    'include', 'continue', 'set', 'learn', 'change',
    'lead', 'understand', 'watch', 'follow', 'stop',
    'create', 'speak', 'read', 'allow', 'add', 'spend',
    'grow', 'open', 'walk', 'win', 'offer', 'remember',
    'love', 'consider', 'appear', 'buy', 'wait', 'serve',
    'die', 'send', 'expect', 'build', 'stay', 'fall',
    'cut', 'reach', 'kill', 'remain', 'suggest', 'raise',
    'pass', 'sell', 'require', 'report', 'decide', 'pull',
    'thank', 'receive', 'agree', 'support', 'hit', 'produce',
    'eat', 'cover', 'catch', 'draw', 'choose',
    'today', 'tomorrow', 'yesterday', 'people', 'time',
    'year', 'way', 'day', 'man', 'woman', 'child',
    'world', 'life', 'hand', 'part', 'place', 'case',
    'week', 'company', 'system', 'program', 'question',
    'work', 'government', 'number', 'night', 'point', 'home',
    'water', 'room', 'mother', 'area', 'money', 'story',
    'fact', 'month', 'lot', 'right', 'study', 'book',
    'eye', 'job', 'word', 'business', 'issue', 'side',
    'kind', 'head', 'house', 'service', 'friend',
    'father', 'power', 'hour', 'game', 'line', 'end',
    'member', 'law', 'car', 'city', 'community',
    'name', 'president', 'team', 'minute', 'idea',
    'body', 'information', 'back', 'parent', 'face',
    'others', 'level', 'office', 'door', 'health',
    'person', 'art', 'war', 'history', 'party',
    'result', 'morning', 'reason', 'research',
    'girl', 'guy', 'moment', 'air', 'teacher',
    'force', 'education',
]


def prefill_common_words(conn, ecdict_db_path, threshold=COMMON_WORD_BNC_THRESHOLD):
    """将 ECDICT 中的高频词汇预填充到 known_words 表"""
    print(f"正在预填充常见词汇（BNC 排名 <= {threshold}）...")

    conn.execute(f"ATTACH DATABASE ? AS ecdict", (ecdict_db_path,))

    cursor = conn.execute("""
        INSERT OR IGNORE INTO known_words (word)
        SELECT LOWER(word) FROM ecdict.stardict
        WHERE bnc > 0 AND bnc <= ?
    """, (threshold,))

    count_bnc = cursor.rowcount

    # 补充基础功能词（BNC 为 NULL/0 但在 ECDICT 中有收录的常见词）
    placeholders = ','.join(['?'] * len(_FUNCTION_WORDS))
    cursor2 = conn.execute(f"""
        INSERT OR IGNORE INTO known_words (word)
        SELECT LOWER(word) FROM ecdict.stardict
        WHERE sw IN ({placeholders})
    """, _FUNCTION_WORDS)
    count_func = cursor2.rowcount

    conn.commit()
    conn.execute("DETACH DATABASE ecdict")

    total = count_bnc + count_func
    print(f"✓ 已添加 {total} 个常见词汇（BNC: {count_bnc}, 功能词: {count_func}）")
    return total


# ─── 内置短语表（弥补 ECDICT 多词短语不足） ─────

_BUILTIN_PHRASES = [
    # 商务邮件常用
    ("as soon as possible", "尽快"),
    ("as soon as practicable", "在可行的情况下尽快"),
    ("as per your request", "按照你的要求"),
    ("as per our discussion", "根据我们的讨论"),
    ("as a reminder", "温馨提示"),
    ("as discussed", "如前所述"),
    ("as follows", "如下"),
    ("as of now", "截至目前"),
    ("as a result", "因此，结果"),
    ("at your earliest convenience", "在你方便的时候尽早"),
    ("at this point", "此时，就目前而言"),
    ("at the moment", "目前，此刻"),
    ("at the same time", "同时"),
    ("at the end of the day", "说到底，最终"),
    ("on behalf of", "代表"),
    ("on the same page", "达成共识，保持一致"),
    ("on top of that", "除此之外"),
    ("on a regular basis", "定期地"),
    ("on the other hand", "另一方面"),
    ("on hold", "暂停，搁置"),
    ("on track", "在正轨上，进展顺利"),
    ("on schedule", "按计划进行"),
    ("in order to", "为了"),
    ("in terms of", "就……而言，在……方面"),
    ("in regard to", "关于"),
    ("in relation to", "关于，与……相关"),
    ("in response to", "回应，答复"),
    ("in accordance with", "根据，按照"),
    ("in addition to", "除……之外"),
    ("in advance", "提前"),
    ("in charge of", "负责，主管"),
    ("in detail", "详细地"),
    ("in due course", "在适当的时候"),
    ("in essence", "本质上"),
    ("in fact", "事实上"),
    ("in favor of", "支持，赞同"),
    ("in light of", "鉴于，考虑到"),
    ("in line with", "符合，与……一致"),
    ("in particular", "尤其，特别"),
    ("in place", "到位，就绪"),
    ("in practice", "实际上，在实践中"),
    ("in principle", "原则上"),
    ("in spite of", "尽管"),
    ("in the meantime", "与此同时"),
    ("in the long run", "从长远来看"),
    ("in the short term", "短期内"),
    ("in the loop", "知情，在圈内"),
    ("in touch", "保持联系"),
    ("in turn", "反过来，依次"),
    ("in vain", "徒劳"),
    ("in writing", "以书面形式"),
    ("with regard to", "关于，至于"),
    ("with respect to", "关于，就……而言"),
    ("with a view to", "为了，旨在"),
    ("by the way", "顺便说一下"),
    ("by means of", "通过……方式"),
    ("by no means", "绝不"),
    ("by virtue of", "由于，凭借"),
    ("for the purpose of", "为了……的目的"),
    ("for instance", "例如"),
    ("for the time being", "暂时，眼下"),
    ("for good", "永久地"),
    ("from scratch", "从头开始"),
    ("from time to time", "不时地"),
    ("out of scope", "超出范围"),
    ("out of the loop", "不知情"),
    ("out of date", "过时的"),
    ("up to date", "最新的"),
    ("up to par", "达到标准"),
    ("up to speed", "了解最新情况"),
    ("up to you", "由你决定"),
    ("under consideration", "在考虑中"),
    ("under control", "在掌控中"),
    ("under review", "在审查中"),
    ("under way", "在进行中"),
    ("follow up", "跟进"),
    ("follow up on", "跟进某事"),
    ("revert to", "回复；恢复原状"),
    ("touch base", "联系，沟通"),
    ("reach out", "联系，接触"),
    ("reach out to", "联系某人"),
    ("figure out", "弄清楚，搞明白"),
    ("point out", "指出"),
    ("point of view", "观点"),
    ("carry out", "执行，实施"),
    ("carry on", "继续"),
    ("set up", "建立，安排"),
    ("set out", "阐述，出发"),
    ("take into account", "考虑，顾及"),
    ("take into consideration", "考虑在内"),
    ("take care of", "处理，照顾"),
    ("take over", "接管"),
    ("take place", "发生"),
    ("take advantage of", "利用"),
    ("take for granted", "认为理所当然"),
    ("look forward to", "期待"),
    ("look into", "调查，研究"),
    ("look up to", "尊敬"),
    ("make sure", "确保"),
    ("make sense", "有意义，讲得通"),
    ("make a difference", "产生影响，有差别"),
    ("make up for", "弥补"),
    ("make use of", "利用"),
    ("come up with", "想出，提出"),
    ("come across", "偶然发现，给人的印象"),
    ("come into effect", "生效"),
    ("come to an end", "结束"),
    ("get back to", "回复，回到……上"),
    ("get rid of", "摆脱，去除"),
    ("get along with", "与……相处"),
    ("get in touch", "取得联系"),
    ("go through", "经历，仔细检查"),
    ("go ahead", "继续，进行"),
    ("go over", "仔细检查，复习"),
    ("go beyond", "超出"),
    ("put forward", "提出"),
    ("put off", "推迟"),
    ("put together", "组合，汇总"),
    ("put up with", "容忍"),
    ("bring up", "提出，抚养"),
    ("bring about", "引起，导致"),
    ("bring forward", "提出；提前"),
    ("turn down", "拒绝"),
    ("turn out", "结果是，证明"),
    ("turn over", "翻转；移交"),
    ("turn up", "出现"),
    ("end up", "最终，结果"),
    ("wind up", "结束，告终"),
    ("deal with", "处理，应对"),
    ("cope with", "应对，处理"),
    ("depend on", "取决于，依赖"),
    ("rely on", "依赖，依靠"),
    ("refer to", "参考，提及"),
    ("apply to", "适用于，申请"),
    ("consist of", "由……组成"),
    ("belong to", "属于"),
    ("contribute to", "贡献于，有助于"),
    ("lead to", "导致"),
    ("amount to", "相当于，总计"),
    ("adhere to", "遵守，坚持"),
    ("comply with", "遵守，符合"),
    ("correspond to", "对应于"),
    ("pertain to", "关于，涉及"),
    ("relate to", "与……有关"),
    ("stem from", "源于，由……引起"),
    ("result in", "导致，造成"),
    ("result from", "由……引起"),
    ("account for", "解释；占（比例）"),
    ("allow for", "考虑到，顾及"),
    ("call for", "需要，要求"),
    ("care for", "照顾，喜欢"),
    ("stand for", "代表，支持"),
    ("aim at", "旨在，瞄准"),
    ("arrive at", "到达；达成（结论等）"),
    ("engage in", "从事，参与"),
    ("participate in", "参与"),
    ("invest in", "投资于"),
    ("specialize in", "专攻，擅长"),
    ("succeed in", "成功做到"),
    ("benefit from", "从……中受益"),
    ("suffer from", "遭受，患……"),
    ("differ from", "区别于"),
    ("range from", "范围从……到"),
    ("a number of", "许多，若干"),
    ("a range of", "一系列，各种"),
    ("a lack of", "缺乏"),
    ("a couple of", "几个，一对"),
    ("a great deal of", "大量的"),
    ("a lot of", "许多"),
    ("a variety of", "各种各样的"),
    ("first of all", "首先"),
    ("last but not least", "最后但同样重要的是"),
    ("all in all", "总而言之"),
    ("in a nutshell", "简而言之"),
    ("in other words", "换句话说"),
    ("in summary", "总而言之"),
    ("for example", "例如"),
    ("such as", "比如，诸如"),
    ("due to", "由于"),
    ("owing to", "由于"),
    ("prior to", "在……之前"),
    ("subsequent to", "在……之后"),
    ("regardless of", "不管，无论"),
    ("according to", "根据，按照"),
    ("apart from", "除了"),
    ("except for", "除了……之外"),
    ("along with", "连同，以及"),
    ("together with", "连同，与……一起"),
    ("rather than", "而不是"),
    ("other than", "除了"),
    ("instead of", "代替，而不是"),
    ("more than", "超过，不仅仅"),
    ("less than", "少于"),
    ("no longer", "不再"),
    ("as well as", "以及，还有"),
    ("as long as", "只要"),
    ("as far as", "就……而言"),
    ("as much as", "多达"),
    ("so that", "以便，所以"),
    ("so as to", "为了"),
    ("so far", "到目前为止"),
    ("so long as", "只要"),
    ("whether or not", "无论是否"),
    ("even though", "尽管"),
    ("even if", "即使"),
    ("if so", "如果是这样"),
    ("if not", "如果不"),
    ("once again", "再一次"),
    ("over time", "随着时间的推移"),
    ("to date", "至今"),
    ("to some extent", "在某种程度上"),
    ("to the point", "中肯的，切题的"),
    ("to begin with", "首先"),
    ("next steps", "后续步骤"),
    ("action items", "待办事项"),
    ("status update", "状态更新"),
    ("tentative date", "暂定日期"),
    ("best regards", "此致敬礼（邮件落款）"),
]

_PHRASE_COUNT = len(_BUILTIN_PHRASES)


def prefill_phrases(conn):
    """预填充内置短语表"""
    print(f"正在预填充常用短语（{_PHRASE_COUNT} 条）...")
    conn.executemany(
        "INSERT OR IGNORE INTO phrases (phrase, translation) VALUES (?, ?)",
        _BUILTIN_PHRASES,
    )
    conn.commit()
    # 统计实际插入数
    count = conn.execute("SELECT COUNT(*) FROM phrases").fetchone()[0]
    print(f"✓ 短语表共 {count} 条")


def download_ecdict_auto():
    """尝试自动下载 ECDICT 数据库"""
    import urllib.request
    import zipfile

    # ECDICT 最新版本 URL（可能需要更新）
    url = "https://github.com/skywind3000/ECDICT/releases/download/1.0.1/ecdict-sqlite-28.zip"
    zip_path = get_db_path("ecdict-temp.zip")
    db_path = get_db_path(ECDICT_DB_FILENAME)

    print(f"下载地址: {url}")
    print("文件约 200MB，请耐心等待...")

    try:
        urllib.request.urlretrieve(url, zip_path, _download_progress)
        print("\n下载完成，正在解压...")

        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.db'):
                    zf.extract(name, PROJECT_DIR)
                    extracted = os.path.join(PROJECT_DIR, name)
                    if extracted != db_path:
                        os.rename(extracted, db_path)
                    print(f"✓ 数据库已解压到: {db_path}")
                    break

        os.remove(zip_path)
        print("✓ 已清理临时文件")
        return db_path

    except Exception as e:
        print(f"\n✗ 自动下载失败: {e}")
        return None


def _download_progress(block_num, block_size, total_size):
    """下载进度回调"""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100, downloaded * 100 / total_size)
        print(f"\r  下载进度: {percent:.0f}%", end='', flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="EVA 数据库初始化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 init_db.py                          # 交互式初始化
  python3 init_db.py --ecdict-db ./ecdict.db  # 指定词典路径
  python3 init_db.py --no-auto-fill           # 不预填充常见词汇
  python3 init_db.py --download               # 尝试自动下载 ECDICT
  python3 init_db.py --threshold 5000         # 自定义词频阈值
        """
    )
    parser.add_argument("--ecdict-db", help="ECDICT 数据库文件路径")
    parser.add_argument("--no-auto-fill", action="store_true", help="不预填充常见词汇")
    parser.add_argument("--threshold", type=int, default=COMMON_WORD_BNC_THRESHOLD,
                        help=f"BNC 词频阈值（默认: {COMMON_WORD_BNC_THRESHOLD}）")
    parser.add_argument("--download", action="store_true", help="尝试自动下载 ECDICT")
    args = parser.parse_args()

    print("=" * 60)
    print("  EVA - Email Vocab Assistant / 数据库初始化")
    print("=" * 60)
    print()

    # ── 第一步：定位 ECDICT 数据库 ──
    ecdict_db_path = None

    if args.ecdict_db:
        ecdict_db_path = args.ecdict_db
    else:
        # 检查默认位置
        default_path = get_db_path(ECDICT_DB_FILENAME)
        if check_ecdict_db(default_path):
            ecdict_db_path = default_path
            print(f"✓ 找到 ECDICT 数据库: {ecdict_db_path}")

    if not ecdict_db_path:
        if args.download:
            ecdict_db_path = download_ecdict_auto()

        if not ecdict_db_path or not check_ecdict_db(ecdict_db_path):
            print("\n✗ 未找到 ECDICT 数据库")
            print("\n请按以下步骤手动获取：")
            print(f"  1. 访问: https://github.com/skywind3000/ECDICT/releases")
            print(f"  2. 下载最新的 ecdict-sqlite-*.zip")
            print(f"  3. 解压 .db 文件到: {PROJECT_DIR}")
            print(f"  4. 重命名为: {ECDICT_DB_FILENAME}")
            print(f"\n或指定数据库路径:")
            print(f"  python3 init_db.py --ecdict-db /path/to/ecdict.db")
            sys.exit(1)

    # 验证数据库
    if not check_ecdict_db(ecdict_db_path):
        print(f"✗ 无效的 ECDICT 数据库: {ecdict_db_path}")
        print("  文件不包含 stardict 表，请确认是否为正确的 ECDICT 数据库")
        sys.exit(1)

    # 显示数据库信息
    conn_tmp = sqlite3.connect(ecdict_db_path)
    word_count = conn_tmp.execute("SELECT COUNT(*) FROM stardict").fetchone()[0]
    conn_tmp.close()
    print(f"  词典信息: {word_count:,} 条词条")
    print()

    # ── 第二步：创建 EVA 数据库 ──
    eva_conn = init_eva_database(ecdict_db_path)

    if eva_conn is not None:
        # ── 第三步：预填充常见词汇 ──
        if not args.no_auto_fill:
            prefill_common_words(eva_conn, ecdict_db_path, args.threshold)

        # ── 第四步：预填充常用短语 ──
        prefill_phrases(eva_conn)

        eva_conn.close()

    # ── 生成配置文件（如不存在） ──
    config_path = os.path.join(PROJECT_DIR, "eva_config.json")
    if not os.path.exists(config_path):
        default_config = {
            "ecdict_db": os.path.join(PROJECT_DIR, ECDICT_DB_FILENAME),
            "eva_db": os.path.join(PROJECT_DIR, EVA_DB_FILENAME),
            "auto_save": False,
            "auto_filter": 0,
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"\n✓ 已生成配置文件: {config_path}")

    print()
    print("=" * 60)
    print("  初始化完成！")
    print()
    print("  下一步：")
    print("    python3 eva.py              # 启动命令行工具")
    print("    python3 eva_gui.py          # 启动图形界面")
    print("    python3 eva.py --help       # 查看帮助")
    print("")
    print("  配置文件: eva_config.json")
    print("    - auto_save: true   → 文件输入默认保存到旁边")
    print("    - auto_filter: 2000 → 默认过滤 BNC 前 2000 词")
    print("=" * 60)


if __name__ == "__main__":
    main()
