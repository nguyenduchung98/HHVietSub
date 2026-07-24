import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Input,
  ProgressBar,
  SegmentedControl,
  Select,
  Slider,
  Spinner,
  ToastProvider,
  useToast,
} from './ui';
import './component-preview.css';

function PreviewContent() {
  const [service, setService] = useState<'capcut' | 'ai33' | 'aimax'>('capcut');
  const [speed, setSpeed] = useState(1);
  const { showToast } = useToast();
  return (
    <main className="component-preview">
      <header>
        <div><span>HHVietSub Lite</span><h1>UI Component Preview</h1><p>Trang QA nội bộ — không thuộc luồng sản phẩm.</p></div>
        <Button variant="ghost" onClick={() => history.back()}>Quay lại</Button>
      </header>

      <div className="component-preview__grid">
        <Card title="Buttons" description="Biến thể, disabled và loading">
          <div className="component-preview__row">
            <Button variant="primary">Tạo voice</Button><Button>Phụ</Button><Button variant="ghost">Ghost</Button><Button variant="danger">Hủy</Button><Button disabled>Disabled</Button><Button loading>Đang xử lý</Button>
          </div>
        </Card>

        <Card title="Form controls" description="Input, select, segmented control và slider">
          <div className="component-preview__form">
            <Input id="preview-name" label="Tên kết quả" placeholder="Nhập tên file" hint="Không cần nhập phần mở rộng." />
            <Select id="preview-language" label="Ngôn ngữ" defaultValue="vi"><option value="vi">Tiếng Việt</option><option value="en">English</option></Select>
            <SegmentedControl label="Dịch vụ tạo giọng" value={service} onChange={setService} options={[{ value: 'capcut', label: 'CapCut' }, { value: 'ai33', label: 'AI33' }, { value: 'aimax', label: 'AIMax' }]} />
            <Slider label="Tốc độ" value={speed} valueLabel={`${speed.toFixed(2)}×`} min={0.5} max={2} step={0.05} onChange={setSpeed} />
          </div>
        </Card>

        <Card title="Trạng thái" description="Badge, progress và spinner">
          <div className="component-preview__stack">
            <div className="component-preview__row"><Badge status="pending" /><Badge status="running" /><Badge status="done" /><Badge status="error" /></div>
            <ProgressBar value={68} label="Đang tạo 221/326 câu" />
            <div className="component-preview__row"><Spinner /><span>Đang tải thư viện giọng…</span></div>
          </div>
        </Card>

        <Card title="Toast" description="Thông báo tự ẩn ở góc phải trên">
          <div className="component-preview__row">
            <Button onClick={() => showToast({ kind: 'success', title: 'Đã hoàn thành', message: '326 câu đã được tạo.' })}>Success</Button>
            <Button onClick={() => showToast({ kind: 'error', title: 'Tạo voice thất bại', message: 'Không thể kết nối dịch vụ.' })}>Error</Button>
            <Button onClick={() => showToast({ kind: 'info', title: 'Đã thêm vào hàng chờ' })}>Info</Button>
          </div>
        </Card>
      </div>
    </main>
  );
}

export function ComponentPreview() {
  return <ToastProvider><PreviewContent /></ToastProvider>;
}
