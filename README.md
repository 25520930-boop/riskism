# 🚀 RISKISM — Agentic AI Stock Risk Intelligence

![Riskism Status](https://img.shields.io/badge/Status-v3.1_Production_Ready-success?style=for-the-badge&logo=fastapi)
![Architecture](https://img.shields.io/badge/Architecture-Multi--Agent_Loop-7C3AED?style=for-the-badge&logo=openai)
![AI Engine](https://img.shields.io/badge/AI_Engine-Gemini_Flash_%2F_Pro_Routing-blue?style=for-the-badge&logo=google-gemini)
![Infrastructure](https://img.shields.io/badge/Infrastructure-FastAPI_+_PostgreSQL_+_Redis_+_Celery-FF4B4B?style=for-the-badge&logo=docker)

**RISKISM** không chỉ là một công cụ theo dõi thị trường; đây là một nền tảng **Agentic AI** tự động hóa quy trình quản trị rủi ro chuyên sâu cho nhà đầu tư cá nhân tại Việt Nam. Dự án tập trung vào việc kết hợp giữa **LLM Reasoning** và **Modern Portfolio Theory (MPT)** để đưa ra các quyết định đầu tư có trọng số rủi ro.

---

## 💎 Killer Feature: Agentic Reflection Loop (RAG-based Self-Correction)

Điểm đột phá kỹ thuật lớn nhất của RISKISM chính là vòng lặp **Phản hồi Tự thân (Self-Reflection)**. Hệ thống không chỉ đưa ra dự báo mà còn biết **tự soi lỗi** để cải thiện độ chính xác:

1.  **Morning Analysis (07:30 AM)**: Agent thu thập tin tức vĩ mô, sentiment thị trường và tạo ra 3 loại Insights chuyên biệt:
    *   **Market Insights**: Phân tích rủi ro hệ thống (Systemic Risk) & Vĩ mô.
    *   **Idiosyncratic Insights**: Rủi ro riêng lẻ từng mã cổ phiếu (Company-specific).
    *   **Risk Metrics Insights**: Báo cáo định lượng về các chỉ số rủi ro hiện tại.
2.  **Market Execution**: Thị trường diễn biến trong ngày.
3.  **Afternoon Review (15:30 PM)**: Agent tự động kích hoạt, lấy dữ liệu thực tế đóng cửa (Close prices) và đối chiếu với dự báo sáng.
4.  **Retrieval-Augmented Reflection**: Sử dụng kỹ thuật RAG để truy xuất lại các lập luận cũ, so sánh với kết quả thực tế và tự rút ra bài học (Error analysis). Kết quả phản hồi này sẽ được lưu vào bộ nhớ để điều chỉnh chiến lược cho ngày hôm sau.

---

## 🏗️ Kiến trúc Công nghệ (Multi-LLM Routing)

Hệ thống được thiết kế với kiến trúc **2-Tier LLM Router**, tận dụng tối đa thế mạnh của từng mô hình:
- **Gemini 2.0 Flash** (`fast` tier): Chịu trách nhiệm xử lý các tác vụ tốc độ cao — Classification, Sentiment scoring, Entity extraction. Tối ưu cho throughput.
- **Gemini 2.0 Pro** (`reasoning` tier): Đảm nhiệm vai trò Agent Orchestrator cho các tác vụ lập luận phức tạp — Insight generation, Morning prediction, Self-reflection.
- **Auto-fallback**: Nếu tier `reasoning` thất bại, hệ thống tự động retry với `flash` tier + mock response để đảm bảo không bị gián đoạn.

---

## 🧩 Technical Depth: Regime Parameters & Stress Testing

Hệ thống vận hành với bộ tham số động (Dynamic Parameters) cho phép hiệu chỉnh theo trạng thái thực tế của thị trường:
- **Regime Switching**: Tự động chuyển đổi giữa **Normal, Stress, và Crisis** dựa trên các triggers: VN30 Volatility, Sentiment Score threshold, và Margin Ratio toàn thị trường.
- **Precision Parameters**: Tích hợp các bộ lọc kỹ thuật sâu như Lambda liquidity, EWM span (Exponential Weighted Moving), Delta rebalance thresholds, và Beta caps để tối ưu hóa việc phân bổ tài sản.
- **Capital Tier Advice**: Hệ thống phân loại người dùng theo quy mô vốn: **Tier Small, Medium, hoặc Whale**, từ đó đưa ra các khuyến nghị về "Position Sizing" và số lượng mã tối đa tương ứng.

---

## 🛠️ 10 Core Tools - Bộ công cụ của Agent

Agent được trang bị 10 công cụ tự động hóa hoàn toàn quy trình phân tích:
1.  `fetch_market_data()`: Lấy dữ liệu giá/khối lượng lịch sử (Vnstock).
2.  `fetch_news()`: Cào tin tức thời gian thực từ CafeF/TinNhanhChungKhoan.
3.  `get_portfolio()`: Truy xuất danh mục và khẩu vị rủi ro người dùng.
4.  `score_sentiment()`: Chấm điểm cảm xúc (Sentiment) cho từng mã/ngành.
5.  `classify_news_impact()`: Phân loại mức độ ảnh hưởng (High/Med/Low Impact).
6.  **`calculate_risk_metrics()`**: Tính toán các chỉ số rủi ro định lượng nâng cao.
7.  `detect_anomaly()`: Phát hiện các bất thường về Volume/Price (Outliers).
8.  `save_insight()`: Lưu trữ tri thức và khuyến nghị vào hệ thống.
9.  `save_morning_prediction()`: Ghi nhớ dự báo đầu ngày.
10. **`evaluate_predictions()`**: Công cụ cốt lõi thực hiện Reflection Loop.

---

## 📈 Risk Engine - Phân tích Tài chính Chuyên sâu

Vượt xa các chỉ số cơ bản, RISKISM cung cấp bộ chỉ số rủi ro chuẩn định chế tài chính:
- **Tail Risk**: CVaR 95/99 (Conditional VaR), VaR 95/99 (Historical Percentile).
- **Performance Ratios**: Sharpe, Sortino, Calmar, Information Ratio.
- **Diversification**: HHI Index (độ tập trung), Effective N (số mã thực tế đóng góp vào rủi ro).
- **Market Regimes**: Tự động chuyển đổi kịch bản phân tích theo trạng thái thị trường (**Normal / Stress / High / Extreme**).
- **Vietnam Specifics**: Kiểm tra Lô tối thiểu (Min lot 100) và so sánh Sector Exposure vs VN30.

---

## 🚀 Hạ tầng & Triển khai (Infrastructure)

Hệ thống sẵn sàng cho Production với:
- **PostgreSQL**: Lưu trữ persistence cho Portfolio và Insights.
- **Redis**: Caching dữ liệu giá thời gian thực để đạt hiệu năng cao nhất.
- **Celery Beat / Workers**: Tự động hóa hoàn toàn việc trigger Agent 2 lần/ngày (Morning & Afternoon review) mà không cần can thiệp thủ công.
- **Docker Compose**: Triển khai toàn bộ stack (Frontend, Backend, DB, Redis, Celery) chỉ với một lệnh.

---

## 📡 API Endpoints & System Diagnostics

Hệ thống cung cấp các giao thức kết nối tiêu chuẩn để giám sát và vận hành:
- `POST /api/agent/trigger`: Kích hoạt Agent thực hiện phân tích (Morning/Afternoon).
- `GET /api/portfolio/{user_id}`: Truy xuất danh mục và phân tích rủi ro thời gian thực.
- **`GET /api/health`**: Cung cấp báo cáo **System Diagnostics** chuyên sâu:
    *   **Latency Monitoring**: Theo dõi độ trễ của các LLM calls.
    *   **LLM Cache Hit Rate**: Hiệu quả của bộ đệm TTLCache.
    *   **Database Connectivity**: Trạng thái kết nối PostgreSQL.
    *   **Market Data Cache**: Quy mô dữ liệu giá đang lưu trữ tại Redis/In-memory.

---

## 🛠️ Cách khởi chạy nhanh (Quick Start)

1.  Clone dự án.
2.  Điền `GEMINI_API_KEY` và `DATABASE_URL` vào file `.env`.
3.  Chạy lệnh: `docker-compose up -d --build`.
4.  Truy cập: `http://localhost:3000`.

---
*Developed with ❤️ for Advanced Investment Intelligence.*
