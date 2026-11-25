# Anki Card Maker
Nhập từ/cụm/cấu trúc → AI (Gemini hoặc OpenAI, key của bạn) điền nghĩa, loại từ, ví dụ, dịch, IPA, đồng/trái nghĩa → sửa trong bảng → xuất `.apkg`.

Chạy máy: `pip install -r requirements.txt && uvicorn main:app --port 8000` rồi mở http://127.0.0.1:8000

Deploy Render: push thư mục này lên GitHub → Render → New → Blueprint (đọc `render.yaml`).
API key chỉ đi qua server để gọi AI, không lưu vào file hay localStorage.
