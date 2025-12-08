#!/bin/bash
# Agora 安装脚本 - 创建全局命令

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

# 创建符号链接
echo "📝 创建全局命令（需要输入密码）..."
sudo ln -sf "$AGORA_BIN" /usr/local/bin/agora

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 安装成功！"
    echo ""
    echo "现在你可以在任何目录运行："
    echo "  $ agora           # 使用当前目录作为项目路径"
    echo "  $ agora -h        # 查看帮助"
    echo ""
    echo "测试命令："
    echo "  $ cd /path/to/your/project"
    echo "  $ agora"
    echo ""
else
    echo ""
    echo "❌ 安装失败"
    echo ""
    echo "手动安装方法："
    echo "  sudo ln -sf $AGORA_BIN /usr/local/bin/agora"
    exit 1
fi
