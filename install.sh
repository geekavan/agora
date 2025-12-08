#!/bin/bash
# Agora 安装脚本 - 创建全局命令（无需 sudo）

# 自动检测脚本所在目录（支持任何路径）
AGORA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGORA_BIN="$AGORA_DIR/agora"

echo "🚀 安装 Agora 全局命令"
echo ""

# 检查 agora 脚本是否存在
if [ ! -f "$AGORA_BIN" ]; then
    echo "❌ 错误: agora 脚本不存在"
    echo "   路径: $AGORA_BIN"
    exit 1
fi

# 确保脚本可执行
chmod +x "$AGORA_BIN"

# 优先安装到用户目录（不需要 sudo）
USER_BIN="$HOME/.local/bin"

# 创建用户 bin 目录（如果不存在）
if [ ! -d "$USER_BIN" ]; then
    echo "📁 创建目录: $USER_BIN"
    mkdir -p "$USER_BIN"
fi

# 创建符号链接
echo "📝 创建命令链接: $USER_BIN/agora"
ln -sf "$AGORA_BIN" "$USER_BIN/agora"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 安装成功！"
    echo ""

    # 创建用户配置目录
    USER_CONFIG_DIR="$HOME/.config/agora"
    if [ ! -d "$USER_CONFIG_DIR" ]; then
        echo "📁 创建配置目录: $USER_CONFIG_DIR"
        mkdir -p "$USER_CONFIG_DIR"
    fi

    # 如果用户配置不存在，提示复制
    if [ ! -f "$USER_CONFIG_DIR/.env" ]; then
        echo ""
        echo "⚠️  请配置 Telegram Bot Token："
        echo "  cp $AGORA_DIR/.env.example $USER_CONFIG_DIR/.env"
        echo "  nano $USER_CONFIG_DIR/.env"
        echo ""
        echo "或者使用环境变量："
        echo "  export TELEGRAM_BOT_TOKEN='your_token_here'"
        echo ""
    fi

    # 检查 PATH
    if [[ ":$PATH:" == *":$USER_BIN:"* ]]; then
        echo "✅ $USER_BIN 已在 PATH 中"
        echo ""
        echo "现在你可以在任何目录运行："
        echo "  $ agora           # 使用当前目录作为项目路径"
        echo "  $ agora -h        # 查看帮助"
    else
        echo "⚠️  需要将 $USER_BIN 添加到 PATH"
        echo ""
        echo "请运行以下命令之一（根据你使用的 shell）："
        echo ""
        echo "# 如果使用 bash："
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
        echo "  source ~/.bashrc"
        echo ""
        echo "# 如果使用 zsh："
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
        echo "  source ~/.zshrc"
        echo ""
        echo "# 如果使用 fish："
        echo "  fish_add_path ~/.local/bin"
        echo ""
        echo "完成后就可以在任何目录运行 'agora' 了！"
    fi
    echo ""
    echo "📖 快速测试："
    echo "  $ cd /path/to/your/project"
    echo "  $ agora"
    echo ""
else
    echo ""
    echo "❌ 安装失败"
    echo ""
    echo "手动安装方法："
    echo "  ln -sf $AGORA_BIN $USER_BIN/agora"
    exit 1
fi
