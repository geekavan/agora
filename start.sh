#!/bin/bash
# Agora Telegram Bot 本地启动脚本
# 这是一个简化版本，用于在项目目录内快速启动

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🤖 启动 Agora Telegram Bot (本地模式)..."
echo ""

# 检查 .env 文件
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "❌ 错误: .env 文件不存在！"
    echo "   请复制 .env.example 为 .env 并填写配置："
    echo "   $ cp .env.example .env"
    echo "   $ nano .env  # 编辑并填写你的 TELEGRAM_BOT_TOKEN"
    exit 1
fi

# 检查 Python 依赖
if ! python3 -c "import telegram" 2>/dev/null; then
    echo "⚠️  python-telegram-bot 未安装"
    echo "   正在安装依赖..."
    pip3 install -r requirements.txt
fi

# 使用当前目录或命令行指定的路径作为项目根目录
if [ -n "$1" ]; then
    export PROJECT_ROOT="$1"
    echo "📁 项目路径: $PROJECT_ROOT (命令行指定)"
else
    export PROJECT_ROOT="$SCRIPT_DIR"
    echo "📁 项目路径: $PROJECT_ROOT (当前目录)"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 启动Bot
cd "$SCRIPT_DIR"
python3 agora_telegram.py
