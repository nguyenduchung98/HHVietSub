# HHVietSub Studio

Ứng dụng desktop Electron + React dùng Python worker để dịch phụ đề, tạo giọng nói, đồng bộ audio/video và tạo dự án CapCut.

## Yêu cầu phát triển

- Node.js 22 trở lên.
- Python 3.12 trở lên cho worker điều phối.
- FFmpeg/FFprobe trong `PATH` nếu sử dụng chức năng đồng bộ media.
- Các engine AI cục bộ là thành phần tùy chọn và được cài riêng.

## Chạy dự án

```powershell
npm install
npm run dev
```

Có thể đặt `DCC_PYTHON` để chỉ định chính xác Python chạy worker:

```powershell
$env:DCC_PYTHON = "C:\\Python312\\python.exe"
npm run dev
```

## Cấu hình engine bên ngoài

Ứng dụng tự tìm engine trong thư mục `runtime` và một số vị trí tương thích cũ. Có thể ghi đè bằng biến môi trường:

| Biến | Thành phần |
| --- | --- |
| `HHVIETSUB_OMNIVOICE_ROOT` | Thư mục OmniVoice và voice library |
| `HHVIETSUB_VIENEU_ROOT` | Thư mục VieNeu-TTS |
| `HHVIETSUB_CAPCUT_BRIDGE_ROOT` | Thư mục bridge chứa `core/draft_engine.py` và cấu hình CapCut |

Ví dụ:

```powershell
$env:HHVIETSUB_OMNIVOICE_ROOT = "E:\\AI\\OmniVoice"
$env:HHVIETSUB_VIENEU_ROOT = "E:\\AI\\VieNeu-TTS"
$env:HHVIETSUB_CAPCUT_BRIDGE_ROOT = "E:\\Tools\\Dich_CapCut_v2"
npm run dev
```

Chạy `setup_vieneu_backend.bat` để cài VieNeu-TTS vào `runtime/VieNeu-TTS`. Chạy `setup_ffmpeg.bat` để kiểm tra hoặc cài FFmpeg trên Windows.

## Kiểm tra

```powershell
npm test
npm run build
```

Bộ `npm test` gồm typecheck frontend, Electron, unit test Python và self-test worker.

## Đóng gói Windows

```powershell
npm run package:win
```

Python worker ưu tiên runtime tại `resources/runtime/python/python.exe`, sau đó dùng `DCC_PYTHON` hoặc Python trong `PATH`. Các model/engine AI lớn không được sao chép nguyên repository phát triển vào installer; chúng cần được cài hoặc cấu hình riêng.
