#!/usr/bin/env python3
"""
EVA — English Vocab Assistant / 英汉词汇助手
=============================================
轻量、离线、本地化英汉词汇辅助工具。

核心功能：
  - 输入英文文本，自动识别生词和短语
  - 基于 ECDICT 开源词典提供音标和中文释义
  - 个人已知词汇表过滤，短语优先于单词匹配
  - 不做整句翻译，仅列出词汇，帮助自主学习

前置条件：
  python3 init_db.py          # 先初始化数据库

使用方式：
  python3 eva.py < email.txt                   # 管道输入
  python3 eva.py                               # 交互输入（Ctrl+D 结束）
  python3 eva.py --add "ubiquitous,paradigm"   # 添加已知词汇
  python3 eva.py --remove "ubiquitous"         # 移除已知词汇
  python3 eva.py --list-known                  # 查看已知词汇
  python3 eva.py --export cards.csv < mail.txt # 导出 Anki CSV
  python3 eva.py --auto-filter 2000 < mail.txt # 过滤常见词

附录：
  ECDICT: https://github.com/skywind3000/ECDICT
"""

import sqlite3
import re
import sys
import os
import csv
import json
import argparse
from typing import Optional

# ─── 路径配置 ───────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(PROJECT_DIR, "eva_config.json")
MAX_PHRASE_LEN = 6          # 短语匹配最大词数

# 默认值（配置文件不存在时使用）
_DEFAULT_CONFIG = {
    "ecdict_db": os.path.join(PROJECT_DIR, "ecdict.db"),
    "eva_db": os.path.join(PROJECT_DIR, "eva.db"),
    "auto_save": False,
    "auto_filter": 0,
}


def load_config() -> dict:
    """加载配置文件，不存在则返回默认值"""
    if not os.path.exists(CONFIG_FILE):
        return dict(_DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            user = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠ 配置文件解析失败，使用默认值：{e}", file=sys.stderr)
        return dict(_DEFAULT_CONFIG)
    # 合并：用户配置覆盖默认值
    cfg = dict(_DEFAULT_CONFIG)
    cfg.update(user)
    return cfg


# ╔══════════════════════════════════════════════════════════════╗
# ║                     VocabAssistant 核心类                     ║
# ╚══════════════════════════════════════════════════════════════╝

class VocabAssistant:
    """英文邮件词汇助手

    通过 SQLite 查询 ECDICT 词典数据，结合个人已知词汇表，
    识别文本中的生词和短语。
    """

    def __init__(self, ecdict_db=None, eva_db=None):
        cfg = load_config()
        self.ecdict_db = ecdict_db or cfg["ecdict_db"]
        self.eva_db = eva_db or cfg["eva_db"]

        # 检查 ECDICT 数据库
        if not os.path.exists(self.ecdict_db):
            raise FileNotFoundError(
                f"ECDICT 数据库未找到：{self.ecdict_db}\n"
                f"请先运行：python3 init_db.py\n"
                f"或在 eva_config.json 中配置 ecdict_db 路径"
            )

        # 主连接（用户数据）
        self.conn = sqlite3.connect(self.eva_db)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_user_tables()

        # 附加 ECDICT 词典（只读查询）
        self.conn.execute("ATTACH DATABASE ? AS ecdict", (self.ecdict_db,))

        # 内存缓存：已知词汇集合（O(1) 查找）
        self.known_words: set = set()
        self._load_known_words()

    # ── 数据库初始化 ──────────────────────────────

    def _init_user_tables(self):
        """创建用户数据表（如不存在）"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS known_words (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                word    TEXT    NOT NULL UNIQUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_known_word ON known_words(word);
            CREATE TABLE IF NOT EXISTS phrases (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                phrase      TEXT    NOT NULL UNIQUE,
                translation TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_phrase ON phrases(phrase);
        """)
        self.conn.commit()

    def _load_known_words(self):
        """将已知词汇加载到内存集合"""
        rows = self.conn.execute("SELECT word FROM known_words")
        self.known_words = {r[0].lower() for r in rows}

    # ── 已知词汇管理 ──────────────────────────────

    def add_known_word(self, word: str) -> bool:
        """添加已知词汇（单词或短语）"""
        w = word.strip().lower()
        if not w:
            return False
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO known_words (word) VALUES (?)", (w,)
            )
            self.conn.commit()
            self.known_words.add(w)
            return True
        except sqlite3.Error:
            return False

    def add_known_words_batch(self, words: list) -> int:
        """批量添加，返回成功数量"""
        return sum(1 for w in words if self.add_known_word(w))

    def remove_known_word(self, word: str):
        """移除已知词汇"""
        w = word.strip().lower()
        self.conn.execute("DELETE FROM known_words WHERE word = ?", (w,))
        self.conn.commit()
        self.known_words.discard(w)

    def list_known_words(self, limit=500, offset=0):
        """列出已知词汇"""
        return self.conn.execute(
            "SELECT word, added_at FROM known_words "
            "ORDER BY added_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()

    def count_known_words(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM known_words").fetchone()[0]

    # ── 词典查询 ──────────────────────────────────

    def _lookup(self, term: str) -> Optional[dict]:
        """在 ECDICT 或内置短语表中查询词条

        Args:
            term: 要查询的文本（如 "hello" 或 "as soon as possible"）

        Returns:
            包含 word/phonetic/translation/pos/tag/collins/bnc/frq 的字典，
            未找到返回 None
        """
        key = term.lower().strip()

        # 先查 ECDICT（单词和部分短语）
        row = self.conn.execute("""
            SELECT word, phonetic, translation, pos, collins, bnc, frq, tag
            FROM ecdict.stardict
            WHERE sw = ?
            LIMIT 1
        """, (key,)).fetchone()

        if row:
            word = row[0]
            # 清理 ECDICT 中的异常格式（如 'i 应为 I）
            if word and word.startswith("'") and len(word) > 1:
                word = word[1:]
        else:
            # 回退到内置短语表（仅对多词短语有效）
            prow = self.conn.execute("""
                SELECT phrase, translation FROM phrases WHERE phrase = ?
            """, (key,)).fetchone()
            if prow:
                return {
                    'word': prow[0], 'phonetic': '',
                    'translation': prow[1], 'pos': '',
                    'collins': 0, 'bnc': 0,
                    'frq': 0, 'tag': '',
                }
            return None
        return {
            'word': word, 'phonetic': row[1] or '',
            'translation': _clean_translation(row[2] or ''),
            'pos': _clean_pos(row[3] or ''),
            'collins': row[4] or 0, 'bnc': row[5] or 0,
            'frq': row[6] or 0, 'tag': row[7] or '',
        }

    # ── 分词 ──────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> tuple[list[str], list[int]]:
        """提取英文 token 并记录起始位置

        规则：
          - 保留缩写：don't、it's、I'm
          - 连字符拆分为独立 token：state-of-the-art → [state, of, the, art]
          - 忽略纯数字、URL、邮箱等
        """
        tokens = []
        positions = []
        for m in re.finditer(r"[a-zA-Z]+(?:'[a-zA-Z]+)*", text):
            tokens.append(m.group())
            positions.append(m.start())
        return tokens, positions

    # ── 频率过滤 ──────────────────────────────────

    @staticmethod
    def _should_filter(info: dict, bnc_threshold: int) -> bool:
        """判断词汇是否因频率过高而应被过滤"""
        if bnc_threshold <= 0:
            return False
        bnc = info.get('bnc', 0)
        return 0 < bnc <= bnc_threshold

    # ── 核心分析方法 ──────────────────────────────

    def analyze(self, text: str, auto_filter_bnc: int = 0) -> list[dict]:
        """分析文本，提取生词和短语

        算法：
          1. 分词
          2. 对每个位置，尝试匹配最长短语（6→2 词），短语优先于单词
          3. 已匹配短语内的单词不再单独检查
          4. 过滤已知词汇和高频词汇
          5. 按原文出现位置排序，去重

        Args:
            text: 英文文本
            auto_filter_bnc: BNC 频率阈值，0=不过滤

        Returns:
            list[dict]: 每项含 text/type/phonetic/translation/pos/tag/collins/bnc/position
        """
        tokens, positions = self._tokenize(text)
        n = len(tokens)
        raw_results = []
        i = 0

        while i < n:
            matched = False

            # 从长到短尝试短语匹配
            for length in range(min(MAX_PHRASE_LEN, n - i), 1, -1):
                phrase = ' '.join(tokens[i:i + length])

                if phrase.lower() in self.known_words:
                    continue  # 已知短语，跳过

                info = self._lookup(phrase)
                if info and not self._should_filter(info, auto_filter_bnc):
                    raw_results.append({
                        'text': info['word'],
                        'type': 'phrase',
                        'phonetic': info['phonetic'],
                        'translation': info['translation'],
                        'pos': info['pos'],
                        'tag': info['tag'],
                        'collins': info['collins'],
                        'bnc': info['bnc'],
                        'position': positions[i],
                    })
                    i += length
                    matched = True
                    break

            if not matched:
                word = tokens[i]
                if word.lower() not in self.known_words:
                    info = self._lookup(word)
                    # 处理缩写：'I'd'/'don't' 若整体不在词典中，尝试查词干
                    if info is None and "'" in word:
                        stem = word.split("'")[0]
                        if stem.lower() not in self.known_words:
                            info = self._lookup(stem)
                    if info and not self._should_filter(info, auto_filter_bnc):
                        raw_results.append({
                            'text': info['word'],
                            'type': 'word',
                            'phonetic': info['phonetic'],
                            'translation': info['translation'],
                            'pos': info['pos'],
                            'tag': info['tag'],
                            'collins': info['collins'],
                            'bnc': info['bnc'],
                            'position': positions[i],
                        })
                i += 1

        # 去重（保留首次出现的顺序）
        seen = set()
        results = []
        for item in raw_results:
            key = item['text'].lower()
            if key not in seen:
                seen.add(key)
                results.append(item)
        return results

    # ── CSV 导出 ──────────────────────────────────

    def export_csv(self, results: list[dict], path: str) -> str:
        """导出为 CSV，格式兼容 Anki 导入（正面=英文，背面=音标+释义）"""
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['term', 'phonetic', 'translation', 'type', 'tag', 'collins'])
            for item in results:
                w.writerow([
                    item['text'], item['phonetic'], item['translation'],
                    item['type'], item.get('tag', ''), item.get('collins', ''),
                ])
        return path

    # ── 清理 ──────────────────────────────────────

    def close(self):
        try:
            self.conn.execute("DETACH DATABASE ecdict")
        except sqlite3.Error:
            pass
        self.conn.close()


# ╔══════════════════════════════════════════════════════════════╗
# ║                     翻译清理                                 ║
# ╚══════════════════════════════════════════════════════════════╝

def _clean_pos(raw: str) -> str:
    """简化 ECDICT 词性标注：去除权重数字"""
    if not raw:
        return ""
    # n:7/j:7/v:86 → n./j./v.
    parts = re.split(r'[/\s]+', raw)
    cleaned = []
    for p in parts:
        # 去掉 :数字 部分
        abbr = re.sub(r':\d+$', '', p).strip()
        if abbr and len(abbr) <= 3:
            cleaned.append(abbr)
    return '/'.join(cleaned) if cleaned else raw


def _clean_translation(raw: str) -> str:
    """简化 ECDICT 翻译为单行摘要"""
    if not raw:
        return ""
    # 取第一义项（按换行或句号截断）
    first = raw.split("\n")[0].strip()
    # 去掉过长的词性标注前缀（如 "n:7/j:7/v:86. "）
    first = re.sub(r'^[a-z]+:\d+(?:/[a-z]+:\d+)*\.\s*', '', first)
    # 只保留前 120 字符
    if len(first) > 120:
        first = first[:120] + "..."
    return first


# ╔══════════════════════════════════════════════════════════════╗
# ║                     格式化输出                                ║
# ╚══════════════════════════════════════════════════════════════╝

def _wrap(text: str, width: int) -> list[str]:
    """按宽度折行，在空格处断开"""
    if len(text) <= width:
        return [text]
    lines = []
    remaining = text
    while len(remaining) > width:
        cut = remaining.rfind(' ', 0, width)
        if cut == -1:
            cut = width
        lines.append(remaining[:cut])
        remaining = remaining[cut:].strip()
    if remaining:
        lines.append(remaining)
    return lines


def format_output(text: str, results: list[dict]) -> str:
    """格式化结果为终端可读文本"""
    W = 70
    sep = "─" * W
    out = []

    out.append("")
    out.append("📧 原文：")
    out.append(sep)
    preview = text if len(text) <= 500 else text[:500] + "..."
    out.append(preview.strip())
    out.append("")

    if not results:
        out.append("✅ 未发现生词/短语。")
        return "\n".join(out)

    out.append(f"📋 生词 / 短语  (共 {len(results)} 个)：")
    out.append(sep)
    out.append("")

    for idx, item in enumerate(results, 1):
        term = item['text']
        phonetic = f"/{item['phonetic']}/" if item['phonetic'] else ""
        pos = f"{item['pos']}." if item['pos'] else ""
        tag = f"[{item['tag']}]" if item.get('tag') else ""
        is_phrase = "[短语]" if item['type'] == 'phrase' else ""
        translation = item['translation']

        # 第一行：词汇 + 音标 + 词性 + 标签
        line = f"{idx:3d}. {term}"
        extras = "  ".join(x for x in [phonetic, pos, tag, is_phrase] if x)
        if extras:
            line += "  " + extras
        out.append(line)

        # 后续行：释义（缩进）
        indent = "     "
        for tl in _wrap(translation, W - 5):
            out.append(f"{indent}{tl}")
        out.append("")

    out.append(sep)
    out.append("💡 提示：")
    out.append("   添加已知词汇:  eva.py --add \"word1, phrase two\"")
    out.append("   导出 Anki CSV: eva.py --export cards.csv < mail.txt")
    out.append("   高频词过滤:    eva.py --auto-filter 2000 < mail.txt")
    out.append("")
    return "\n".join(out)


def format_brief(results: list[dict]) -> str:
    """紧凑格式输出（用于 CSV 导出后的摘要）"""
    if not results:
        return ""
    width_term = max(len(r['text']) for r in results) + 2
    lines = []
    for item in results:
        term = item['text'].ljust(width_term)
        lines.append(f"  {term}{item['translation']}")
    return "\n".join(lines)


# ╔══════════════════════════════════════════════════════════════╗
# ║                     文件输出辅助                              ║
# ╚══════════════════════════════════════════════════════════════╝

def _gen_output_path(input_path: str, suffix: str = "_eva") -> str:
    """根据输入文件路径生成输出路径，已存在则自动加序号

    例：
      邮件.txt   →  邮件_eva.txt
      邮件.txt   →  邮件_eva_1.txt  （当 _eva.txt 已存在时）
    """
    dir_name = os.path.dirname(input_path) or "."
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    candidate = os.path.join(dir_name, f"{base_name}{suffix}.txt")

    if not os.path.exists(candidate):
        return candidate

    i = 1
    while True:
        candidate = os.path.join(dir_name, f"{base_name}{suffix}_{i}.txt")
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _write_output(path: str, content: str):
    """写入文件并打印确认"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✓ 结果已保存到：{path}", file=sys.stderr)


# ╔══════════════════════════════════════════════════════════════╗
# ║                       命令行入口                              ║
# ╚══════════════════════════════════════════════════════════════╝

def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(
        description="EVA — Email Vocab Assistant / 英文邮件词汇助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 从文件读取，结果自动保存到旁边
  python3 eva.py 邮件.txt

  # 从文件读取，指定输出路径
  python3 eva.py 邮件.txt -o result.txt

  # 管道输入，显式指定输出文件
  python3 eva.py -o result.txt < 邮件.txt

  # 交互模式（粘贴文本，Ctrl+D 结束）
  python3 eva.py

  # 过滤常见词 + 自动保存
  python3 eva.py 邮件.txt --auto-filter 2000

  # 导出 Anki CSV
  python3 eva.py 邮件.txt --export cards.csv

  # 管理已知词汇
  python3 eva.py --add "ubiquitous,paradigm shift"
  python3 eva.py --remove "ubiquitous"
  python3 eva.py --list-known
        """,
    )
    # 输入文件（位置参数）
    parser.add_argument(
        "input", nargs="?", metavar="FILE",
        help="输入文件路径；省略则从标准输入读取"
    )
    # 输出选项
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="将分析结果写入指定文件（默认输出到终端）"
    )
    parser.add_argument(
        "--save", action="store_true",
        help="将结果自动保存到输入文件旁边（如 邮件.txt → 邮件_eva.txt）"
    )
    # 管理模式
    parser.add_argument("--add", help="添加已知词汇，多个用逗号分隔")
    parser.add_argument("--remove", help="移除已知词汇")
    parser.add_argument("--list-known", action="store_true", help="列出已知词汇表")
    # 分析选项
    parser.add_argument("--export", metavar="FILE", help="导出结果到 CSV 文件（兼容 Anki）")
    parser.add_argument("--auto-filter", type=int, default=cfg["auto_filter"], metavar="N",
                        help=f"自动过滤 BNC 排名前 N 的常见词（默认: {cfg['auto_filter']}，0=不过滤）")
    # 其他
    parser.add_argument("--ecdict-db", help="ECDICT 数据库路径（覆盖配置文件）")
    parser.add_argument("--eva-db", help="EVA 数据库路径（覆盖配置文件）")
    parser.add_argument("--brief", action="store_true", help="紧凑输出模式")
    args = parser.parse_args()

    # 创建助手实例（CLI 参数优先于配置文件）
    try:
        assistant = VocabAssistant(
            ecdict_db=args.ecdict_db or None,
            eva_db=args.eva_db or None,
        )
    except FileNotFoundError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)

    # ── 管理模式 ──
    if args.add:
        words = [w.strip() for w in args.add.split(",") if w.strip()]
        ok = assistant.add_known_words_batch(words)
        print(f"✓ 已添加 {ok} 个词汇"
              + (f"（{len(words) - ok} 个已存在）" if ok < len(words) else ""))
        assistant.close()
        return

    if args.remove:
        assistant.remove_known_word(args.remove)
        print(f"✓ 已移除：{args.remove}")
        assistant.close()
        return

    if args.list_known:
        total = assistant.count_known_words()
        print(f"已知词汇列表（共 {total} 个，显示最近 500 条）：")
        print("-" * 45)
        for word, added_at in assistant.list_known_words(limit=500):
            print(f"  {word}")
        assistant.close()
        return

    # ── 读取输入 ──
    if args.input:
        # 从文件读取
        if not os.path.exists(args.input):
            print(f"错误：文件不存在 — {args.input}", file=sys.stderr)
            assistant.close()
            sys.exit(1)
        with open(args.input, 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        # 从标准输入读取
        if sys.stdin.isatty():
            print("📧 EVA — Email Vocab Assistant")
            print("   请粘贴英文文本，然后按 Ctrl+D 结束输入")
            print("   输入 eva.py --help 查看全部选项")
            print()
        text = sys.stdin.read()

    if not text.strip():
        print("错误：未接收到输入文本", file=sys.stderr)
        assistant.close()
        sys.exit(1)

    # ── 分析 ──
    results = assistant.analyze(text, auto_filter_bnc=args.auto_filter)

    # ── 决定输出目标 ──
    output_path = args.output  # -o 显式指定

    if not output_path and args.save and args.input:
        # --save 模式：保存到输入文件旁边
        output_path = _gen_output_path(args.input)

    if not output_path and not args.output and args.input and not args.export \
       and not args.brief and cfg.get("auto_save"):
        # 配置文件中 auto_save=true 时，默认启用自动保存
        output_path = _gen_output_path(args.input)

    # ── 输出结果 ──
    if args.export:
        path = assistant.export_csv(results, args.export)
        print(f"✓ CSV 已导出到：{path}  （{len(results)} 条记录）")
        if results:
            print()
            print(format_brief(results))

    elif output_path:
        # 写入文件
        formatted = format_output(text, results)
        _write_output(output_path, formatted)
        # 同时在终端显示简要结果
        if results:
            print(format_brief(results))
        else:
            print("✅ 未发现生词/短语。")

    elif args.brief:
        print(format_brief(results))

    else:
        print(format_output(text, results))

    assistant.close()


if __name__ == "__main__":
    main()
