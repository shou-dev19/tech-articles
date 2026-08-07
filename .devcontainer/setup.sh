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
# 3. Git サブモジュールの初期化
# ---------------------------------------------------------
echo "Initializing git submodules..."
git -C /workspaces/tech-articles submodule update --init --recursive

# 親を push するとき、未 push のサブモジュールコミットも一緒に push する。
# これがないと「親だけ push → 参照先コミットが誰も取得できない」状態になる。
git -C /workspaces/tech-articles config --local push.recurseSubmodules on-demand
git -C /workspaces/tech-articles config --local fetch.recurseSubmodules on-demand
# git status / git diff にサブモジュールの変更を表示させる
git -C /workspaces/tech-articles config --local status.submoduleSummary true
git -C /workspaces/tech-articles config --local diff.submodule log

# ---------------------------------------------------------
# 4. CLI ツールのインストール
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
# 5. Node のバージョン調整
# ベースイメージ (typescript-node:1-22-bookworm) の Node は 22.16.0 だが、
# @qiita/qiita-cli 1.10.0 は engines: node >=22.22.1 を要求するため入れ直す。
# NVM_SYMLINK_CURRENT=true かつ PATH が nvm の current/bin を
# /usr/local/bin より先に見るので、alias default を張れば以降のシェルにも効く。
# このスクリプト自体は非対話 bash なので /etc/bash.bashrc は読まれない。
# nvm.sh を明示的に source する必要がある。
# ---------------------------------------------------------
NODE_VERSION_REQUIRED="22.22.1"
echo "Ensuring Node ${NODE_VERSION_REQUIRED}..."
export NVM_DIR="${NVM_DIR:-/usr/local/share/nvm}"
# nvm.sh とその配下のコマンドは set -e 下で非ゼロを返すことがあるため一時的に外す
set +e
. "$NVM_DIR/nvm.sh"
nvm install "$NODE_VERSION_REQUIRED"
nvm alias default "$NODE_VERSION_REQUIRED"
nvm use "$NODE_VERSION_REQUIRED"
set -e
echo "Node version is now: $(node -v)"

# ---------------------------------------------------------
# 6. Qiita CLI の依存関係インストール
# node_modules は gitignore されているので、コンテナ再作成のたびに
# 入れ直さないと `npx qiita preview` が使えない。
# lockfile がある場合は npm ci で固定バージョンを再現する。
# ---------------------------------------------------------
echo "Installing Qiita CLI dependencies..."
if [ -f /workspaces/tech-articles/qiita-cli/package-lock.json ]; then
    npm --prefix /workspaces/tech-articles/qiita-cli ci
else
    npm --prefix /workspaces/tech-articles/qiita-cli install
fi

# ---------------------------------------------------------
# 7. シェルエイリアスの設定
# ---------------------------------------------------------
echo "alias agyyolo='agy --dangerously-skip-permissions'" >> /home/node/.bashrc
source ~/.bashrc

echo "Dev Container setup complete!"
