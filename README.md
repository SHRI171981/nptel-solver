# NPTEL Answering

A Flask-based backend service that uses OpenAI's Vision-Language Model (VLM) to automatically answer NPTEL exam questions. It supports single-select MCQ, multi-select (MSQ), and numerical/text questions — with optional image inputs processed concurrently.

---

## Features

- **Multimodal input** — accepts question text, image URLs, or both
- **Three question types** — `mcq`, `msq`, `numerical`
- **Structured outputs** — uses Pydantic schemas with OpenAI's `beta.chat.completions.parse` for guaranteed JSON schema compliance
- **Concurrent processing** — all questions in a batch are processed in parallel via `asyncio.gather`
- **Token tracking** — per-question and per-batch token usage (input, output, total) logged to `token_usage.log` with IST timestamps
- **Configurable model** — defaults to `gpt-4o-mini`, overridable via the `MODEL` environment variable

---

## Project Structure

```
NPTEL Answering/
├── app.py             # Flask application and async processing logic
├── requirements.txt   # Python dependencies
├── .env               # Environment variables (not committed)
└── token_usage.log    # Auto-generated token usage log (IST timestamps)
```

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd "NPTEL Answering"
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...
MODEL=gpt-4o-mini          # optional, defaults to gpt-4o-mini
```

---

## Running the Server

```bash
python app.py
```

The server starts at `http://127.0.0.1:5000`.

---

## API Reference

### `POST /api/solve`

Accepts a JSON array of question objects and returns answers for all questions.

**Request body:**

```json
[
  {
    "question_id": "q1",
    "question_type": "mcq",
    "question_text": "Which of the following is a prime number?",
    "options": ["4", "6", "7", "9"],
    "image_url": "https://example.com/question_image.jpg"
  }
]
```

| Field           | Type     | Required | Description                                      |
|----------------|----------|----------|--------------------------------------------------|
| `question_id`  | string   | Yes      | Unique identifier for the question               |
| `question_type`| string   | No       | `mcq` (default), `msq`, or `numerical`           |
| `question_text`| string   | No       | Plain text of the question                       |
| `image_url`    | string   | No       | Public URL of the question image                 |
| `options`      | string[] | No       | Answer choices (required for `mcq` and `msq`)   |

**Response:**

```json
{
  "results": [
    {
      "question_id": "q1",
      "question_type": "mcq",
      "option_indices": [2],
      "tokens_used": {
        "input_tokens": 118,
        "output_tokens": 24,
        "total_tokens": 142
      }
    }
  ],
  "token_summary": {
    "total_questions": 1,
    "total_input_tokens": 118,
    "total_output_tokens": 24,
    "total_tokens": 142
  }
}
```

### Answer fields by question type

| `question_type` | Answer field       | Type       | Example              |
|----------------|--------------------|------------|----------------------|
| `mcq`          | `option_indices`   | `[int]`    | `[2]`                |
| `msq`          | `option_indices`   | `[int, …]` | `[0, 2, 3]`          |
| `numerical`    | `text_answer`      | `string`   | `"42"` or `"9.81"`  |

---

## Token Logging

Each batch appended to `token_usage.log` in the format:

```
2026-02-26T14:32:10.123456+05:30 - Batch processed: {'total_questions': 5, 'total_input_tokens': 590, 'total_output_tokens': 120, 'total_tokens': 710}
```

---

## Dependencies

| Package        | Purpose                                      |
|---------------|----------------------------------------------|
| `flask`       | HTTP server and routing                      |
| `flask-cors`  | Cross-Origin Resource Sharing                |
| `aiohttp`     | Async HTTP client for fetching images        |
| `openai`      | OpenAI API client with structured outputs    |
| `pydantic`    | Response schema validation                   |
| `python-dotenv` | Loading `.env` environment variables       |
| `pytz`        | IST timezone for log timestamps              |
