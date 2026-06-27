"""
云端录音文件监听器
监听指定目录下的新录音文件和截图，自动上传到销售 AI 后端。

使用场景：
  手机 FolderSync 把录音/截图同步到阿里云 OSS → OSS挂载到服务器目录 → 本脚本监听该目录

启动：
    python cloud_recording_watcher.py --watch-dir /data/inbox --api-url http://127.0.0.1:8100
"""

import argparse
import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path

import httpx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 已处理文件的记录文件，避免重复上传
DB_PATH = Path(__file__).with_name(".cloud_watcher_db.json")


def load_processed() -> set:
    if DB_PATH.exists():
        return set(json.loads(DB_PATH.read_text(encoding="utf-8")))
    return set()


def save_processed(processed: set) -> None:
    DB_PATH.write_text(json.dumps(list(processed), ensure_ascii=False), encoding="utf-8")


def file_signature(file_path: Path) -> str:
    """用 文件名 + 大小 + 修改时间 做签名，避免重复上传"""
    stat = file_path.stat()
    return hashlib.md5(f"{file_path.name}|{stat.st_size}|{stat.st_mtime}".encode()).hexdigest()


def upload_file(file_path: Path, api_url: str, token: str, sales_username: str = "") -> bool:
    """上传单个文件到销售 AI 后端"""
    suffix = file_path.suffix.lower()
    is_audio = suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
    is_image = suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    if not is_audio and not is_image:
        return False

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")}
            data = {}
            if sales_username:
                data["sales_username"] = sales_username

            if is_audio:
                resp = httpx.post(
                    f"{api_url}/api/call-recordings",
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=300,
                )
            else:
                resp = httpx.post(
                    f"{api_url}/api/uploads",
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=300,
                )

        if resp.status_code in (200, 201):
            logger.info(f"上传成功: {file_path.name}")
            return True
        else:
            logger.warning(f"上传失败 {file_path.name}: {resp.status_code} {resp.text[:200]}")
            return False

    except Exception as e:
        logger.error(f"上传异常 {file_path.name}: {e}")
        return False


def login(api_url: str, username: str, password: str) -> str | None:
    """登录获取 token"""
    try:
        resp = httpx.post(f"{api_url}/api/auth/login", json={"username": username, "password": password}, timeout=10)
        if resp.status_code == 200:
            return resp.json()["access_token"]
        logger.error(f"登录失败: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"登录异常: {e}")
    return None


def watch_loop(watch_dir: Path, api_url: str, username: str, password: str, sales_username: str = "", interval: int = 30):
    """持续监听目录"""
    processed = load_processed()
    token = login(api_url, username, password)
    if not token:
        logger.error("启动失败，无法登录后端")
        return

    logger.info(f"开始监听目录: {watch_dir}")
    logger.info(f"API 地址: {api_url}")
    logger.info(f"轮询间隔: {interval}秒")

    while True:
        try:
            # 定期刷新 token
            if int(time.time()) % 3600 < interval:
                new_token = login(api_url, username, password)
                if new_token:
                    token = new_token

            files = sorted(watch_dir.rglob("*"), key=lambda p: p.stat().st_mtime)
            for file_path in files:
                if not file_path.is_file():
                    continue
                sig = file_signature(file_path)
                if sig in processed:
                    continue
                # 文件刚同步完可能还在写入，等 10 秒
                if time.time() - file_path.stat().st_mtime < 10:
                    continue
                if upload_file(file_path, api_url, token, sales_username):
                    processed.add(sig)
                    save_processed(processed)

            time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("监听已停止")
            break
        except Exception as e:
            logger.error(f"监听异常: {e}")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="云端录音/截图监听上传工具")
    parser.add_argument("--watch-dir", required=True, help="监听的目录路径")
    parser.add_argument("--api-url", default="http://127.0.0.1:8100", help="销售 AI 后端地址")
    parser.add_argument("--username", default="admin", help="后端登录账号")
    parser.add_argument("--password", default="admin123", help="后端登录密码")
    parser.add_argument("--sales-username", default="", help="上传归属的销售账号（不填则用admin）")
    parser.add_argument("--interval", type=int, default=30, help="轮询间隔（秒）")
    args = parser.parse_args()

    watch_dir = Path(args.watch_dir)
    if not watch_dir.exists():
        logger.error(f"监听目录不存在: {watch_dir}")
        return

    watch_loop(
        watch_dir=watch_dir,
        api_url=args.api_url,
        username=args.username,
        password=args.password,
        sales_username=args.sales_username,
        interval=args.interval,
    )


if __name__ == "__main__":
    main()
