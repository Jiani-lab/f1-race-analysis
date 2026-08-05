#!/usr/bin/env bash
# One-time onboarding for a new local install. Covers everything that CAN
# be automated (deps, VAPID keys, .env scaffolding); for the handful of
# steps that genuinely can't be (Luci itself, a Voyage signup, the
# browser's own notification-permission prompt), it explains exactly what
# to do and pauses instead of silently skipping. Safe to re-run any time --
# every step checks what's already in .env before touching it.
#
# See .env.example for what each variable is and why setup.sh either can
# or can't fill it in for you.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

step() { printf "\n${BOLD}== %s ==${RESET}\n" "$1"; }
note() { printf "${DIM}%s${RESET}\n" "$1"; }

# --env-var-file helpers -----------------------------------------------
# .env is a flat KEY=VALUE file (python-dotenv reads it, see backend/*.py's
# load_dotenv() calls). These upsert one key at a time without disturbing
# the rest of the file or duplicating a key across re-runs.

env_get() {
  # $1 = key. Prints current value (empty if unset or file missing).
  [ -f .env ] || { echo ""; return; }
  grep -m1 "^$1=" .env | cut -d= -f2- || true
}

env_set() {
  # $1 = key, $2 = value.
  touch .env
  if grep -q "^$1=" .env; then
    # BSD sed (macOS default) needs the '' after -i; GNU sed doesn't care
    # for an empty backup suffix either way, so this works on both.
    sed -i '' "s|^$1=.*|$1=$2|" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

interactive() { [ -t 0 ]; }

# 1. Python deps -----------------------------------------------------------
step "Python 依赖"
if ! command -v uv >/dev/null 2>&1; then
  echo "没找到 uv。先装它：https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
uv sync
echo "装好了。"

# 2. .env scaffold ----------------------------------------------------------
step ".env"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "已从 .env.example 创建 .env。"
else
  echo "已存在，不覆盖，接下来只补缺的字段。"
fi

# 3. Luci connectivity -------------------------------------------------------
step "Luci"
LUCI_URL="$(env_get LUCI_MCP_URL)"
if [ -z "$LUCI_URL" ]; then
  LUCI_URL="http://127.0.0.1:8765/mcp"
  env_set LUCI_MCP_URL "$LUCI_URL"
fi
LUCI_TOKEN="$(env_get LUCI_MCP_TOKEN)"
if [ -z "$LUCI_TOKEN" ]; then
  note "Luci 必须先在这台机器上装好并跑起来（screen capture + OCR + ASR），没有远程/托管模式——"
  note "这一步没法帮你自动装。bearer token 在 Luci 自己的设置里找。"
  if interactive; then
    read -r -p "把 token 粘贴在这里（不确定的话先回车跳过，之后手动填 .env 里的 LUCI_MCP_TOKEN）： " LUCI_TOKEN
  fi
  if [ -n "$LUCI_TOKEN" ]; then
    env_set LUCI_MCP_TOKEN "$LUCI_TOKEN"
  else
    echo "先跳过——RAG chat/dashboard 能跑，但检测不到直播、抓不到数据，装好 Luci 后记得回来补上。"
  fi
fi
if [ -n "$LUCI_TOKEN" ]; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "$LUCI_URL" || echo "000")"
  if [ "$CODE" = "000" ]; then
    echo "连不上 $LUCI_URL——Luci 现在没在跑，或者端口不对。先把 Luci 打开，稍后重跑这个脚本或直接启动网站都行。"
  else
    echo "$LUCI_URL 有响应（HTTP $CODE），说明 Luci 在跑，端口通。"
  fi
fi

# 4. VAPID keys (web push) ---------------------------------------------------
step "Web Push (VAPID)"
if [ -n "$(env_get VAPID_PRIVATE_KEY_B64)" ] && [ -n "$(env_get VAPID_PUBLIC_KEY_B64)" ]; then
  echo "已经有一对了，跳过。"
else
  # Generate the raw base64url-encoded EC P-256 scalar/point pair directly
  # -- deliberately NOT going through `vapid --gen`'s PEM files. push.py's
  # own comment documents the real bug this avoids: py_vapid's
  # Vapid.from_string() wants the raw base64url scalar, not a PEM blob,
  # and hand-converting PEM->raw after the fact is just extra room to get
  # it wrong. Generating in the same raw form we need sidesteps that.
  VAPID_PAIR="$(uv run python3 -c "
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import base64
key = ec.generate_private_key(ec.SECP256R1())
priv = key.private_numbers().private_value
priv_b64 = base64.urlsafe_b64encode(priv.to_bytes(32, 'big')).rstrip(b'=').decode()
pub_bytes = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode()
print(f'{priv_b64} {pub_b64}')
")"
  read -r VAPID_PRIV VAPID_PUB <<< "$VAPID_PAIR"
  env_set VAPID_PRIVATE_KEY_B64 "$VAPID_PRIV"
  env_set VAPID_PUBLIC_KEY_B64 "$VAPID_PUB"
  echo "生成好了，已写入 .env。"
fi
if [ -z "$(env_get VAPID_SUBJECT)" ]; then
  SUBJECT_EMAIL=""
  if interactive; then
    read -r -p "留一个邮箱作为推送发送方标识（浏览器只在你的推送被滥用举报时才会用它联系你，随便填一个真实能收到信的地址即可）： " SUBJECT_EMAIL
  fi
  [ -z "$SUBJECT_EMAIL" ] && SUBJECT_EMAIL="you@example.com"
  env_set VAPID_SUBJECT "mailto:$SUBJECT_EMAIL"
fi

# 5. Voyage API key (RAG chatbot) --------------------------------------------
step "RAG Chatbot (Voyage)"
if [ -n "$(env_get VOYAGE_API_KEY)" ]; then
  echo "已经配了，跳过。"
elif interactive; then
  echo "可选功能——不配也能用，chatbot 会退化成纯联网搜索模式（不能针对这场比赛已抓到的具体事件回答）。"
  echo "  1) 用邀请你的人给的共享项目 key"
  echo "  2) 自己注册一个免费 key（https://dashboard.voyageai.com/）"
  echo "  3) 先跳过"
  read -r -p "选一个 [1/2/3，默认3]： " VOYAGE_CHOICE
  case "$VOYAGE_CHOICE" in
    1)
      read -r -p "粘贴共享 key： " VOYAGE_KEY
      if [ -n "$VOYAGE_KEY" ]; then
        env_set VOYAGE_API_KEY "$VOYAGE_KEY"
        env_set VOYAGE_KEY_SHARED "true"
        echo "配好了。这是共享 key，有额度上限，用完会自动降级成联网模式并提示你换成自己的 key。"
      fi
      ;;
    2)
      read -r -p "粘贴你自己的 key： " VOYAGE_KEY
      if [ -n "$VOYAGE_KEY" ]; then
        env_set VOYAGE_API_KEY "$VOYAGE_KEY"
        env_set VOYAGE_KEY_SHARED "false"
        echo "配好了，自己的 key 没有这个项目设的用量上限。"
      fi
      ;;
    *)
      echo "先跳过，之后随时可以在 .env 里补 VOYAGE_API_KEY。"
      ;;
  esac
else
  echo "非交互模式，跳过——之后随时可以在 .env 里补 VOYAGE_API_KEY（见 .env.example 的说明）。"
fi

# 6. What's left ---------------------------------------------------------
step "最后一步（没法脚本化，浏览器安全机制要求真人点一下）"
note "启动网站后，打开首页会有一个「开启比赛提醒」的按钮——点一下、浏览器会弹出通知权限"
note "请求，同意就行。这一步只需要做一次，之后不用再管。"

step "启动"
echo "一切就绪，运行："
echo ""
echo "  uv run uvicorn app:app --app-dir backend --reload --port 8800"
echo ""
echo "然后打开 http://127.0.0.1:8800"
