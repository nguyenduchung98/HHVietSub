# HHVietSub — V1 Dev

Ứng dụng desktop Electron + React với Python worker. Bản này chỉ phục vụ chạy và phát triển; chưa có cấu hình installer.

## Chạy dev

```powershell
npm install
npm run dev
```

Trên Windows có thể chạy trực tiếp `run_dev.bat`.

Python backend mặc định dùng Python 3.12 được cài bởi uv. Có thể đặt biến `DCC_PYTHON` để dùng interpreter khác.

## Kiểm tra

```powershell
pnpm test
& "$env:APPDATA\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe" backend\worker\main.py --self-test
```

## Phạm vi hiện tại

- App shell Electron theo giao diện tham chiếu.
- Python JSON-RPC worker.
- Đọc danh sách dự án CapCut từ cấu hình dự án cũ.
- Đọc Voice Library từ `D:\OmniVoice\voices` ở chế độ chỉ đọc.
- Không có CapCut TTS.
- Chưa build installer.

Hai dự án nguồn không bị sửa bởi ứng dụng mới.
