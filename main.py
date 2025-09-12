from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
import firebase_admin
from firebase_admin import credentials, firestore, auth
from datetime import datetime
import logging
import os
import json

# Initialize FastAPI app
app = FastAPI(title="AI Questions API", version="1.0.0")

def initialize_firebase():
    """Initialize Firebase with environment variables or service account file"""
    if not firebase_admin._apps:
        try:
            # Try to get credentials from environment variable (for Vercel)
            firebase_credentials = os.getenv('FIREBASE_SERVICE_ACCOUNT')
            
            if firebase_credentials:
                # Parse JSON from environment variable
                cred_dict = json.loads(firebase_credentials)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                print("Firebase initialized with environment credentials")
            else:
                # Fallback to service account file (for local development)
                service_account_path = os.getenv(
                    'FIREBASE_SERVICE_ACCOUNT_PATH', 
                    'C:\Users\cokun\Downloads\firebase-service-account.json'
                )
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
                print("Firebase initialized with service account file")
                
        except Exception as e:
            print(f"Error initializing Firebase: {e}")
            raise e

# Initialize Firebase
initialize_firebase()

# Initialize Firestore client
db = firestore.client()

# Rest of your FastAPI code remains the same...
# [Include all your existing endpoint code here]


# Security scheme
security = HTTPBearer()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models
class AIAnswersRequest(BaseModel):
    answers: Dict[int, str] = Field(..., description="Dictionary mapping question IDs to answers")
    
    class Config:
        json_schema_extra = {
            "example": {
                "answers": {
                    1: "I value honesty and communication",
                    2: "Travel, hiking, reading",
                    3: "Looking for a serious relationship"
                }
            }
        }

class AIAnswersResponse(BaseModel):
    success: bool
    message: str
    answers: Optional[Dict[int, str]] = None
    saved_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

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

@app.post("/api/ai-answers", response_model=AIAnswersResponse)
async def save_ai_answers(
    request: AIAnswersRequest,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Save AI question answers for a user
    """
    try:
        # Validate answers
        if not request.answers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Answers cannot be empty"
            )
        
        # Convert question IDs to strings for Firestore (Firestore doesn't support integer keys)
        answers_data = {str(k): v for k, v in request.answers.items()}
        
        # Prepare document data
        current_time = datetime.utcnow()
        doc_data = {
            "answers": answers_data,
            "user_id": user_id,
            "created_at": current_time,
            "updated_at": current_time,
            "total_questions": len(answers_data)
        }
        
        # Reference to user's AI answers document
        doc_ref = db.collection("ai_answers").document(user_id)
        
        # Check if document already exists
        existing_doc = doc_ref.get()
        
        if existing_doc.exists:
            # Update existing document
            doc_data["created_at"] = existing_doc.to_dict().get("created_at", current_time)
            doc_data["updated_at"] = current_time
            doc_ref.set(doc_data, merge=True)
            logger.info(f"Updated AI answers for user {user_id}")
        else:
            # Create new document
            doc_ref.set(doc_data)
            logger.info(f"Created new AI answers for user {user_id}")
        
        return AIAnswersResponse(
            success=True,
            message="AI answers saved successfully",
            answers=request.answers,
            saved_at=current_time,
            updated_at=current_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving AI answers for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save AI answers"
        )

@app.get("/api/ai-answers", response_model=AIAnswersResponse)
async def get_ai_answers(user_id: str = Depends(verify_firebase_token)):
    """
    Retrieve AI question answers for a user
    """
    try:
        # Reference to user's AI answers document
        doc_ref = db.collection("ai_answers").document(user_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return AIAnswersResponse(
                success=True,
                message="No AI answers found for user",
                answers={}
            )
        
        doc_data = doc.to_dict()
        
        # Convert string keys back to integers for consistency with frontend
        answers = {}
        if "answers" in doc_data:
            for k, v in doc_data["answers"].items():
                try:
                    answers[int(k)] = v
                except (ValueError, TypeError):
                    # Skip invalid keys
                    logger.warning(f"Invalid question ID key: {k}")
                    continue
        
        logger.info(f"Retrieved AI answers for user {user_id}: {len(answers)} questions")
        
        return AIAnswersResponse(
            success=True,
            message="AI answers retrieved successfully",
            answers=answers,
            saved_at=doc_data.get("created_at"),
            updated_at=doc_data.get("updated_at")
        )
        
    except Exception as e:
        logger.error(f"Error retrieving AI answers for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve AI answers"
        )

@app.delete("/api/ai-answers", response_model=AIAnswersResponse)
async def delete_ai_answers(user_id: str = Depends(verify_firebase_token)):
    """
    Delete AI question answers for a user
    """
    try:
        # Reference to user's AI answers document
        doc_ref = db.collection("ai_answers").document(user_id)
        
        # Check if document exists
        if not doc_ref.get().exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No AI answers found for user"
            )
        
        # Delete the document
        doc_ref.delete()
        
        logger.info(f"Deleted AI answers for user {user_id}")
        
        return AIAnswersResponse(
            success=True,
            message="AI answers deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting AI answers for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete AI answers"
        )

@app.put("/api/ai-answers/{question_id}", response_model=AIAnswersResponse)
async def update_single_answer(
    question_id: int,
    answer: str,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Update a single AI question answer
    """
    try:
        if not answer.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Answer cannot be empty"
            )
        
        # Reference to user's AI answers document
        doc_ref = db.collection("ai_answers").document(user_id)
        
        current_time = datetime.utcnow()
        
        # Update specific answer
        doc_ref.update({
            f"answers.{question_id}": answer.strip(),
            "updated_at": current_time
        })
        
        logger.info(f"Updated answer for question {question_id} for user {user_id}")
        
        return AIAnswersResponse(
            success=True,
            message=f"Answer for question {question_id} updated successfully",
            updated_at=current_time
        )
        
    except Exception as e:
        logger.error(f"Error updating answer for user {user_id}, question {question_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update answer"
        )

@app.get("/api/ai-answers/stats", response_model=Dict[str, Any])
async def get_answer_stats(user_id: str = Depends(verify_firebase_token)):
    """
    Get statistics about user's AI answers
    """
    try:
        # Reference to user's AI answers document
        doc_ref = db.collection("ai_answers").document(user_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return {
                "success": True,
                "total_questions": 0,
                "completed_questions": 0,
                "completion_percentage": 0,
                "last_updated": None
            }
        
        doc_data = doc.to_dict()
        answers = doc_data.get("answers", {})
        
        # Calculate stats
        total_questions = len(answers)
        completed_questions = sum(1 for answer in answers.values() if answer and answer.strip())
        completion_percentage = (completed_questions / total_questions * 100) if total_questions > 0 else 0
        
        return {
            "success": True,
            "total_questions": total_questions,
            "completed_questions": completed_questions,
            "completion_percentage": round(completion_percentage, 2),
            "last_updated": doc_data.get("updated_at"),
            "created_at": doc_data.get("created_at")
        }
        
    except Exception as e:
        logger.error(f"Error getting answer stats for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get answer statistics"
        )

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

# For Vercel deployment
handler = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)