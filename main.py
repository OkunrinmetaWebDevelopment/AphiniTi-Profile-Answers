from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import base64
import firebase_admin
from firebase_admin import credentials, firestore, auth
from datetime import datetime
import logging
import os
import json
from typing import Dict, Optional, Any, List

# Initialize FastAPI app
app = FastAPI(title="AI Questions API", version="1.0.0")

def initialize_firebase():
    """Initialize Firebase with environment variables or service account file"""
    if not firebase_admin._apps:
        try:
            firebase_credentials = os.getenv('FIREBASE_SERVICE_ACCOUNT')
            firebase_credentials_b64 = os.getenv('FIREBASE_SERVICE_ACCOUNT_BASE64')

            cred_dict = None
            if firebase_credentials:  # raw JSON string
                cred_dict = json.loads(firebase_credentials)
            elif firebase_credentials_b64:  # base64 encoded JSON
                decoded = base64.b64decode(firebase_credentials_b64).decode("utf-8")
                cred_dict = json.loads(decoded)

            if cred_dict:
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                print("Firebase initialized with environment credentials")
            else:
                # fallback: local file
                service_account_path = os.getenv(
                    'FIREBASE_SERVICE_ACCOUNT_PATH',
                    'config/firebase-service-account.json'
                )
                if os.path.exists(service_account_path):
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                    print("Firebase initialized with service account file")
                else:
                    raise Exception("No Firebase credentials found. Please set FIREBASE_SERVICE_ACCOUNT or FIREBASE_SERVICE_ACCOUNT_BASE64.")
        except Exception as e:
            print(f"Error initializing Firebase: {e}")
            raise e

# Initialize Firebase
initialize_firebase()

# Initialize Firestore client
db = firestore.client()

# Security scheme
security = HTTPBearer()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models
class QuestionAnswerRequest(BaseModel):
    question_id: int = Field(..., description="The ID of the question")
    question_text: str = Field(..., description="The question text")
    answer: str = Field(..., description="The user's answer")
    user_id: str = Field(..., description="The user ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question_id": 1,
                "question_text": "What do you value most in a relationship?",
                "answer": "I value honesty and communication",
                "user_id": "user123"
            }
        }

class BulkAnswersRequest(BaseModel):
    answers: List[Dict[str, Any]] = Field(..., description="List of question-answer pairs")
    user_id: str = Field(..., description="The user ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user123",
                "answers": [
                    {
                        "question_id": 1,
                        "question_text": "What do you value most in a relationship?",
                        "answer": "I value honesty and communication"
                    },
                    {
                        "question_id": 2,
                        "question_text": "What are your hobbies?",
                        "answer": "Travel, hiking, reading"
                    }
                ]
            }
        }

class UserAnswersResponse(BaseModel):
    success: bool
    message: str
    user_id: str
    answers: Optional[List[Dict[str, Any]]] = None
    total_answers: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class QuestionAnswerResponse(BaseModel):
    success: bool
    message: str
    question_id: int
    question_text: str
    answer: str
    user_id: str
    saved_at: datetime

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: Optional[str] = None

# Authentication dependency
async def verify_firebase_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Verify Firebase ID token and return the user ID
    """
    try:
        # Extract token from Bearer scheme
        id_token = credentials.credentials
        
        # Verify the ID token
        decoded_token = auth.verify_id_token(id_token)
        user_id = decoded_token['uid']
        
        logger.info(f"Successfully authenticated user: {user_id}")
        return user_id
        
    except auth.InvalidIdTokenError:
        logger.error("Invalid Firebase ID token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    except auth.ExpiredIdTokenError:
        logger.error("Expired Firebase ID token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired"
        )
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

@app.post("/api/question-answer", response_model=QuestionAnswerResponse)
async def save_question_answer(
    request: QuestionAnswerRequest,
    authenticated_user_id: str = Depends(verify_firebase_token)
):
    """
    Save a single question-answer pair for a user
    """
    try:
        # Validate that the authenticated user matches the request user_id
        if authenticated_user_id != request.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot save answers for another user"
            )
        
        # Validate inputs
        if not request.answer.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Answer cannot be empty"
            )
        
        if not request.question_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Question text cannot be empty"
            )
        
        # Prepare document data
        current_time = datetime.utcnow()
        answer_data = {
            "question_id": request.question_id,
            "question_text": request.question_text.strip(),
            "answer": request.answer.strip(),
            "created_at": current_time,
            "updated_at": current_time
        }
        
        # Reference to user's answers collection
        user_doc_ref = db.collection("ai_answers").document(request.user_id)
        answer_doc_ref = user_doc_ref.collection("questions").document(str(request.question_id))
        
        # Check if answer already exists
        existing_answer = answer_doc_ref.get()
        
        if existing_answer.exists:
            # Update existing answer
            answer_data["created_at"] = existing_answer.to_dict().get("created_at", current_time)
            answer_data["updated_at"] = current_time
            answer_doc_ref.set(answer_data)
            logger.info(f"Updated answer for question {request.question_id} for user {request.user_id}")
        else:
            # Create new answer
            answer_doc_ref.set(answer_data)
            logger.info(f"Created new answer for question {request.question_id} for user {request.user_id}")
        
        # Update user summary document
        await update_user_summary(request.user_id)
        
        return QuestionAnswerResponse(
            success=True,
            message="Question answer saved successfully",
            question_id=request.question_id,
            question_text=request.question_text,
            answer=request.answer,
            user_id=request.user_id,
            saved_at=current_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving question answer for user {request.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save question answer"
        )

@app.post("/api/bulk-answers", response_model=UserAnswersResponse)
async def save_bulk_answers(
    request: BulkAnswersRequest,
    authenticated_user_id: str = Depends(verify_firebase_token)
):
    """
    Save multiple question-answer pairs for a user in a single request
    """
    try:
        # Validate that the authenticated user matches the request user_id
        if authenticated_user_id != request.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot save answers for another user"
            )
        
        if not request.answers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Answers list cannot be empty"
            )
        
        current_time = datetime.utcnow()
        user_doc_ref = db.collection("ai_answers").document(request.user_id)
        
        # Use a batch write for better performance
        batch = db.batch()
        
        for answer_item in request.answers:
            # Validate each answer item
            if not all(key in answer_item for key in ["question_id", "question_text", "answer"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Each answer must contain question_id, question_text, and answer"
                )
            
            if not answer_item["answer"].strip():
                continue  # Skip empty answers
            
            answer_data = {
                "question_id": answer_item["question_id"],
                "question_text": answer_item["question_text"].strip(),
                "answer": answer_item["answer"].strip(),
                "created_at": current_time,
                "updated_at": current_time
            }
            
            answer_doc_ref = user_doc_ref.collection("questions").document(str(answer_item["question_id"]))
            
            # Check if answer already exists
            existing_answer = answer_doc_ref.get()
            if existing_answer.exists:
                answer_data["created_at"] = existing_answer.to_dict().get("created_at", current_time)
            
            batch.set(answer_doc_ref, answer_data)
        
        # Commit the batch
        batch.commit()
        
        # Update user summary
        await update_user_summary(request.user_id)
        
        logger.info(f"Saved {len(request.answers)} answers for user {request.user_id}")
        
        return UserAnswersResponse(
            success=True,
            message=f"Successfully saved {len(request.answers)} answers",
            user_id=request.user_id,
            total_answers=len(request.answers),
            updated_at=current_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving bulk answers for user {request.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save bulk answers"
        )

@app.get("/api/user-answers/{user_id}", response_model=UserAnswersResponse)
async def get_user_answers(
    user_id: str,
    authenticated_user_id: str = Depends(verify_firebase_token)
):
    """
    Retrieve all answers for a specific user
    """
    try:
        # Validate that the authenticated user matches the requested user_id
        if authenticated_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access another user's answers"
            )
        
        # Get all answers for the user
        user_doc_ref = db.collection("ai_answers").document(user_id)
        questions_ref = user_doc_ref.collection("questions")
        
        answers_docs = questions_ref.stream()
        answers = []
        
        for doc in answers_docs:
            answer_data = doc.to_dict()
            answers.append({
                "question_id": answer_data.get("question_id"),
                "question_text": answer_data.get("question_text"),
                "answer": answer_data.get("answer"),
                "created_at": answer_data.get("created_at"),
                "updated_at": answer_data.get("updated_at")
            })
        
        # Sort by question_id
        answers.sort(key=lambda x: x["question_id"])
        
        logger.info(f"Retrieved {len(answers)} answers for user {user_id}")
        
        return UserAnswersResponse(
            success=True,
            message="User answers retrieved successfully",
            user_id=user_id,
            answers=answers,
            total_answers=len(answers)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving answers for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user answers"
        )

@app.get("/api/question-answer/{user_id}/{question_id}")
async def get_specific_answer(
    user_id: str,
    question_id: int,
    authenticated_user_id: str = Depends(verify_firebase_token)
):
    """
    Get a specific question-answer pair for a user
    """
    try:
        # Validate that the authenticated user matches the requested user_id
        if authenticated_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access another user's answers"
            )
        
        # Get specific answer
        user_doc_ref = db.collection("ai_answers").document(user_id)
        answer_doc_ref = user_doc_ref.collection("questions").document(str(question_id))
        
        answer_doc = answer_doc_ref.get()
        
        if not answer_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No answer found for question {question_id}"
            )
        
        answer_data = answer_doc.to_dict()
        
        return {
            "success": True,
            "message": "Answer retrieved successfully",
            "user_id": user_id,
            "question_id": answer_data.get("question_id"),
            "question_text": answer_data.get("question_text"),
            "answer": answer_data.get("answer"),
            "created_at": answer_data.get("created_at"),
            "updated_at": answer_data.get("updated_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving answer for user {user_id}, question {question_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve answer"
        )


async def update_user_summary(user_id: str):
    """
    Update the user's summary document with answer statistics
    """
    try:
        user_doc_ref = db.collection("ai_answers").document(user_id)
        questions_ref = user_doc_ref.collection("questions")
        
        # Count total answers
        answers_docs = list(questions_ref.stream())
        total_answers = len(answers_docs)
        
        # Update summary document
        summary_data = {
            "user_id": user_id,
            "total_answers": total_answers,
            "last_updated": datetime.utcnow()
        }
        
        user_doc_ref.set(summary_data, merge=True)
        
    except Exception as e:
        logger.error(f"Error updating user summary for {user_id}: {str(e)}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy", "timestamp": datetime.utcnow()}

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return ErrorResponse(
        message=exc.detail,
        error_code=str(exc.status_code)
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)