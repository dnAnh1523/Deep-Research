# Frontend — Deep Research Agent

> Mô tả frontend Vite + React 19 + Tailwind CSS v4: component tree, luồng UX, SSE integration, và styling.

---

## Stack

| Công nghệ | Phiên bản | Vai trò |
|---|---|---|
| **Vite** | 8.x | Build tool + dev server |
| **React** | 19.x | UI framework |
| **Tailwind CSS** | 4.x (via `@tailwindcss/vite`) | Utility-first CSS |
| **TypeScript** | 6.x | Type safety |
| **Lucide React** | 1.x | Icon library |
| **Marked** | 18.x | Markdown → HTML renderer |

---

## Component Tree

```
App.tsx
├── Sidebar.tsx                    ← Collapsible left sidebar (sessions list)
├── ChatFeed.tsx                   ← Central chat interface
│   └── ResearchPlanCard.tsx       ← AI-generated research plan card
└── ResearchCanvas.tsx             ← Fixed right-side canvas panel
    ├── CanvasThoughtStream.tsx    ← Real-time thought steps + web source pills
    └── CanvasReportViewer.tsx     ← Full report viewer with accordions
        ├── ReadingCanvas.tsx      ← Markdown rendering engine
        └── CitationPopover.tsx    ← Hover-triggered citation preview
```

---

## Luồng UX (User Experience Flow)

### 1. Zero State
Khi chưa có phiên nào, toàn bộ màn hình hiển thị:
- **Giữa**: Câu hỏi *"Bạn muốn nghiên cứu về nội dung gì?"*
- **Dưới cùng**: Thanh nhập liệu nổi
- **Sidebar**: Thu gọn mặc định

### 2. Lập kế hoạch (Planning)
Người dùng nhập câu hỏi → `useResearchApi.fetchPlan()` gọi `POST /research/plan`:
- AI sinh ra **Research Plan Card** hiển thị trong chat
- 2 nút hành động: `[Chỉnh sửa kế hoạch]` và `[Bắt đầu nghiên cứu]`

### 3. Chỉnh sửa kế hoạch (Clarify Loop)
Nếu bấm `[Chỉnh sửa kế hoạch]`:
- Chat chuyển sang mode `editing_plan`
- AI hỏi người dùng cần sửa gì
- Người dùng nhắn lại → Plan Card mới được sinh (mang theo `clarificationHistory`)

### 4. Nghiên cứu đang chạy (Researching)
Nếu bấm `[Bắt đầu nghiên cứu]`:
- Chat hiện thẻ trạng thái *"Đang nghiên cứu..."*
- **Side Canvas** mở bên phải ở mode `progress`:
  - Thought steps xuất hiện theo thời gian thực (icon ✨ + tiêu đề + mô tả)
  - Web source pills hiện tên miền + favicon
  - Skeleton loading animation

### 5. Báo cáo hoàn chỉnh (Completed)
Khi stream kết thúc:
- Canvas chuyển sang mode `report`
- Hiển thị báo cáo Markdown đầy đủ
- Mục lục dropdown + trích dẫn hover
- 3 accordion ở cuối: Nguồn được dùng, Nguồn tham khảo khác, Quá trình suy nghĩ

---

## Components chi tiết

### [`App.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/App.tsx)

Root component quản lý toàn bộ state:
- `sessions` (persist vào `localStorage`)
- `messages`, `currentPlan`, `status`, `thoughtSteps`, `webSources`, `report`, `citations`
- `isCanvasOpen`, `canvasMode` ('progress' | 'report')

### [`Sidebar.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/components/Sidebar.tsx)

- Nút `+ Cuộc trò chuyện mới`
- Danh sách phiên nghiên cứu gần đây
- Collapsible (toggle via hamburger button)

### [`ChatFeed.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/components/ChatFeed.tsx)

- Render danh sách `ChatMessage[]`
- Nhận diện `message.type` để render đúng component:
  - `'plan'` → `ResearchPlanCard`
  - `'start_confirmation'` → Thẻ trạng thái xanh
  - `'completed_notice'` → Thẻ hoàn thành
  - default → Bong bóng text
- Input bar nằm dưới đáy

### [`ResearchPlanCard.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/components/ResearchPlanCard.tsx)

- Tiêu đề nghiên cứu
- Danh sách bước (expandable)
- Thời gian ước tính
- 2 nút: `[Chỉnh sửa kế hoạch]` + `[Bắt đầu nghiên cứu]`

### [`ResearchCanvas.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/components/ResearchCanvas.tsx)

Side panel cố định (50-56% màn hình), bo tròn (`rounded-3xl`), floating card design:
- **mode = 'progress'**: Header + `CanvasThoughtStream`
- **mode = 'report'**: `CanvasReportViewer`

### [`CanvasThoughtStream.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/components/CanvasThoughtStream.tsx)

- Render danh sách `ThoughtStep[]` với icon Sparkle
- Render `WebSourceChip[]` dạng capsule pills (domain name)
- Skeleton bars khi `isStreaming`

### [`CanvasReportViewer.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/components/CanvasReportViewer.tsx)

- Header: Tiêu đề + Mục lục dropdown + Chia sẻ/Xuất + Nút đóng
- Body: `ReadingCanvas` (Markdown rendering)
- Footer: 3 accordion sections

### [`ReadingCanvas.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/components/ReadingCanvas.tsx)

- Markdown → HTML via `marked`
- Custom renderer cho tables, headings (auto-generate `id`)
- Superscript citations `[1]` hover → `CitationPopover`

### [`CitationPopover.tsx`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/components/CitationPopover.tsx)

- Hover-triggered (không phải click)
- Giữ mở khi chuột ở trong popover
- Hiển thị: title, publisher, year, snippet, link gốc

---

## SSE Integration

### [`hooks/useResearchApi.ts`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/hooks/useResearchApi.ts)

Cung cấp 2 hàm chính:

#### `fetchPlan(query, clarificationHistory)`
- `POST /research/plan` → trả về `ResearchPlan`
- Fallback plan nếu backend không phản hồi

#### `executeResearch(query, clarificationHistory, callbacks)`
- `POST /research/stream` → đọc `ReadableStream`
- Parse từng `data:` line thành JSON
- Dispatch callbacks:
  - `onThought(ThoughtStep)` — khi nhận event từ `intent_arbitrator`, `supervisor`, `researcher`
  - `onWebSource(WebSourceChip)` — bóc từ citations
  - `onComplete(report, citations)` — khi stream kết thúc
  - `onError(message)` — khi có lỗi
- Fallback: nếu stream không có `final_report`, fetch `/api/latest-report`

---

## Type System

[`types/research.ts`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/types/research.ts) định nghĩa:

| Interface | Mục đích |
|---|---|
| `Citation` | Trích dẫn nguồn (id, title, url, snippet, verified) |
| `SectionNode` | Mục lục heading (id, title, level) |
| `ResearchPlan` | Kế hoạch nghiên cứu (title, steps, time_estimate) |
| `ThoughtStep` | Bước tư duy real-time (id, title, detail) |
| `WebSourceChip` | Thẻ nguồn web (url, title, domain) |
| `ChatMessage` | Tin nhắn chat (sender, text, type, plan) |
| `ResearchSession` | Phiên nghiên cứu đầy đủ (messages, plan, report, citations, status) |

---

## Styling

### Theme tokens ([`index.css`](file:///f:/AI_ML%20Projects/Deep%20Research/frontend/src/index.css))

Dark-mode only. CSS custom properties:
- **Surfaces**: `--surface-ground` (#0f0f0f), `--surface-card` (#171717), `--surface-elevated` (#1f1f1f)
- **Text**: `--text-display`, `--text-primary`, `--text-secondary`, `--text-tertiary`
- **Accent**: `--accent-blue` (#1f3b9b), with neutral hover brightness instead of decorative outlines

### Utility classes

| Class | Mục đích |
|---|---|
| `.glass-chrome` | Glassmorphism background + blur |
| `.glass-pill` | Capsule pill glassmorphism |
| `.apple-card` | Elevated card with subtle shadow + hover border |
| `.tactile-btn` | Button with scale-down on press |

### Font

Geist + Geist Mono (loaded from CDN trong `index.html`).

---

## Chạy development

```bash
cd frontend
npm install
npm run dev        # Vite dev server tại http://localhost:3000
```

Build production:
```bash
npm run build      # Output tại frontend/dist/
```

Lint:
```bash
npm run lint       # OxLint
```
