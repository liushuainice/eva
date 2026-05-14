#!/usr/bin/env python3
"""
EVA GUI — 图形界面
===================
基于 tkinter 的简易图形界面，无需额外依赖。

使用：
  python3 eva_gui.py
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
import threading
import os
import sys

# 确保能导入同目录下的 eva 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eva import VocabAssistant, format_output


class EvaGUI:
    """EVA 图形界面主窗口"""

    def __init__(self):
        self.assistant = None
        self._init_assistant()

        self.root = tk.Tk()
        self.root.title("EVA — Email Vocab Assistant")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        # 样式
        self._setup_styles()
        # 布局
        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_assistant(self):
        try:
            self.assistant = VocabAssistant()
        except FileNotFoundError as e:
            messagebox.showerror("数据库错误", str(e))
            sys.exit(1)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Helvetica", 14, "bold"))
        style.configure("Status.TLabel", font=("Helvetica", 10))

    def _build_ui(self):
        # ── 顶部标题 ──
        header = ttk.Frame(self.root, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(header, text="📧 EVA — 英文邮件词汇助手",
                  style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="管理已知词汇", command=self._manage_known).pack(
            side=tk.RIGHT, padx=5)
        ttk.Button(header, text="导出 CSV", command=self._export_csv).pack(
            side=tk.RIGHT, padx=5)

        # ── 输入区域 ──
        input_frame = ttk.LabelFrame(self.root, text="输入英文文本", padding=5)
        input_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 5))

        self.input_text = scrolledtext.ScrolledText(
            input_frame, height=10, font=("Menlo", 12),
            wrap=tk.WORD, undo=True,
        )
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        # 占位提示
        self._show_placeholder()

        # ── 选项栏 ──
        opt_frame = ttk.Frame(self.root, padding=(10, 0))
        opt_frame.pack(fill=tk.X)

        ttk.Label(opt_frame, text="BNC 词频过滤：").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar(value="0")
        filter_entry = ttk.Entry(opt_frame, textvariable=self.filter_var, width=8)
        filter_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(opt_frame, text="（0=不过滤，如设 2000 则过滤最常见 2000 词）",
                  font=("Helvetica", 9)).pack(side=tk.LEFT)

        self.analyze_btn = ttk.Button(
            opt_frame, text="🔍 分析词汇", command=self._analyze,
        )
        self.analyze_btn.pack(side=tk.RIGHT, padx=5)

        # ── 结果区域 ──
        result_frame = ttk.LabelFrame(self.root, text="分析结果", padding=5)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 使用 Treeview 表格展示
        columns = ("term", "phonetic", "pos", "translation", "type", "tag")
        self.tree = ttk.Treeview(
            result_frame, columns=columns, show="headings",
            selectmode="extended",
        )
        self.tree.heading("term", text="词汇/短语", anchor=tk.W)
        self.tree.heading("phonetic", text="音标", anchor=tk.W)
        self.tree.heading("pos", text="词性", anchor=tk.CENTER)
        self.tree.heading("translation", text="中文释义", anchor=tk.W)
        self.tree.heading("type", text="类型", anchor=tk.CENTER)
        self.tree.heading("tag", text="标签", anchor=tk.CENTER)

        self.tree.column("term", width=180, minwidth=100)
        self.tree.column("phonetic", width=150, minwidth=80)
        self.tree.column("pos", width=60, minwidth=40)
        self.tree.column("translation", width=300, minwidth=150)
        self.tree.column("type", width=60, minwidth=50)
        self.tree.column("tag", width=100, minwidth=60)

        # 滚动条
        tree_scroll = ttk.Scrollbar(result_frame, orient=tk.VERTICAL,
                                    command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 右键菜单
        self.tree_menu = tk.Menu(self.root, tearoff=0)
        self.tree_menu.add_command(label="标记为已知词汇", command=self._mark_known)
        self.tree.bind("<Button-2>", self._on_right_click)   # macOS
        self.tree.bind("<Button-3>", self._on_right_click)   # Windows/Linux

        # ── 底部状态栏 ──
        status_frame = ttk.Frame(self.root, padding=(10, 5))
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_label = ttk.Label(
            status_frame,
            text=f"已知词汇：{self.assistant.count_known_words()} 个  |  就绪",
            style="Status.TLabel",
        )
        self.status_label.pack(side=tk.LEFT)

    # ── 输入框占位提示 ──

    def _show_placeholder(self):
        self.input_text.insert("1.0", "在此粘贴英文邮件内容...")
        self.input_text.config(fg="gray")
        self.input_text.bind("<FocusIn>", self._clear_placeholder)

    def _clear_placeholder(self, event):
        if self.input_text.get("1.0", "end-1c").strip() == "在此粘贴英文邮件内容...":
            self.input_text.delete("1.0", tk.END)
            self.input_text.config(fg="black")

    # ── 分析 ──

    def _analyze(self):
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text or text == "在此粘贴英文邮件内容...":
            messagebox.showwarning("提示", "请输入英文文本")
            return

        # 解析过滤阈值
        try:
            threshold = int(self.filter_var.get())
        except ValueError:
            threshold = 0

        self.analyze_btn.config(state=tk.DISABLED, text="分析中...")
        self.status_label.config(text="正在分析...")

        # 在后台线程执行，避免阻塞 UI
        def run():
            try:
                results = self.assistant.analyze(text, auto_filter_bnc=threshold)
                self.root.after(0, lambda: self._display_results(results))
            except Exception as e:
                self.root.after(0, lambda: self._show_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _display_results(self, results):
        # 清空旧结果
        for item in self.tree.get_children():
            self.tree.delete(item)

        for r in results:
            self.tree.insert("", tk.END, values=(
                r['text'],
                f"/{r['phonetic']}/" if r['phonetic'] else "",
                r.get('pos', ''),
                r['translation'],
                r['type'],
                r.get('tag', ''),
            ))

        self.analyze_btn.config(state=tk.NORMAL, text="🔍 分析词汇")
        self.status_label.config(
            text=f"已知词汇：{self.assistant.count_known_words()} 个  |  "
                 f"找到 {len(results)} 个生词/短语"
        )

    def _show_error(self, msg):
        self.analyze_btn.config(state=tk.NORMAL, text="🔍 分析词汇")
        self.status_label.config(text="分析出错")
        messagebox.showerror("错误", msg)

    # ── 右键菜单 ──

    def _on_right_click(self, event):
        try:
            self.tree.selection_set(self.tree.identify_row(event.y))
            self.tree_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tree_menu.grab_release()

    def _mark_known(self):
        """将选中的词汇标记为已知"""
        selected = self.tree.selection()
        if not selected:
            return
        count = 0
        for item_id in selected:
            values = self.tree.item(item_id, "values")
            term = values[0]
            if self.assistant.add_known_word(term):
                self.tree.delete(item_id)
                count += 1
        self.status_label.config(
            text=f"已知词汇：{self.assistant.count_known_words()} 个  |  "
                 f"已标记 {count} 个"
        )

    # ── 导出 CSV ──

    def _export_csv(self):
        children = self.tree.get_children()
        if not children:
            messagebox.showwarning("提示", "没有可导出的数据，请先分析文本")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            initialfile="eva_vocab.csv",
        )
        if not path:
            return

        # 从 treeview 收集数据
        results = []
        for item_id in children:
            values = self.tree.item(item_id, "values")
            results.append({
                'text': values[0],
                'phonetic': values[1].strip("/") if values[1] else "",
                'translation': values[3],
                'type': values[4],
                'tag': values[5],
                'collins': "",
            })

        self.assistant.export_csv(results, path)
        messagebox.showinfo("导出成功", f"已导出 {len(results)} 条记录到：\n{path}")

    # ── 管理已知词汇 ──

    def _manage_known(self):
        """弹出已知词汇管理窗口"""
        dialog = tk.Toplevel(self.root)
        dialog.title("管理已知词汇")
        dialog.geometry("500x450")
        dialog.transient(self.root)

        # 搜索和添加
        top = ttk.Frame(dialog, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="添加词汇：").pack(side=tk.LEFT)
        add_var = tk.StringVar()
        add_entry = ttk.Entry(top, textvariable=add_var, width=25)
        add_entry.pack(side=tk.LEFT, padx=5)

        def do_add():
            text = add_var.get().strip()
            if not text:
                return
            words = [w.strip() for w in text.split(",") if w.strip()]
            ok = self.assistant.add_known_words_batch(words)
            add_var.set("")
            messagebox.showinfo("提示", f"已添加 {ok} 个词汇")
            refresh_list()
            self.status_label.config(
                text=f"已知词汇：{self.assistant.count_known_words()} 个  |  就绪"
            )

        ttk.Button(top, text="添加", command=do_add).pack(side=tk.LEFT, padx=5)

        # 列表
        list_frame = ttk.Frame(dialog, padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True)

        listbox = tk.Listbox(list_frame, font=("Menlo", 11), selectmode=tk.EXTENDED)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_list():
            listbox.delete(0, tk.END)
            words = self.assistant.list_known_words(limit=1000)
            for word, _ in words:
                listbox.insert(tk.END, word)

        def do_remove():
            selected = listbox.curselection()
            if not selected:
                return
            for idx in reversed(selected):
                word = listbox.get(idx)
                self.assistant.remove_known_word(word)
            refresh_list()
            self.status_label.config(
                text=f"已知词汇：{self.assistant.count_known_words()} 个  |  就绪"
            )

        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="移除选中", command=do_remove).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=dialog.destroy).pack(
            side=tk.RIGHT, padx=5)

        refresh_list()
        add_entry.focus()

    # ── 关闭 ──

    def _on_close(self):
        if self.assistant:
            self.assistant.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = EvaGUI()
    app.run()


if __name__ == "__main__":
    main()
