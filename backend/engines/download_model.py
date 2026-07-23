import sys
import json
import os
import traceback
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"event": "error", "error": "Thiếu tham số repo_id"}))
        return 1
    repo_id = sys.argv[1]
    print(json.dumps({"event": "start", "repo": repo_id, "message": f"Đang kết nối để tải {repo_id}..."}))
    sys.stdout.flush()

    try:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            import subprocess
            print(json.dumps({"event": "info", "repo": repo_id, "message": "Đang chuẩn bị thư viện huggingface_hub..."}))
            sys.stdout.flush()
            subprocess.run([sys.executable, "-m", "pip", "install", "huggingface_hub"], check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            from huggingface_hub import snapshot_download

        print(json.dumps({"event": "downloading", "repo": repo_id, "message": f"Đang nạp dữ liệu {repo_id} về máy..."}))
        sys.stdout.flush()

        local_path = snapshot_download(repo_id=repo_id, resume_download=True)
        print(json.dumps({"event": "completed", "repo": repo_id, "path": str(local_path), "message": f"Tải thành công model {repo_id}"}))
        sys.stdout.flush()
        return 0
    except Exception as exc:
        print(json.dumps({"event": "error", "repo": repo_id, "error": str(exc), "trace": traceback.format_exc()}))
        sys.stdout.flush()
        return 1

if __name__ == "__main__":
    sys.exit(main())
