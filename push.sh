#!/bin/bash
# EVA 项目提交推送脚本
# 用法：
#   ./push.sh "提交信息"              # 提交并推送
#   ./push.sh                         # 使用默认信息"update"
#   ./push.sh -a "信息"               # add 所有变更 + 提交 + 推送
#   ./push.sh -f "信息" 文件1 文件2   # 提交指定文件 + 推送

set -e

cd "$(dirname "$0")"

ADD_ALL=false
MSG=""
FILES=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--all)
            ADD_ALL=true
            shift
            ;;
        -f|--files)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                FILES+=("$1")
                shift
            done
            ;;
        *)
            MSG="$1"
            shift
            ;;
    esac
done

MSG="${MSG:-update}"

echo "📦 EVA 提交推送"
echo "   信息: $MSG"
echo ""

# 暂存文件
if $ADD_ALL; then
    echo "→ git add -A"
    git add -A
elif [[ ${#FILES[@]} -gt 0 ]]; then
    echo "→ git add ${FILES[*]}"
    git add "${FILES[@]}"
else
    # 默认：add 所有已跟踪文件的变更
    echo "→ git add -u"
    git add -u
fi

# 检查是否有内容可提交
if git diff --cached --quiet; then
    echo "⚠ 没有暂存的变更，跳过提交"
else
    echo "→ git commit"
    git commit -m "$MSG"
fi

# 推送
echo "→ git push"
git push

echo ""
echo "✓ 完成"
