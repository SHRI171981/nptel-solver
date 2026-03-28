import asyncio
import os
import aiohttp
from flask import Flask, request, jsonify
from flask_cors import CORS
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Optional, Union
from datetime import datetime

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- LLM Provider Configuration ---

provider = GoogleProvider(api_key=os.environ.get("GEMINI_API_KEY"))
model = GoogleModel(os.environ.get("MODEL", "gemini-2.5-flash"), provider=provider)

# --- VLM Output Schemas ---

class MCQAnswer(BaseModel):
    """Schema for Single-Select Multiple Choice Questions."""
    option_index: int

class MSQAnswer(BaseModel):
    """Schema for Multi-Select Multiple Choice Questions."""
    option_indices: list[int]

class TextAnswer(BaseModel):
    """Schema for Numerical or String input questions."""
    text_answer: str

# --- Application Data Schemas ---

class QuestionPayload(BaseModel):
    """Schema defining the required structure for incoming question data."""
    question_id: Union[str, int]
    question_type: str = Field(default="mcq")
    question_text: Optional[str] = ""
    case_study_text: Optional[str] = ""
    image_url: Optional[str] = None
    options: list[str] = Field(default_factory=list)

class TokenUsage(BaseModel):
    """Schema for individual question token consumption."""
    input_tokens: int
    output_tokens: int

class QuestionResult(BaseModel):
    """Schema for the standardized output of a processed question."""
    question_id: Union[str, int]
    question_type: Optional[str] = None
    tokens_used: Optional[TokenUsage] = None
    text_answer: Optional[str] = None
    option_indices: Optional[list[int]] = None
    error: Optional[str] = None

class TokenSummary(BaseModel):
    """Schema for aggregate batch token consumption metrics."""
    total_questions: int
    total_input_tokens: int
    total_output_tokens: int

class BatchResult(BaseModel):
    """Schema for the final API response payload."""
    results: list[QuestionResult]
    token_summary: TokenSummary

# --- Agent Definitions ---

numerical_agent = Agent(
    model,
    output_type=TextAnswer,
    instructions=(
        "Analyze the provided educational question.\n"
        "Solve the problem and return ONLY the final numerical or string answer required.\n"
        "Do not include units unless explicitly requested."
    )
)

msq_agent = Agent(
    model,
    output_type=MSQAnswer,
    instructions=(
        "Analyze the provided educational question and the corresponding options.\n"
        "Determine the correct options. Return an array containing the integer indices of ALL correct options."
    )
)

mcq_agent = Agent(
    model,
    output_type=MCQAnswer,
    instructions=(
        "Analyze the provided educational question and the corresponding options.\n"
        "Determine the correct option. Return the integer index of the strictly correct option."
    )
)

# --- Core Logic ---

async def fetch_image_base64(session: aiohttp.ClientSession, url: str) -> bytes | None:
    """Asynchronously retrieves image binary data. Returns raw bytes for BinaryContent structure."""
    try:
        async with session.get(url, timeout=10) as response:
            response.raise_for_status()
            return await response.read()
    except aiohttp.ClientError as e:
        print(f"Network error fetching image {url}: {e}")
        return None

async def evaluate_single_question(session: aiohttp.ClientSession, question: QuestionPayload) -> QuestionResult:
    """Processes a typed question payload via dedicated Agents and maps the output property."""
    prompt_parts = []
    
    # Construct textual context
    text_context = []
    if question.case_study_text:
        text_context.append(f"Context / Case Study:\n{question.case_study_text}\n")
    if question.question_text:
        text_context.append(f"Question:\n{question.question_text}")
    
    if question.question_type in ["mcq", "msq"] and question.options:
        options_text = "\n".join([f"Index {i}: {opt}" for i, opt in enumerate(question.options)])
        text_context.append(f"\nOptions:\n{options_text}")
        
    combined_text = "\n".join(text_context)
    if combined_text:
        prompt_parts.append(combined_text)
        
    # Construct multimodal context
    if question.image_url:
        image_bytes = await fetch_image_base64(session, question.image_url)
        if image_bytes:
            prompt_parts.append(BinaryContent(data=image_bytes, media_type='image/jpeg'))
        else:
            return QuestionResult(question_id=question.question_id, error="Image fetch failed")

    # Route to appropriate Agent based on payload definition
    try:
        if question.question_type == "numerical":
            run_result = await numerical_agent.run(prompt_parts)
        elif question.question_type == "msq":
            run_result = await msq_agent.run(prompt_parts)
        else:
            run_result = await mcq_agent.run(prompt_parts)
            
        usage_data = run_result.usage()
        tokens = TokenUsage(
            input_tokens=usage_data.input_tokens if usage_data else 0,
            output_tokens=usage_data.output_tokens if usage_data else 0,
        )

        result = QuestionResult(
            question_id=question.question_id,
            question_type=question.question_type,
            tokens_used=tokens
        )

        # Map dynamic agent output directly to unified response schema
        if isinstance(run_result.output, TextAnswer):
            result.text_answer = run_result.output.text_answer
        elif isinstance(run_result.output, MSQAnswer):
            result.option_indices = run_result.output.option_indices
        elif isinstance(run_result.output, MCQAnswer):
            result.option_indices = [run_result.output.option_index]

        return result

    except Exception as e:
        print(f"Agent execution failed for question {question.question_id}: {e}")
        return QuestionResult(question_id=question.question_id, error="Agent processing failed")

async def process_batch(payload: list[QuestionPayload]) -> BatchResult:
    """Orchestrates concurrent execution of Agent runs and aggregates token utilization metrics."""
    async with aiohttp.ClientSession() as session:
        tasks = [evaluate_single_question(session, question) for question in payload]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = [res for res in results if isinstance(res, QuestionResult)]
        
        total_in = sum(res.tokens_used.input_tokens for res in valid_results if res.tokens_used)
        total_out = sum(res.tokens_used.output_tokens for res in valid_results if res.tokens_used)

        token_summary = TokenSummary(
            total_questions=len(valid_results),
            total_input_tokens=total_in,
            total_output_tokens=total_out,
        )
        
        # Format timestamp and target log data execution state
        timestamp = datetime.now().astimezone().isoformat()
        log_payload = {
            'total_questions': len(valid_results),
            'total_input_tokens': total_in,
            'total_output_tokens': total_out,
            'total_tokens': total_in + total_out
        }
        
        # Append target execution string cleanly to physical log
        with open('tokens.log', 'a') as log_file:
            log_file.write(f"{timestamp} - Batch processed: {log_payload}\n")
        
        return BatchResult(
            results=valid_results,
            token_summary=token_summary
        )

@app.route('/api/solve', methods=['POST'])
def solve_exam():
    """Synchronous Flask route handling input validation and executing the event loop."""
    raw_payload = request.get_json()
    if not raw_payload or not isinstance(raw_payload, list):
        return jsonify({"error": "Invalid payload format. Expected JSON array."}), 400

    try:
        validated_payload = [QuestionPayload.model_validate(item) for item in raw_payload]
    except Exception as e:
        return jsonify({"error": f"Schema validation failed: {str(e)}"}), 422

    try:
        resolved_answers = asyncio.run(process_batch(validated_payload))
        return jsonify(resolved_answers.model_dump()), 200
    except Exception as e:
        print(f"Batch processing error: {e}")
        return jsonify({"error": "Internal server processing failure."}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)