from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import base64
import firebase_admin
from firebase_admin import credentials, firestore
import os, json
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