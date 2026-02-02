#!/usr/bin/env python3
import json
import sys
import os
import urllib.request
import datetime
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/33e5b2f6-4f68-40cb-9506-795022ac1db4"

# 判断是否运行在 iTerm 中
# Codex 在 iTerm 下会自带系统通知，这里避免重复发送
def running_in_iterm():
    pid = os.getpid()

    while True:
        try:
            ppid = os.popen(f"ps -o ppid= -p {pid}").read().strip()
            if not ppid:
                return False

            pid = int(ppid)
            cmd = os.popen(f"ps -o comm= -p {pid}").read().strip()

            if "iTerm" in cmd:
                return True

            if pid == 1:
                return False
        except Exception:
            return False


def main():
    if running_in_iterm():
        return

    if len(sys.argv) < 2:
        return

    # 解析 Codex 传入的事件 JSON
    try:
        event = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        return

    cwd = event.get("cwd", "")
    project = os.path.basename(cwd)
    event_type = event.get("type", "")
    last_msg = event.get("last-assistant-message", "").strip()
    time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"""✅ Codex 通知
项目：{project}
事件：{event_type}
时间: {time}
助手最后消息：{last_msg[:20]}
"""

    payload = {
        "msg_type": "text",
        "content": {
            "text": text
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        FEISHU_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


if __name__ == "__main__":
    main()