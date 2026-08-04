#!/bin/bash
set -ex

echo "Starting Dev Container setup..."

# ---------------------------------------------------------
# 1. マウントしたボリュームの権限を node ユーザーに修正
# devcontainer.json の mounts で作成されたディレクトリは
# root 所有になることがあるため、ここで node に変更します
# ---------------------------------------------------------
echo "Fixing volume permissions..."
sudo chown -R node:node /home/node/.gemini
sudo chown -R node:node /home/node/.claude
sudo chown -R node:node /home/node/.codex
sudo mkdir -p /home/node/.config/gh
sudo chown -R node:node /home/node/.config/gh
sudo mkdir -p /home/node/.config/gcloud
sudo chown -R node:node /home/node/.config/gcloud

sudo apt-get update

# ---------------------------------------------------------
# 2. Git config
# ---------------------------------------------------------
if [ -z "$(git config --global user.email)" ]; then
    if [ -n "$GIT_USER_EMAIL" ]; then
        echo "Configuring global git user.email from environment..."
        git config --global user.email "$GIT_USER_EMAIL"
    else
        echo "GIT_USER_EMAIL not set, skipping git config user.email..."
    fi
fi

if [ -z "$(git config --global user.name)" ]; then
    if [ -n "$GIT_USER_NAME" ]; then
        echo "Configuring global git user.name from environment..."
        git config --global user.name "$GIT_USER_NAME"
    else
        echo "GIT_USER_NAME not set, skipping git config user.name..."
    fi
fi

# ---------------------------------------------------------
# 3. CLI ツールのインストール
# ---------------------------------------------------------
echo "Installing Antigravity CLI..."
curl -fsSL https://antigravity.google/cli/install.sh | bash

echo "Installing Claude CLI..."
if command -v claude &> /dev/null; then
    echo "Claude CLI already installed, skipping to preserve auth."
else
    curl -fsSL https://claude.ai/install.sh | bash
fi

echo "Installing Codex CLI..."
if command -v codex &> /dev/null; then
    echo "Codex CLI already installed, skipping to preserve auth."
else
    curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh
fi

# ---------------------------------------------------------
# 4. シェルエイリアスの設定
# ---------------------------------------------------------
echo "alias agyyolo='agy --dangerously-skip-permissions'" >> /home/node/.bashrc
source ~/.bashrc

echo "Dev Container setup complete!"
