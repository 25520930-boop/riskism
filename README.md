# 🚀 RISKISM — Agentic AI Stock Risk Intelligence

![Riskism Status](https://img.shields.io/badge/Status-v3.1_Production_Ready-success?style=for-the-badge&logo=fastapi)
![Architecture](https://img.shields.io/badge/Architecture-Multi--Agent_Loop-7C3AED?style=for-the-badge&logo=openai)
![AI Engine](https://img.shields.io/badge/AI_Engine-Gemini_Flash_%2F_Pro_Routing-blue?style=for-the-badge&logo=google-gemini)
![Infrastructure](https://img.shields.io/badge/Infrastructure-FastAPI_+_PostgreSQL_+_Redis_+_Celery-FF4B4B?style=for-the-badge&logo=docker)

**RISKISM** là nền tảng quản trị rủi ro chứng khoán thế hệ mới dựa trên **Agentic AI**. Không chỉ dừng lại ở việc theo dõi bảng điện, RISKISM kết hợp sức mạnh của **Định lượng Tài chính (Quant)** và **Trí tuệ nhân tạo (LLM)** để mang đến cái nhìn chuyên sâu và khách quan cho nhà đầu tư cá nhân tại Việt Nam.

---

## 💎 Điểm nhấn công nghệ: Self-Reflection Loop
Đây là "bộ não" của RISKISM, cho phép AI tự học và cải thiện độ chính xác thông qua dữ liệu thực tế:
1.  **Morning Analysis (07:30 AM)**: Dự báo triển vọng thị trường và rủi ro danh mục dựa trên tin tức vĩ mô và sentiment.
2.  **Afternoon Review (15:30 PM)**: Đối chiếu dự báo sáng với kết quả thực tế.
3.  **Agentic Reflection**: AI tự phân tích tại sao mình đúng/sai, rút ra bài học kinh nghiệm và lưu vào bộ nhớ dài hạn để tối ưu hóa dự báo cho ngày hôm sau.

---

## 🛠️ Bộ công cụ & Kiến trúc (Technical Stack)

### Backend (Python/FastAPI)
- **FastAPI**: Core API hiệu năng cao với hỗ trợ WebSocket và Request Tracing.
- **Celery & Redis**: Tự động hóa các tác vụ Agent chạy ngầm và lập lịch (Beat) theo giờ giao dịch.
- **PostgreSQL**: Lưu trữ dữ liệu danh mục, lịch sử insights và bộ nhớ của AI.
- **Multi-LLM Router**: Cơ chế điều phối linh hoạt giữa **Gemini 2.0 Pro** (Lập luận sâu) và **Gemini 2.0 Flash** (Xử lý tin tức tốc độ cao).

### Frontend (Vanilla JS / Modern CSS)
- **Real-time Engine**: WebSocket truyền tải giá live và kết quả phân tích AI ngay tức thì.
- **Quant Charts**: Trực quan hóa các chỉ số rủi ro chuyên sâu (VaR, Correlation, Stress Test).
- **Responsive Design**: Giao diện cao cấp, hỗ trợ chế độ Dark Mode và tối ưu trên mọi thiết bị.

---

## 📉 Quant Risk Engine - Phân tích định lượng chuẩn định chế
Hệ thống cung cấp bộ chỉ số rủi ro chuyên sâu vượt xa các ứng dụng thông thường:
- **Tail Risk**: Tính toán **VaR 95/99** và **CVaR** (Rủi ro đuôi) theo phương pháp Historical.
- **Performance**: Sharpe, Sortino, và Max Drawdown.
- **Liquidity Aware**: Đánh giá thanh khoản thực tế T+2 và rủi ro giải chấp.
- **Anomaly Detection**: Tự động phát hiện biến động khối lượng đột biến hoặc giá phá đỉnh/đáy.

---

## 🚀 Hướng dẫn khởi chạy nhanh

### 1. Yêu cầu hệ thống
- Docker & Docker Compose.
- Google Gemini API Key.

### 2. Cài đặt
1.  **Clone repo** và copy file cấu hình:
    ```bash
    cp .env.example .env
    ```
2.  **Cấu hình `.env`**: Điền `GEMINI_API_KEY` và các thông tin Database/Firebase (nếu có).
3.  **Chạy Docker**:
    ```bash
    docker-compose up -d --build
    ```
4.  **Truy cập**:
    - Frontend: `http://localhost:3000`
    - API Docs (Swagger): `http://localhost:8000/docs`

---

## 🧪 Kiểm thử & Phát triển
Dự án bao gồm bộ test tự động toàn diện để đảm bảo tính ổn định:
```bash
python test_all.py
```
Bộ test bao gồm 14 hạng mục kiểm tra từ Logic tài chính, Bảo mật LLM đến sự chính xác của các API endpoints.

---

## 🛡️ Bảo mật & Tin cậy
- **Observability**: Hệ thống tích hợp sẵn X-Request-ID và Diagnostics Healthcheck.
- **Degraded Mode**: Tự động chuyển sang chế độ phân tích toán học cơ bản khi LLM gặp sự cố hoặc hết quota.
- **Audit Logging**: Ghi lại mọi hành động nhạy cảm để đảm bảo tính minh bạch.

---
*Phát triển bởi đội ngũ đam mê tài chính định lượng và AI.*
