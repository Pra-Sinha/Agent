from fastapi import FastAPI, HTTPException, Depends, status,APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth, credentials, firestore
from schemas import ChatResponse, ChatMessage
from pydantic import BaseModel, constr, conint
from datetime import datetime, timedelta
import uvicorn
from typing import Dict, Optional
from dotenv import load_dotenv
import httpx
import os
import logging
import traceback
import asyncio  # Required for async sleep

from memory import db, get_session, update_session

# Flight booking components
from nlu_processor import process_user_input
from flight_api import search_flights, get_flight_details
from booking_api import create_booking
from payment_gateway import initiate_payment
from ticket_generator import generate_ticket
from memory import ConversationMemory
from booking_request import BookingRequest

# 🔐 Load environment variables
load_dotenv()

# 🔥 Firebase initialization
logger = logging.getLogger(__name__)
router = APIRouter()
app = FastAPI(title="Flight Booking AI Agent API")
app.include_router(router)


security = HTTPBearer()

@app.get("/")
async def root():
    print("✅ Root endpoint called")
    return {"status": "ok"}


# 📝 Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 🌐 CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
# 🗄️ Conversation store
conversations = db.collection("chat_sessions")

# 🔑 Auth dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        decoded_token = auth.verify_id_token(credentials.credentials)
        return {
            "uid": decoded_token["uid"],
            "email": decoded_token.get("email"),
            "phone": decoded_token.get("phone_number")
        }
    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ✈️ Enhanced FlightSearchRequest with validation
class FlightSearchRequest(BaseModel):
    origin: constr(min_length=3, max_length=3, to_upper=True)
    destination: constr(min_length=3, max_length=3, to_upper=True)
    date: constr(pattern=r"^\d{4}-\d{2}-\d{2}$")
    adults: conint(gt=0, le=9) = 1

# 🤖 Enhanced chat endpoint
@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    chat_message: ChatMessage,
    user: dict = Depends(get_current_user)
):
    session_id = f"{user['uid']}_{chat_message.session_id}"

    try:
        print(f"📥 Incoming message: {chat_message.message}")
        print(f"🔐 Authenticated user: {user['email'] or user['phone']}")

        # 🔄 Load session or create new
        session_ref = conversations.document(session_id)
        doc_snapshot = session_ref.get()
        session_data = doc_snapshot.to_dict() if doc_snapshot.exists else {
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": [],
            "context": {}
        }

        # 🧠 Process user message
        processed_input = process_user_input(chat_message.message)

        # 📝 Append user message
        session_data["messages"].append({
            "role": "user",
            "content": chat_message.message,
            "timestamp": datetime.now()
        })

        # 🧾 Define system prompt
        system_prompt = f"""
        You are an expert flight booking assistant. Current user: {user['email'] or user['phone']}.
        Context: {session_data.get('context', {})}
        """

        # 🤖 Get AI response
        ai_response = await chat_with_deepseek(
            messages=session_data["messages"],
            system_prompt=system_prompt
        )

        print(f"💬 AI Response: {ai_response}")

        # 📎 Append AI message
        session_data["messages"].append({
            "role": "assistant",
            "content": ai_response,
            "timestamp": datetime.now()
        })

        # 🔧 Update context from AI response
        session_data["context"] = process_user_input(ai_response)
        session_data["updated_at"] = datetime.now()

        # 💾 Save session to Firestore
        session_ref.set(session_data)

        # ✅ Return response
        return ChatResponse(
            response=ai_response,
            requires_input="true" if not session_data["context"].get("complete") else "false"
        )

    except Exception as e:
        print("❌ Exception in chat_endpoint:")
        traceback.print_exc()
        logger.error(f"[ERROR] Chat endpoint failed: {e}")
        return ChatResponse(
            response="Sorry, I'm having trouble processing your request. Please try again.",
            requires_input="true"
        )

# 🤖 Async DeepSeek integration
async def chat_with_deepseek(
    messages: list,
    system_prompt: str,
    model: str = "deepseek-chat",
    max_retries: int = 3
) -> str:
    """
    Enhanced DeepSeek API integration with:
    - Better error handling
    - Usage tracking
    - Cost optimization
    - Response validation
    """
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_api_key:
        logger.error("DeepSeek API key not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service configuration error"
        )

    headers = {
        "Authorization": f"Bearer {deepseek_api_key}",
        "Accept": "application/json",
        "User-Agent": "FlightBookingAI/1.0",
    }

    formatted_messages = [{"role": "system", "content": system_prompt}]
    formatted_messages.extend([
        {"role": msg["role"], "content": msg["content"][:500]}  # Truncate long messages
        for msg in messages[-6:]  # Maintain conversation history
    ])

    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                # 🔄 Retry with exponential backoff
                response = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": formatted_messages,
                        "temperature": 0.7,
                        "max_tokens": 300,  # Increased from 150 for better responses
                        "stream": False
                    },
                    timeout=15.0  # Increased timeout
                )

                # 🔍 Validate response structure
                response_data = response.json()
                if not response_data.get("choices"):
                    logger.error("Invalid response format from DeepSeek")
                    raise ValueError("Invalid API response structure")

                # 📊 Track API usage in Firebase
                usage_data = response_data.get("usage", {})
                await update_session(
                    session_id=session_id,
                    data={
                        "api_usage": firestore.ArrayUnion([{
                            "timestamp": datetime.now(),
                            "model": model,
                            "prompt_tokens": usage_data.get("prompt_tokens", 0),
                            "completion_tokens": usage_data.get("completion_tokens", 0),
                            "cost": calculate_cost(usage_data, model)  # Implement pricing lookup
                        }])
                    }
                )

                return response_data["choices"][0]["message"]["content"].strip()

            except httpx.HTTPStatusError as e:
                logger.error(f"API Error [{e.response.status_code}]: {e.response.text}")
                if e.response.status_code in [401, 429]:
                    break  # Don't retry auth/rate limit errors
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

            except (httpx.RequestError, json.JSONDecodeError) as e:
                logger.error(f"Network/JSON error: {str(e)}")
                await asyncio.sleep(1 + attempt)  # Linear backoff

            except KeyError as e:
                logger.error(f"Missing key in response: {str(e)}")
                traceback.print_exc()
                break  # Don't retry on structural errors

        # 🔥 Fallback response after all retries
        logger.warning("All DeepSeek API attempts failed")
        return "I'm currently experiencing technical difficulties. Please try again later."


# 🏁 Server configuration
if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
