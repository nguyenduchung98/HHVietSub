# HHVietSub Lite

Phiên bản tinh gọn dành cho máy yếu, phát triển độc lập trên nhánh
`codex/lite`.

## Chức năng giữ lại

- CapCut TTS, xử lý một file hoặc hàng chờ thư mục SRT.
- Từ điển phát âm: thêm, sửa, xóa, nhập và xuất.
- Đồng bộ video bằng FFmpeg.
- Chỉnh sửa dự án CapCut đã có.

## Cấu hình đồng bộ

- **Máy yếu:** CPU x264, nhóm 6 cụm, ưu tiên ít RAM và ổn định.
- **Cân bằng:** tự chọn GPU, nhóm 12 cụm.
- **Máy mạnh:** tự chọn GPU, nhóm 24 cụm để tăng tốc.

FFmpeg xử lý tuần tự từng đoạn để tránh tăng RAM đột biến. Nếu một đoạn không
ổn định, tiến trình chuyển sang render an toàn và giữ các đoạn đã hoàn tất.

## Khác biệt với bản đầy đủ

- Không OmniVoice hoặc VieNeu local GPU.
- Không Gemini/Chrome automation.
- Không tải hoặc đóng gói model AI, runtime GPU và thư viện Python nặng.
- Không tạo dự án CapCut mới; chỉ chỉnh sửa dự án đã có.
- App ID: `com.hhvietsub.lite`.
- Dữ liệu và cache: `%LOCALAPPDATA%\HHVietSub Lite`.
