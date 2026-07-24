# HHVietSub Lite — Redesign Notes

## 1. Phạm vi đã khóa

Phase 0 chỉ khảo sát, chưa refactor UI hoặc thay đổi logic xử lý.

Các chức năng phải được giữ nguyên xuyên suốt redesign:

- CapCut TTS nội bộ, Hugging Face Space và chế độ kết hợp.
- AI33 API và AIMax API, bao gồm nhiều API key.
- Hàng chờ một file hoặc cả thư mục SRT.
- Từ điển phát âm, nhập/xuất JSON.
- Job đã lưu, pause/resume/cancel/retry.
- FFmpeg đồng bộ video, không ghép audio trong bản Lite.
- Chỉnh sửa dự án CapCut có sẵn.

Không đưa trở lại Gemini, OmniVoice, VieNeu hoặc tạo dự án CapCut mới.

## 2. Stack và entry point

| Lớp | Công nghệ | Entry point |
| --- | --- | --- |
| Desktop shell | Electron + TypeScript | `electron/main.ts` |
| IPC bridge | Electron preload | `electron/preload.ts` |
| Frontend | React + TypeScript + Vite | `src/main.tsx`, `src/App.tsx` |
| Styling | CSS thuần, nhiều file theo tính năng | `src/styles.css`, `src/srt-voice-v1.css`, `src/capcut-project-v1.css` |
| Backend | Python JSON-RPC qua stdio | `backend/worker/main.py` |
| Services | Python | `backend/services/*` |
| Media engines | Python + FFmpeg/CapCut | `backend/engines/*` |

Luồng runtime:

1. Electron tạo cửa sổ và khởi động Python worker.
2. React gọi `window.desktop.request(...)` qua preload.
3. Electron kiểm tra allowlist RPC rồi chuyển request xuống worker.
4. Worker phát sự kiện tiến trình ngược lên React qua IPC.

## 3. Cấu trúc UI hiện tại

### Khung ứng dụng

`App` giữ tab chính:

- `srt`: màn tạo voice.
- `capcut`: màn FFmpeg và chỉnh dự án CapCut.

Header, điều hướng và toàn bộ các màn hình hiện vẫn nằm chung trong
`src/App.tsx`.

### Tạo voice SRT

Component `SrtVoicePage` quản lý:

- Chọn engine CapCut/AI33/AIMax.
- Chọn file hoặc quét thư mục SRT.
- Thư viện giọng dạng modal.
- API key dạng modal.
- Từ điển phát âm dạng modal.
- Hàng chờ nhiều file.
- Job đã lưu.
- Bảng cue và trạng thái từng cue.
- Progress, pause/resume/cancel/retry.

### Đồng bộ

`FfmpegAndCapCutTab` quản lý:

- Video, SRT, thư mục voice, thư mục xuất.
- Tốc độ voice, đổi cao độ.
- Cấu hình máy và encoder.
- Validate input, progress và log FFmpeg.
- Bản Lite luôn gửi `mergeAudio: false`.

`CapCutProjectPage` quản lý:

- Sub-tab FFmpeg/CapCut.
- Danh sách dự án CapCut có sẵn.
- Validate và đồng bộ voice vào dự án.

## 4. Bản đồ state quan trọng

### App

- `page`: tab chính.
- `online`: trạng thái backend.
- `srtDraft`: dữ liệu chuyển sang màn tạo voice.

### SrtVoicePage

Nguồn và giọng:

- `engine`, `apiProvider`, `apiModel`, `apiVoiceId`.
- `apiVoices`, `voiceLibraryOpen`, `voiceLibraryLoading`.
- `subtitleLanguage`, `speed`.
- `capcutBackend`.

Hiệu năng API:

- `apiWorkers`.
- `apiRequestInterval`.
- `autoRetry`.

Input và hàng chờ:

- `draft`, `queue`, `queueRunning`.
- `outputDir`.
- `pronunciationDictionary`, `dictionaryOpen`.

Job và tiến trình:

- `running`, `activeJobId`, `jobState`.
- `progress`.
- `savedJobs`, `selectedJobId`, `jobPickerOpen`.
- `message`, `audioUrl`, `previewUrl`.

API key:

- `ai33Key`, `aimaxKey`.
- `apiKeyStatus`, `apiKeyBusy`, `apiSettingsOpen`.

### FfmpegAndCapCutTab

- `videoPath`, `srtPath`, `voiceDir`, `outputDir`.
- `voiceSpeed`, `changePitch`.
- `renderProfile`, `encoder`, `jobName`.
- `analysis`, `running`, `progressPercent`, `logs`, `result`, `message`.

### CapCutProjectPage

- `subtab`, `mode`.
- `projects`, `projectPath`.
- `videoPath`, `srtPath`, `voiceDir`.
- `analysis`, `running`, `logs`, `result`, `message`.

## 5. CSS hiện tại

CSS đang phân tán:

- `styles.css`: shell, header và style cũ dùng chung.
- `srt-voice-v1.css`: màn voice, queue, modal, bảng cue.
- `capcut-project-v1.css`: FFmpeg và CapCut.
- `capcut-sync.css`: phần CapCut bổ sung.
- Nhiều file `studio-*`, `translate-*`, `voice-*` vẫn còn dù màn hình Lite
  không sử dụng.

Design token hiện mới được thêm trực tiếp vào cuối `styles.css` với prefix
`--lite-*`; chưa có theme module độc lập hoặc dark mode.

## 6. Nợ kỹ thuật và rủi ro refactor

### Rủi ro cao

1. `src/App.tsx` hơn 1.000 dòng, chứa cả component Lite và component cũ đã
   không còn điều hướng tới.
2. Type `Page` vẫn chứa `studio`, `translate`, `settings`; nhiều state và
   component dead-code vẫn được TypeScript biên dịch.
3. `backend/worker/main.py` còn nhiều method OmniVoice/VieNeu/Gemini/Studio
   không có trong route allowlist. Một số method tham chiếu service đã xóa.
4. CSS dùng nhiều override nối tiếp và selector theo vị trí như
   `nth-child`; thay thứ tự JSX có thể làm ẩn sai card.
5. Job SRT là tác vụ dài và nhận progress bất đồng bộ. Unmount/remount panel
   trong lúc chạy có thể mất trạng thái UI dù backend vẫn chạy.

### Rủi ro trung bình

1. Modal hiện do nhiều state boolean riêng quản lý; có thể mở chồng nếu
   refactor thiếu kiểm soát.
2. API key được mã hóa ở Electron Safe Storage rồi nạp vào memory worker.
   Không được đưa key vào React state sau khi đã lưu.
3. File/folder picker phụ thuộc Electron preload; preview trên trình duyệt
   thường không thể kiểm tra toàn bộ hành vi desktop.
4. FFmpeg có timeout dài và cơ chế render tuần tự an toàn. Redesign không
   được thay handler hoặc payload.
5. Cấu hình Lite ép `mergeAudio: false` ở cả renderer và backend; không được
   đưa checkbox ghép audio trở lại.

### Rủi ro thấp

1. Đổi token màu, font, spacing.
2. Tách component trình bày thuần.
3. Thêm dark theme nếu toàn bộ màu hard-code được thay bằng token.

## 7. Chiến lược refactor đề xuất

Không dựng lại toàn bộ trong một commit. Thứ tự an toàn:

1. Tạo `src/theme/tokens.css` và `src/theme/base.css`, chưa đổi JSX.
2. Tạo component thuần trong `src/components/ui/`.
3. Tách `SrtVoicePage` và các modal khỏi `App.tsx` nhưng giữ nguyên state và
   handler trước.
4. Tách FFmpeg/CapCut page.
5. Chuyển layout sang hai cột sau khi component đã tách.
6. Thêm toast, accordion nâng cao và preset.
7. Cuối cùng mới xóa dead-code/CSS cũ.

Mỗi phase phải đạt:

- `npm run typecheck`.
- Python compile/self-test.
- Kiểm tra Electron dev.
- Không đóng gói Windows cho đến khi người dùng xác nhận.

## 8. Tiêu chí UI mục tiêu

- Input bắt buộc và CTA chính nhìn thấy ngay.
- Cấu hình nâng cao mặc định thu gọn.
- Không quá một lớp tab con trong mỗi màn hình.
- Label tiếng Việt, không dùng toàn bộ chữ hoa cho nội dung thường.
- Bảng cue/job luôn có progress tổng và trạng thái màu.
- Kích thước chữ nội dung tối thiểu 12–13 px.
- Hỗ trợ cửa sổ từ 1024 px trở lên.
- Light/dark dùng chung design token, đạt tương phản dễ đọc.

## 9. Kết luận Phase 0

Kiến trúc xử lý backend/IPC có thể giữ nguyên. Phần cần refactor lớn nhất là
frontend nguyên khối `src/App.tsx` và hệ CSS override. Nên ưu tiên tách module
trước khi áp dụng layout hai cột; nếu đổi layout ngay trên file hiện tại,
rủi ro regression ở queue, modal và progress khá cao.
