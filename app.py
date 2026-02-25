import asyncio
import base64
import os
import aiohttp
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import AsyncOpenAI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

MODEL = os.environ.get("MODEL", "gpt-4o-mini")
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

class MCQAnswer(BaseModel):
    """Schema for Single-Select Multiple Choice Questions."""
    option_index: int

class MSQAnswer(BaseModel):
    """Schema for Multi-Select Multiple Choice Questions."""
    option_indices: list[int]

class TextAnswer(BaseModel):
    """Schema for Numerical or String input questions."""
    text_answer: str

async def fetch_image_base64(session: aiohttp.ClientSession, url: str) -> str | None:
    """Asynchronously retrieves image binary data and returns a base64 encoded string."""
    try:
        async with session.get(url, timeout=10) as response:
            response.raise_for_status()
            image_data = await response.read()
            return base64.b64encode(image_data).decode('utf-8')
    except aiohttp.ClientError as e:
        print(f"Network error fetching image {url}: {e}")
        return None

async def evaluate_single_question(session: aiohttp.ClientSession, question: dict) -> dict | None:
    """Processes a single question, handling case study context and dynamically routing to the appropriate Pydantic schema."""
    question_id = question.get("question_id")
    question_type = question.get("question_type", "mcq")
    question_text = question.get("question_text", "")
    case_study_text = question.get("case_study_text", "")
    image_url = question.get("image_url")
    options = question.get("options", [])

    if question_type == "numerical":
        response_format = TextAnswer
        system_prompt = (
            "Analyze the provided educational question.\n"
            "Solve the problem and return ONLY the final numerical or string answer required.\n"
            "Do not include units unless explicitly requested."
        )
    elif question_type == "msq":
        response_format = MSQAnswer
        options_text = "\n".join([f"Index {i}: {opt}" for i, opt in enumerate(options)])
        system_prompt = (
            "Analyze the provided educational question and the corresponding options.\n"
            f"Options:\n{options_text}\n\n"
            "Determine the correct options. Return an array containing the integer indices of ALL correct options."
        )
    else:
        response_format = MCQAnswer
        options_text = "\n".join([f"Index {i}: {opt}" for i, opt in enumerate(options)])
        system_prompt = (
            "Analyze the provided educational question and the corresponding options.\n"
            f"Options:\n{options_text}\n\n"
            "Determine the correct option. Return the integer index of the strictly correct option."
        )

    user_content = []
    text_parts = []
    
    if case_study_text:
        text_parts.append(f"Context / Case Study:\n{case_study_text}\n")
    if question_text:
        text_parts.append(f"Question:\n{question_text}")
        
    combined_text = "\n".join(text_parts)
    if combined_text:
        user_content.append({"type": "text", "text": combined_text})
        
    if image_url:
        base64_image = await fetch_image_base64(session, image_url)
        if base64_image:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}",
                    "detail": "low"
                }
            })
        else:
            return {"question_id": question_id, "error": "Image fetch failed"}

    try:
        response = await client.beta.chat.completions.parse(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format=response_format,
            temperature=0.0
        )
        
        parsed_result = response.choices[0].message.parsed
        
        result_payload = {
            "question_id": question_id,
            "question_type": question_type,
            "tokens_used": {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }

        if question_type == "numerical":
            result_payload["text_answer"] = str(parsed_result.text_answer)
        elif question_type == "msq":
            result_payload["option_indices"] = parsed_result.option_indices
        else:
            result_payload["option_indices"] = [parsed_result.option_index]

        return result_payload

    except Exception as e:
        print(f"VLM evaluation failed for question {question_id}: {e}")
        return {"question_id": question_id, "error": "VLM processing failed"}

async def process_batch(payload: list) -> dict:
    """Orchestrates concurrent execution of API calls and aggregates token utilization metrics."""
    async with aiohttp.ClientSession() as session:
        tasks = [evaluate_single_question(session, question) for question in payload]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = [res for res in results if isinstance(res, dict)]
        
        token_summary = {
            "total_questions": len(valid_results),
            "total_input_tokens": sum(res.get("tokens_used", {}).get("input_tokens", 0) for res in valid_results),
            "total_output_tokens": sum(res.get("tokens_used", {}).get("output_tokens", 0) for res in valid_results),
            "total_tokens": sum(res.get("tokens_used", {}).get("total_tokens", 0) for res in valid_results)
        }
        
        return {
            "results": valid_results,
            "token_summary": token_summary
        }

@app.route('/api/solve', methods=['POST'])
def solve_exam():
    """Synchronous Flask route bridging the HTTP request to the asynchronous event loop."""
    payload = request.get_json()
    if not payload or not isinstance(payload, list):
        return jsonify({"error": "Invalid payload format. Expected JSON array."}), 400

    try:
        resolved_answers = asyncio.run(process_batch(payload))
        return jsonify(resolved_answers), 200
    except Exception as e:
        print(f"Batch processing error: {e}")
        return jsonify({"error": "Internal server processing failure."}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)